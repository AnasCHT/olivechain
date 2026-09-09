// SPDX-License-Identifier: Apache-2.0
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const (
	eventObjectType       = "eventIndex"
	subjectObjectType     = "subjectIndex"
	typeObjectType        = "typeIndex"
	actorObjectType       = "actorIndex"
	eventKeyPrefix        = "event:"
	orgKeyPrefix          = "org:"
	mspOrgKeyPrefix       = "orgmsp:"
	supersedeKeyPrefix    = "supersede:"
	governanceKeyPrefix   = "governance:"
	governanceThreshold   = 3
	maxPayloadBytes       = 128 * 1024
	maxEvidenceReferences = 32
)

func parseObject(raw, label string) (map[string]interface{}, error) {
	var value map[string]interface{}
	if err := json.Unmarshal([]byte(raw), &value); err != nil {
		return nil, fmt.Errorf("%s must be a JSON object: %w", label, err)
	}
	if value == nil {
		value = map[string]interface{}{}
	}
	return value, nil
}

func parseEvidence(raw string) ([]EvidenceRef, error) {
	if strings.TrimSpace(raw) == "" {
		return []EvidenceRef{}, nil
	}
	var refs []EvidenceRef
	if err := json.Unmarshal([]byte(raw), &refs); err != nil {
		return nil, fmt.Errorf("evidence must be a JSON array: %w", err)
	}
	if len(refs) > maxEvidenceReferences {
		return nil, fmt.Errorf("evidence has more than %d references", maxEvidenceReferences)
	}
	for i, ref := range refs {
		if strings.TrimSpace(ref.Name) == "" || strings.TrimSpace(ref.SHA256) == "" || strings.TrimSpace(ref.URI) == "" {
			return nil, fmt.Errorf("evidence[%d] requires name, sha256 and uri", i)
		}
	}
	return refs, nil
}

func validatePayload(eventType string, payload map[string]interface{}) error {
	required, ok := requiredFields[eventType]
	if !ok {
		return fmt.Errorf("unknown event type %q", eventType)
	}
	for _, field := range required {
		if _, exists := payload[field]; !exists {
			return fmt.Errorf("%s: missing required field %q", eventType, field)
		}
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode payload: %w", err)
	}
	if len(encoded) > maxPayloadBytes {
		return fmt.Errorf("payload exceeds %d bytes", maxPayloadBytes)
	}
	if eventType == EventResidueGeneration {
		if v, ok := payload["residue_type"].(string); ok && !residueTypes[v] {
			return fmt.Errorf("unsupported residue_type %q", v)
		}
	}
	if eventType == EventUsefulOutput || eventType == EventReturnOrSale {
		if v, ok := payload["output_type"].(string); ok && !outputTypes[v] {
			return fmt.Errorf("unsupported output_type %q", v)
		}
	}
	return nil
}

func callerIdentity(ctx contractapi.TransactionContextInterface) (*IdentityInfo, error) {
	mspID, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return nil, fmt.Errorf("read caller MSP: %w", err)
	}
	clientID, err := ctx.GetClientIdentity().GetID()
	if err != nil {
		return nil, fmt.Errorf("read caller identity: %w", err)
	}
	role, found, err := ctx.GetClientIdentity().GetAttributeValue("olivechain.role")
	if err != nil {
		return nil, fmt.Errorf("read olivechain.role attribute: %w", err)
	}
	if !found || strings.TrimSpace(role) == "" {
		return nil, fmt.Errorf("caller certificate is missing olivechain.role")
	}
	if roles, ok := mspAllowedRoles[mspID]; !ok || !roles[role] {
		return nil, fmt.Errorf("role %q is not valid for MSP %s", role, mspID)
	}
	walletAddress := ""
	if value, found, attrErr := ctx.GetClientIdentity().GetAttributeValue("olivechain.wallet"); attrErr != nil {
		return nil, fmt.Errorf("read olivechain.wallet attribute: %w", attrErr)
	} else if found {
		walletAddress = strings.TrimSpace(value)
	}
	digest := sha256.Sum256([]byte(clientID))
	info := &IdentityInfo{MSPID: mspID, Role: role, WalletAddress: walletAddress, ClientIDHash: hex.EncodeToString(digest[:]), OrgID: mspID}
	if org, err := getOrganizationByMSP(ctx, mspID); err == nil && org != nil {
		info.OrgID = org.OrgID
	}
	return info, nil
}

func requireRole(info *IdentityInfo, role string) error {
	if info.Role != role {
		return fmt.Errorf("operation requires role %q; caller role is %q", role, info.Role)
	}
	return nil
}

func requireEventPermission(info *IdentityInfo, eventType string) error {
	allowed, ok := permissions[eventType]
	if !ok {
		return fmt.Errorf("unknown event type %q", eventType)
	}
	if !allowed[info.Role] {
		return fmt.Errorf("role %q may not submit %s", info.Role, eventType)
	}
	return nil
}

func txTime(ctx contractapi.TransactionContextInterface) (float64, string, string, error) {
	stamp, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return 0, "", "", fmt.Errorf("read transaction timestamp: %w", err)
	}
	if stamp == nil {
		return 0, "", "", fmt.Errorf("transaction timestamp is missing")
	}
	t := stamp.AsTime().UTC()
	seconds := float64(t.Unix()) + float64(t.Nanosecond())/1e9
	orderKey := fmt.Sprintf("%020d", t.UnixNano())
	return seconds, t.Format(time.RFC3339Nano), orderKey, nil
}

func eventKey(eventID string) string     { return eventKeyPrefix + strings.TrimSpace(eventID) }
func orgKey(orgID string) string         { return orgKeyPrefix + strings.TrimSpace(orgID) }
func mspOrgKey(mspID string) string      { return mspOrgKeyPrefix + strings.TrimSpace(mspID) }
func supersedeKey(eventID string) string { return supersedeKeyPrefix + strings.TrimSpace(eventID) }
func governanceKey(proposalID string) string {
	return governanceKeyPrefix + strings.TrimSpace(proposalID)
}

func putJSON(ctx contractapi.TransactionContextInterface, key string, value interface{}) error {
	encoded, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("encode %s: %w", key, err)
	}
	if err := ctx.GetStub().PutState(key, encoded); err != nil {
		return fmt.Errorf("write %s: %w", key, err)
	}
	return nil
}

func getEventRaw(ctx contractapi.TransactionContextInterface, eventID string) (*Event, error) {
	raw, err := ctx.GetStub().GetState(eventKey(eventID))
	if err != nil {
		return nil, fmt.Errorf("read event %q: %w", eventID, err)
	}
	if raw == nil {
		return nil, fmt.Errorf("event %q does not exist", eventID)
	}
	var event Event
	if err := json.Unmarshal(raw, &event); err != nil {
		return nil, fmt.Errorf("decode event %q: %w", eventID, err)
	}
	return &event, nil
}

func getSupersededBy(ctx contractapi.TransactionContextInterface, eventID string) (string, error) {
	raw, err := ctx.GetStub().GetState(supersedeKey(eventID))
	if err != nil {
		return "", fmt.Errorf("read supersession for %q: %w", eventID, err)
	}
	return string(raw), nil
}

func eventWithSupersession(ctx contractapi.TransactionContextInterface, event *Event) (*Event, error) {
	copyEvent := *event
	next, err := getSupersededBy(ctx, event.EventID)
	if err != nil {
		return nil, err
	}
	copyEvent.SupersededBy = next
	return &copyEvent, nil
}

func effectiveEvent(ctx contractapi.TransactionContextInterface, event *Event) (*Event, error) {
	result := *event
	result.Payload = cloneMap(event.Payload)
	currentID := event.EventID
	seen := map[string]bool{currentID: true}
	for {
		next, err := getSupersededBy(ctx, currentID)
		if err != nil {
			return nil, err
		}
		if next == "" {
			break
		}
		if seen[next] {
			return nil, fmt.Errorf("correction cycle detected at event %s", next)
		}
		seen[next] = true
		correction, err := getEventRaw(ctx, next)
		if err != nil {
			return nil, err
		}
		corrected, ok := correction.Payload["corrected_payload"].(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("correction %s has malformed corrected_payload", next)
		}
		result.Payload = mergeMaps(result.Payload, corrected)
		result.SupersededBy = next
		currentID = next
	}
	return &result, nil
}

func cloneMap(in map[string]interface{}) map[string]interface{} {
	out := make(map[string]interface{}, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

func mergeMaps(base, patch map[string]interface{}) map[string]interface{} {
	out := cloneMap(base)
	for k, v := range patch {
		out[k] = v
	}
	return out
}

func hashEvent(event *Event) (string, error) {
	copyEvent := *event
	copyEvent.EventHash = ""
	copyEvent.SupersededBy = ""
	encoded, err := json.Marshal(copyEvent)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}

func addEventIndexes(ctx contractapi.TransactionContextInterface, event *Event, orderKey string) error {
	indexes := []struct {
		objectType string
		attrs      []string
	}{
		{eventObjectType, []string{orderKey, event.EventID}},
		{subjectObjectType, []string{event.SubjectID, orderKey, event.EventID}},
		{typeObjectType, []string{event.EventType, orderKey, event.EventID}},
		{actorObjectType, []string{event.ActorOrg, orderKey, event.EventID}},
	}
	for _, idx := range indexes {
		key, err := ctx.GetStub().CreateCompositeKey(idx.objectType, idx.attrs)
		if err != nil {
			return fmt.Errorf("create %s index: %w", idx.objectType, err)
		}
		if err := ctx.GetStub().PutState(key, []byte{0}); err != nil {
			return fmt.Errorf("write %s index: %w", idx.objectType, err)
		}
	}
	return nil
}

func listEventsFromIndex(ctx contractapi.TransactionContextInterface, objectType string, attrs []string, includeSuperseded bool) ([]*Event, error) {
	iter, err := ctx.GetStub().GetStateByPartialCompositeKey(objectType, attrs)
	if err != nil {
		return nil, fmt.Errorf("query %s: %w", objectType, err)
	}
	defer iter.Close()
	events := make([]*Event, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, fmt.Errorf("iterate %s: %w", objectType, err)
		}
		_, parts, err := ctx.GetStub().SplitCompositeKey(row.Key)
		if err != nil || len(parts) == 0 {
			return nil, fmt.Errorf("decode %s index key", objectType)
		}
		eventID := parts[len(parts)-1]
		event, err := getEventRaw(ctx, eventID)
		if err != nil {
			return nil, err
		}
		enriched, err := eventWithSupersession(ctx, event)
		if err != nil {
			return nil, err
		}
		if !includeSuperseded && enriched.SupersededBy != "" {
			continue
		}
		events = append(events, enriched)
	}
	sort.SliceStable(events, func(i, j int) bool {
		if events[i].Timestamp == events[j].Timestamp {
			return events[i].EventID < events[j].EventID
		}
		return events[i].Timestamp < events[j].Timestamp
	})
	return events, nil
}

func writeEvent(ctx contractapi.TransactionContextInterface, eventType, subjectID string, payload map[string]interface{}, evidence []EvidenceRef, actor *IdentityInfo, eventID string) (*Event, error) {
	if strings.TrimSpace(subjectID) == "" {
		return nil, fmt.Errorf("subject_id is required")
	}
	if err := validatePayload(eventType, payload); err != nil {
		return nil, err
	}
	if err := validateWorkflowTransition(ctx, eventType, subjectID, payload); err != nil {
		return nil, err
	}
	if strings.TrimSpace(eventID) == "" {
		eventID = ctx.GetStub().GetTxID()
	}
	if existing, err := ctx.GetStub().GetState(eventKey(eventID)); err != nil {
		return nil, err
	} else if existing != nil {
		return nil, fmt.Errorf("event_id %q already exists", eventID)
	}
	timestamp, timestampRFC, orderKey, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	event := &Event{
		DocType: "event", EventID: eventID, EventType: eventType, SubjectID: subjectID,
		ActorOrg: actor.OrgID, ActorMSP: actor.MSPID, ActorRole: actor.Role, ActorWallet: actor.WalletAddress,
		ClientIDHash: actor.ClientIDHash, Timestamp: timestamp, TimestampRFC: timestampRFC,
		Payload: payload, Evidence: evidence, FabricTxID: ctx.GetStub().GetTxID(),
		SignedByFabric: true,
	}
	event.EventHash, err = hashEvent(event)
	if err != nil {
		return nil, fmt.Errorf("hash event: %w", err)
	}
	if err := putJSON(ctx, eventKey(event.EventID), event); err != nil {
		return nil, err
	}
	if err := addEventIndexes(ctx, event, orderKey); err != nil {
		return nil, err
	}
	if err := applyWalletIncentives(ctx, event); err != nil {
		return nil, fmt.Errorf("apply wallet incentives: %w", err)
	}
	emitted, _ := json.Marshal(map[string]string{"event_id": event.EventID, "event_type": event.EventType, "subject_id": event.SubjectID})
	if err := ctx.GetStub().SetEvent("OliveChainEventCommitted", emitted); err != nil {
		return nil, fmt.Errorf("emit event: %w", err)
	}
	return event, nil
}

func asFloat(value interface{}) float64 {
	switch v := value.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case json.Number:
		n, _ := v.Float64()
		return n
	case string:
		n, _ := strconv.ParseFloat(v, 64)
		return n
	default:
		return 0
	}
}

func asString(value interface{}) string {
	if value == nil {
		return ""
	}
	if v, ok := value.(string); ok {
		return v
	}
	return fmt.Sprint(value)
}

func asBool(value interface{}) bool {
	if v, ok := value.(bool); ok {
		return v
	}
	return strings.EqualFold(asString(value), "true")
}

func asStringSlice(value interface{}) []string {
	raw, ok := value.([]interface{})
	if !ok {
		if typed, ok := value.([]string); ok {
			return typed
		}
		return nil
	}
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		out = append(out, asString(item))
	}
	return out
}

func round2(value float64) float64 { return math.Round(value*100) / 100 }

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

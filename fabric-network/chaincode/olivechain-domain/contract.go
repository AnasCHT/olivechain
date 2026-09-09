// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

type OliveChainContract struct {
	contractapi.Contract
}

func (c *OliveChainContract) GetContractInfo(ctx contractapi.TransactionContextInterface) (*ContractInfo, error) {
	return &ContractInfo{
		Name: "olivechain", Version: "1.0.0-wallet-incentives",
		SourceModel:         "traceability + workflow + wallet + token + reputation model",
		IdentityModel:       "wallet authentication + Fabric MSP + role + wallet certificate attributes",
		GovernanceThreshold: governanceThreshold,
	}, nil
}

func (c *OliveChainContract) WhoAmI(ctx contractapi.TransactionContextInterface) (*IdentityInfo, error) {
	return callerIdentity(ctx)
}

func (c *OliveChainContract) GetSchema(ctx contractapi.TransactionContextInterface) ([]SchemaEntry, error) {
	entries := make([]SchemaEntry, 0, len(allEventTypes))
	for _, eventType := range allEventTypes {
		roles := make([]string, 0)
		for role := range permissions[eventType] {
			roles = append(roles, role)
		}
		sort.Strings(roles)
		entries = append(entries, SchemaEntry{EventType: eventType, AllowedRoles: roles, RequiredFields: append([]string{}, requiredFields[eventType]...)})
	}
	return entries, nil
}

// SubmitEvent is the Fabric-backed replacement for Ledger.append and the
// /events/prepare + /events/commit persistence path. Fabric supplies ordering,
// transaction signatures and identity verification.
func (c *OliveChainContract) SubmitEvent(ctx contractapi.TransactionContextInterface, eventID, eventType, subjectID, payloadJSON, evidenceJSON string) (*Event, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if eventType == EventCorrection {
		return nil, fmt.Errorf("use CorrectEvent for correction events")
	}
	if eventType == EventRewardIssued || eventType == EventReviewFlag || eventType == EventReviewResolution {
		return nil, fmt.Errorf("%s requires the consortium governance workflow", eventType)
	}
	if err := requireEventPermission(caller, eventType); err != nil {
		return nil, err
	}
	// Public QR scans keep using the consortium consumer service identity. Every
	// operational actor event must come from a Fabric certificate bound to an
	// active OliveChain wallet.
	if !(eventType == EventConsumerVerification && caller.Role == RoleConsumer && caller.WalletAddress == "") {
		if _, err := validateActiveWalletBinding(ctx, caller); err != nil {
			return nil, err
		}
	}
	payload, err := parseObject(payloadJSON, "payload")
	if err != nil {
		return nil, err
	}
	evidence, err := parseEvidence(evidenceJSON)
	if err != nil {
		return nil, err
	}
	return writeEvent(ctx, eventType, subjectID, payload, evidence, caller, eventID)
}

func (c *OliveChainContract) CorrectEvent(ctx contractapi.TransactionContextInterface, eventID, targetEventID, reason, correctedPayloadJSON, evidenceJSON string) (*Event, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if _, err := validateActiveWalletBinding(ctx, caller); err != nil {
		return nil, err
	}
	target, err := getEventRaw(ctx, targetEventID)
	if err != nil {
		return nil, err
	}
	if target.ActorMSP != caller.MSPID {
		return nil, fmt.Errorf("only the original actor organization may directly correct event %s; consortium corrections require governance", targetEventID)
	}
	if target.ActorRole != caller.Role {
		return nil, fmt.Errorf("direct correction requires the original event role %s; caller role is %s", target.ActorRole, caller.Role)
	}
	patch, err := parseObject(correctedPayloadJSON, "corrected_payload")
	if err != nil {
		return nil, err
	}
	evidence, err := parseEvidence(evidenceJSON)
	if err != nil {
		return nil, err
	}
	payload := map[string]interface{}{
		"supersedes_event":  targetEventID,
		"reason":            reason,
		"corrected_payload": patch,
	}
	correction, err := writeEvent(ctx, EventCorrection, target.SubjectID, payload, evidence, caller, eventID)
	if err != nil {
		return nil, err
	}
	if existing, err := getSupersededBy(ctx, targetEventID); err != nil {
		return nil, err
	} else if existing != "" {
		return nil, fmt.Errorf("event %s is already superseded by %s", targetEventID, existing)
	}
	if err := ctx.GetStub().PutState(supersedeKey(targetEventID), []byte(correction.EventID)); err != nil {
		return nil, err
	}
	return correction, nil
}

func (c *OliveChainContract) GetEvent(ctx contractapi.TransactionContextInterface, eventID string) (*Event, error) {
	event, err := getEventRaw(ctx, eventID)
	if err != nil {
		return nil, err
	}
	return eventWithSupersession(ctx, event)
}

func (c *OliveChainContract) GetEffectiveEvent(ctx contractapi.TransactionContextInterface, eventID string) (*Event, error) {
	event, err := getEventRaw(ctx, eventID)
	if err != nil {
		return nil, err
	}
	return effectiveEvent(ctx, event)
}

func (c *OliveChainContract) GetAllEvents(ctx contractapi.TransactionContextInterface, includeSuperseded bool) ([]*Event, error) {
	return listEventsFromIndex(ctx, eventObjectType, nil, includeSuperseded)
}

func (c *OliveChainContract) GetEventsForSubject(ctx contractapi.TransactionContextInterface, subjectID string, includeSuperseded bool) ([]*Event, error) {
	return listEventsFromIndex(ctx, subjectObjectType, []string{subjectID}, includeSuperseded)
}

func (c *OliveChainContract) GetEventsByType(ctx contractapi.TransactionContextInterface, eventType string, includeSuperseded bool) ([]*Event, error) {
	if _, ok := requiredFields[eventType]; !ok {
		return nil, fmt.Errorf("unknown event type %q", eventType)
	}
	return listEventsFromIndex(ctx, typeObjectType, []string{eventType}, includeSuperseded)
}

func (c *OliveChainContract) GetEventsByActor(ctx contractapi.TransactionContextInterface, actorOrg string, includeSuperseded bool) ([]*Event, error) {
	return listEventsFromIndex(ctx, actorObjectType, []string{actorOrg}, includeSuperseded)
}

// GetSellableProducts implements the existing project requirement for a
// seller-facing catalogue of batches that reached distribution/retail.
func (c *OliveChainContract) GetSellableProducts(ctx contractapi.TransactionContextInterface) ([]SellableProduct, error) {
	distributions, err := c.GetEventsByType(ctx, EventDistributionRetail, false)
	if err != nil {
		return nil, err
	}
	byBatch := map[string]*Event{}
	for _, event := range distributions {
		byBatch[event.SubjectID] = event
	}
	batchIDs := make([]string, 0, len(byBatch))
	for batchID := range byBatch {
		batchIDs = append(batchIDs, batchID)
	}
	sort.Strings(batchIDs)
	products := make([]SellableProduct, 0, len(batchIDs))
	for _, batchID := range batchIDs {
		events, err := c.GetEventsForSubject(ctx, batchID, false)
		if err != nil {
			return nil, err
		}
		product := SellableProduct{BatchID: batchID, Details: map[string]interface{}{}}
		for _, event := range events {
			effective, err := effectiveEvent(ctx, event)
			if err != nil {
				return nil, err
			}
			switch effective.EventType {
			case EventBottling:
				product.LotID = asString(effective.Payload["lot_id"])
				product.BottleCount = asFloat(effective.Payload["bottle_count"])
				product.FillDate = asString(effective.Payload["fill_date"])
				product.LabelClaims = effective.Payload["label_claims"]
			case EventLabVerification:
				product.QualityClass = asString(effective.Payload["quality_class"])
			case EventDistributionRetail:
				product.Destination = asString(effective.Payload["destination"])
				product.CurrentHolder = asString(effective.Payload["to_org"])
			}
		}
		product.Details["passport_ready"] = product.LotID != "" && product.Destination != ""
		products = append(products, product)
	}
	return products, nil
}

func marshalString(value interface{}) string {
	encoded, _ := json.Marshal(value)
	return string(encoded)
}

func normalizedPayloadKey(event *Event) string {
	return strings.Join([]string{event.EventType, event.SubjectID, event.ActorOrg, marshalString(event.Payload)}, "|")
}

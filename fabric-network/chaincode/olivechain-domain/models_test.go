// SPDX-License-Identifier: Apache-2.0
package main

import "testing"

func TestOriginalEventModelIsPreserved(t *testing.T) {
	if len(allEventTypes) != 18 {
		t.Fatalf("expected 18 event types from models.py, got %d", len(allEventTypes))
	}
	if !permissions[EventMilling][RoleMill] || permissions[EventMilling][RoleFarmer] {
		t.Fatal("milling permissions diverged from models.py")
	}
	if !permissions[EventResidueCustody][RoleCollector] || !permissions[EventResidueCustody][RoleProcessor] {
		t.Fatal("residue custody permissions diverged from models.py")
	}
	if len(requiredFields[EventMilling]) != 5 {
		t.Fatal("milling required fields diverged from models.py")
	}
}

func TestMSPRolePlacement(t *testing.T) {
	cases := []struct {
		msp, role string
		allowed   bool
	}{
		{"FarmerOrgMSP", RoleFarmer, true},
		{"MakerOrgMSP", RoleMill, true},
		{"MakerOrgMSP", RoleBottler, true},
		{"CourierOrgMSP", RoleCollector, true},
		{"RecyclerOrgMSP", RoleProcessor, true},
		{"FarmerOrgMSP", RoleMill, false},
		{"RecyclerOrgMSP", RoleAuthority, false},
	}
	for _, tc := range cases {
		if got := mspAllowedRoles[tc.msp][tc.role]; got != tc.allowed {
			t.Fatalf("%s role %s: got %v, want %v", tc.msp, tc.role, got, tc.allowed)
		}
	}
}

func TestMergeMapsMatchesCorrectionSemantics(t *testing.T) {
	original := map[string]interface{}{"weight_kg": 100.0, "method": "manual"}
	corrected := map[string]interface{}{"weight_kg": 95.0}
	merged := mergeMaps(original, corrected)
	if merged["weight_kg"] != 95.0 || merged["method"] != "manual" {
		t.Fatalf("unexpected merged payload: %#v", merged)
	}
	if original["weight_kg"] != 100.0 {
		t.Fatal("merge mutated original payload")
	}
}

func workflowEvent(eventType string, accepted bool) *Event {
	payload := map[string]interface{}{}
	if eventType == EventResidueCustody {
		payload["accepted"] = accepted
	}
	if eventType == EventResidueGeneration {
		payload["origin_batch"] = "BATCH-1"
	}
	return &Event{EventID: eventType, EventType: eventType, SubjectID: "S1", Payload: payload, TimestampRFC: "2026-08-02T00:00:00Z"}
}

func TestProductWorkflowStatusEnforcesOrder(t *testing.T) {
	events := []*Event{
		workflowEvent(EventCultivation, false),
		workflowEvent(EventHarvest, false),
	}
	status, err := analyzeWorkflow("BATCH-1", events)
	if err != nil {
		t.Fatal(err)
	}
	if !status.Valid || status.CurrentStep != EventHarvest {
		t.Fatalf("unexpected status: %#v", status)
	}
	if len(status.NextAllowed) != 1 || status.NextAllowed[0] != EventCollectionTransport {
		t.Fatalf("unexpected next step: %#v", status.NextAllowed)
	}
}

func TestProductWorkflowDetectsOutOfOrderHistory(t *testing.T) {
	events := []*Event{
		workflowEvent(EventCultivation, false),
		workflowEvent(EventMilling, false),
	}
	status, err := analyzeWorkflow("BATCH-1", events)
	if err != nil {
		t.Fatal(err)
	}
	if status.Valid {
		t.Fatalf("expected invalid status: %#v", status)
	}
}

func TestCircularWorkflowWaitsForAcceptance(t *testing.T) {
	events := []*Event{
		workflowEvent(EventResidueGeneration, false),
		workflowEvent(EventResidueCustody, false),
	}
	status, err := analyzeWorkflow("RES-1", events)
	if err != nil {
		t.Fatal(err)
	}
	if len(status.NextAllowed) != 1 || status.NextAllowed[0] != EventResidueCustody {
		t.Fatalf("expected another custody event, got %#v", status.NextAllowed)
	}

	events = append(events, workflowEvent(EventResidueCustody, true))
	status, err = analyzeWorkflow("RES-1", events)
	if err != nil {
		t.Fatal(err)
	}
	if len(status.NextAllowed) != 1 || status.NextAllowed[0] != EventValorization {
		t.Fatalf("expected valorization, got %#v", status.NextAllowed)
	}
}

func TestCircularWorkflowAllowsRepeatedOutputs(t *testing.T) {
	events := []*Event{
		workflowEvent(EventResidueGeneration, false),
		workflowEvent(EventResidueCustody, true),
		workflowEvent(EventValorization, false),
		workflowEvent(EventUsefulOutput, false),
		workflowEvent(EventUsefulOutput, false),
	}
	status, err := analyzeWorkflow("RES-1", events)
	if err != nil {
		t.Fatal(err)
	}
	if !status.Valid || status.CurrentStep != EventUsefulOutput {
		t.Fatalf("unexpected status: %#v", status)
	}
	if !containsString(status.NextAllowed, EventUsefulOutput) || !containsString(status.NextAllowed, EventReturnOrSale) {
		t.Fatalf("unexpected next steps: %#v", status.NextAllowed)
	}
}

func TestWalletRoleVisibilityPolicy(t *testing.T) {
	if org, ok := publicSignupRoles[RoleFarmer]; !ok || org != "farmer-org" {
		t.Fatalf("farmer should be a public-request role for farmer-org")
	}
	if org, ok := publicSignupRoles[RoleCollector]; !ok || org != "courier-org" {
		t.Fatalf("collector should be a public-request role for courier-org")
	}
	if _, ok := publicSignupRoles[RoleLaboratory]; ok {
		t.Fatal("laboratory must not be exposed through public sign-up")
	}
	if org := restrictedWalletRoles[RoleLaboratory]; org != "maker-org" {
		t.Fatalf("laboratory should be restricted to maker-org, got %q", org)
	}
	if org := restrictedWalletRoles[RoleProcessor]; org != "recycler-org" {
		t.Fatalf("processor should be restricted to recycler-org, got %q", org)
	}
}

func TestWalletAddressDerivation(t *testing.T) {
	// The ledger address is content-derived from the wallet's SPKI bytes.
	spki := "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQQ=="
	address, err := expectedWalletAddress(spki)
	if err != nil {
		t.Fatal(err)
	}
	if len(address) != len("OLIVE-")+24 || address[:6] != "OLIVE-" {
		t.Fatalf("unexpected wallet address %q", address)
	}
}

func TestTokenPolicyDefaults(t *testing.T) {
	policy, err := (&OliveChainContract{}).GetTokenPolicy(nil)
	if err != nil {
		t.Fatal(err)
	}
	if policy.EcoTokenPerVerifiedKWh != 0.1 {
		t.Fatalf("unexpected ECO policy: %v", policy.EcoTokenPerVerifiedKWh)
	}
	if policy.TrustTransferable || policy.EcoTransferable || policy.OliveTransferable {
		t.Fatal("prototype wallet assets should be non-transferable")
	}
}

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

func governanceEventType(eventType string) bool {
	return eventType == EventRewardIssued || eventType == EventReviewFlag || eventType == EventReviewResolution
}

func (c *OliveChainContract) ProposeGovernanceEvent(ctx contractapi.TransactionContextInterface, proposalID, eventType, subjectID, payloadJSON, evidenceJSON string) (*GovernanceProposal, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireRole(caller, RoleOrgAdmin); err != nil {
		return nil, err
	}
	if !governanceEventType(eventType) {
		return nil, fmt.Errorf("event type %s is not a consortium-governed action", eventType)
	}
	proposalID = strings.TrimSpace(proposalID)
	if proposalID == "" {
		return nil, fmt.Errorf("proposal_id is required")
	}
	if raw, err := ctx.GetStub().GetState(governanceKey(proposalID)); err != nil {
		return nil, err
	} else if raw != nil {
		return nil, fmt.Errorf("governance proposal %q already exists", proposalID)
	}
	payload, err := parseObject(payloadJSON, "payload")
	if err != nil {
		return nil, err
	}
	if err := validatePayload(eventType, payload); err != nil {
		return nil, err
	}
	evidence, err := parseEvidence(evidenceJSON)
	if err != nil {
		return nil, err
	}
	_, timestampRFC, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	proposal := &GovernanceProposal{
		DocType: "governance_proposal", ProposalID: proposalID, EventType: eventType,
		SubjectID: subjectID, Payload: payload, Evidence: evidence,
		ProposedByMSP: caller.MSPID, CreatedAt: timestampRFC,
		Approvals: []GovernanceApproval{{MSPID: caller.MSPID, ClientIDHash: caller.ClientIDHash, ApprovedAt: timestampRFC}},
	}
	if err := putJSON(ctx, governanceKey(proposalID), proposal); err != nil {
		return nil, err
	}
	return proposal, nil
}

func (c *OliveChainContract) ApproveGovernanceProposal(ctx contractapi.TransactionContextInterface, proposalID string) (*GovernanceProposal, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireRole(caller, RoleOrgAdmin); err != nil {
		return nil, err
	}
	proposal, err := c.GetGovernanceProposal(ctx, proposalID)
	if err != nil {
		return nil, err
	}
	if proposal.Finalized {
		return nil, fmt.Errorf("proposal %s is already finalized", proposalID)
	}
	for _, approval := range proposal.Approvals {
		if approval.MSPID == caller.MSPID {
			return proposal, nil
		}
	}
	_, timestampRFC, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	proposal.Approvals = append(proposal.Approvals, GovernanceApproval{MSPID: caller.MSPID, ClientIDHash: caller.ClientIDHash, ApprovedAt: timestampRFC})
	sort.Slice(proposal.Approvals, func(i, j int) bool { return proposal.Approvals[i].MSPID < proposal.Approvals[j].MSPID })
	if err := putJSON(ctx, governanceKey(proposalID), proposal); err != nil {
		return nil, err
	}
	return proposal, nil
}

func (c *OliveChainContract) FinalizeGovernanceProposal(ctx contractapi.TransactionContextInterface, proposalID, eventID string) (*Event, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireRole(caller, RoleOrgAdmin); err != nil {
		return nil, err
	}
	proposal, err := c.GetGovernanceProposal(ctx, proposalID)
	if err != nil {
		return nil, err
	}
	if proposal.Finalized {
		return nil, fmt.Errorf("proposal %s is already finalized as event %s", proposalID, proposal.FinalEventID)
	}
	unique := map[string]bool{}
	for _, approval := range proposal.Approvals {
		if _, valid := mspAllowedRoles[approval.MSPID]; valid {
			unique[approval.MSPID] = true
		}
	}
	if len(unique) < governanceThreshold {
		return nil, fmt.Errorf("proposal requires %d distinct business MSP approvals; currently has %d", governanceThreshold, len(unique))
	}
	switch proposal.EventType {
	case EventRewardIssued:
		if err := c.validateRewardProposal(ctx, proposal.Payload); err != nil {
			return nil, err
		}
	case EventReviewFlag:
		if _, err := getEventRaw(ctx, asString(proposal.Payload["subject_event"])); err != nil {
			return nil, err
		}
	case EventReviewResolution:
		flag, err := getEventRaw(ctx, asString(proposal.Payload["flag_event"]))
		if err != nil {
			return nil, err
		}
		if flag.EventType != EventReviewFlag {
			return nil, fmt.Errorf("flag_event does not reference a review_flag")
		}
	}
	authority := &IdentityInfo{MSPID: "Consortium", Role: RoleAuthority, ClientIDHash: caller.ClientIDHash, OrgID: "consortium-authority"}
	event, err := writeEvent(ctx, proposal.EventType, proposal.SubjectID, proposal.Payload, proposal.Evidence, authority, eventID)
	if err != nil {
		return nil, err
	}
	proposal.Finalized = true
	proposal.FinalEventID = event.EventID
	if err := putJSON(ctx, governanceKey(proposalID), proposal); err != nil {
		return nil, err
	}
	return event, nil
}

func (c *OliveChainContract) GetGovernanceProposal(ctx contractapi.TransactionContextInterface, proposalID string) (*GovernanceProposal, error) {
	raw, err := ctx.GetStub().GetState(governanceKey(proposalID))
	if err != nil {
		return nil, err
	}
	if raw == nil {
		return nil, fmt.Errorf("governance proposal %q does not exist", proposalID)
	}
	var proposal GovernanceProposal
	if err := json.Unmarshal(raw, &proposal); err != nil {
		return nil, err
	}
	return &proposal, nil
}

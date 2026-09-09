// SPDX-License-Identifier: Apache-2.0
package main

import (
	"fmt"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const (
	WorkflowProduct  = "product"
	WorkflowCircular = "circular"
	WorkflowUnknown  = "unknown"
)

var productWorkflow = []string{
	EventCultivation,
	EventHarvest,
	EventCollectionTransport,
	EventMilling,
	EventLabVerification,
	EventBottling,
	EventDistributionRetail,
}

var circularWorkflow = []string{
	EventResidueGeneration,
	EventResidueCustody,
	EventValorization,
	EventUsefulOutput,
	EventReturnOrSale,
	EventEnvAccounting,
}

var productStageLabels = map[string]string{
	EventCultivation:         "Farming recorded",
	EventHarvest:             "Harvest recorded",
	EventCollectionTransport: "Olives transported",
	EventMilling:             "Olives milled",
	EventLabVerification:     "Quality verified",
	EventBottling:            "Oil bottled",
	EventDistributionRetail:  "Delivered to seller",
}

var circularStageLabels = map[string]string{
	EventResidueGeneration: "Residue generated",
	EventResidueCustody:    "Residue in custody transfer",
	EventValorization:      "Residue valorized",
	EventUsefulOutput:      "Useful output recorded",
	EventReturnOrSale:      "Output returned or sold",
	EventEnvAccounting:     "Environmental accounting complete",
}

func workflowForEvent(eventType string) (string, []string, bool) {
	if containsString(productWorkflow, eventType) {
		return WorkflowProduct, productWorkflow, true
	}
	if containsString(circularWorkflow, eventType) {
		return WorkflowCircular, circularWorkflow, true
	}
	return WorkflowUnknown, nil, false
}

func workflowIndex(stages []string, eventType string) int {
	for i, stage := range stages {
		if stage == eventType {
			return i
		}
	}
	return -1
}

func stageLabel(workflow, stage string) string {
	if stage == "" || stage == "not_started" {
		return "Not started"
	}
	if workflow == WorkflowProduct {
		if label := productStageLabels[stage]; label != "" {
			return label
		}
	}
	if workflow == WorkflowCircular {
		if label := circularStageLabels[stage]; label != "" {
			return label
		}
	}
	return strings.ReplaceAll(stage, "_", " ")
}

func subjectWorkflowEvents(ctx contractapi.TransactionContextInterface, subjectID string) ([]*Event, error) {
	events, err := listEventsFromIndex(ctx, subjectObjectType, []string{subjectID}, false)
	if err != nil {
		return nil, err
	}
	relevant := make([]*Event, 0, len(events))
	for _, event := range events {
		if _, _, ok := workflowForEvent(event.EventType); ok {
			relevant = append(relevant, event)
		}
	}
	return relevant, nil
}

func analyzeWorkflow(subjectID string, events []*Event) (*WorkflowStatus, error) {
	status := &WorkflowStatus{
		DocType:           "workflow_status",
		SubjectID:         subjectID,
		Workflow:          WorkflowUnknown,
		Exists:            false,
		CurrentStep:       "not_started",
		CurrentLabel:      "Not started",
		CurrentStepNumber: 0,
		TotalSteps:        0,
		ProgressPct:       0,
		NextAllowed:       []string{},
		Complete:          false,
		Valid:             true,
		Message:           "No workflow event has been recorded for this subject.",
		LastEventID:       "",
		UpdatedAt:         "",
		OriginBatch:       "",
	}
	if len(events) == 0 {
		return status, nil
	}

	workflow := WorkflowUnknown
	var stages []string
	for _, event := range events {
		candidate, candidateStages, ok := workflowForEvent(event.EventType)
		if !ok {
			continue
		}
		if workflow == WorkflowUnknown {
			workflow = candidate
			stages = candidateStages
		} else if workflow != candidate {
			status.Valid = false
			status.Message = fmt.Sprintf("subject %s mixes product and circular workflow events", subjectID)
			return status, nil
		}
	}
	if workflow == WorkflowUnknown {
		return status, nil
	}

	status.Workflow = workflow
	status.Exists = true
	status.TotalSteps = len(stages)
	current := -1
	acceptedCustody := false
	seen := map[string]int{}

	for _, event := range events {
		candidate, _, ok := workflowForEvent(event.EventType)
		if !ok || candidate != workflow {
			continue
		}
		idx := workflowIndex(stages, event.EventType)
		if idx < 0 {
			continue
		}
		seen[event.EventType]++

		switch workflow {
		case WorkflowProduct:
			if idx != current+1 {
				status.Valid = false
				expected := stages[0]
				if current+1 < len(stages) {
					expected = stages[current+1]
				}
				status.Message = fmt.Sprintf(
					"existing history is out of order: found %s while expecting %s",
					event.EventType, expected,
				)
				return status, nil
			}
			current = idx
		case WorkflowCircular:
			if event.EventType == EventResidueCustody && current == 1 {
				if asBool(event.Payload["accepted"]) {
					acceptedCustody = true
				}
				status.LastEventID = event.EventID
				status.UpdatedAt = event.TimestampRFC
				continue
			}
			if event.EventType == EventUsefulOutput && current == 3 {
				status.LastEventID = event.EventID
				status.UpdatedAt = event.TimestampRFC
				continue
			}
			if event.EventType == EventReturnOrSale && current == 4 {
				status.LastEventID = event.EventID
				status.UpdatedAt = event.TimestampRFC
				continue
			}
			if idx != current+1 {
				status.Valid = false
				expected := stages[0]
				if current+1 < len(stages) {
					expected = stages[current+1]
				}
				status.Message = fmt.Sprintf(
					"existing circular history is out of order: found %s while expecting %s",
					event.EventType, expected,
				)
				return status, nil
			}
			current = idx
			if event.EventType == EventResidueCustody && asBool(event.Payload["accepted"]) {
				acceptedCustody = true
			}
			if event.EventType == EventResidueGeneration {
				status.OriginBatch = asString(event.Payload["origin_batch"])
			}
		}
		status.LastEventID = event.EventID
		status.UpdatedAt = event.TimestampRFC
	}

	if current >= 0 {
		status.CurrentStep = stages[current]
		status.CurrentLabel = stageLabel(workflow, status.CurrentStep)
		status.CurrentStepNumber = current + 1
		status.ProgressPct = round2(float64(current+1) * 100 / float64(len(stages)))
	}

	if current == len(stages)-1 {
		status.Complete = true
		status.Message = "Workflow complete."
		if workflow == WorkflowProduct {
			status.NextAllowed = []string{EventConsumerVerification}
		}
		return status, nil
	}

	if workflow == WorkflowCircular {
		switch current {
		case 1:
			if acceptedCustody {
				status.NextAllowed = []string{EventValorization}
				status.Message = "Residue accepted. Valorization is the next required step."
			} else {
				status.NextAllowed = []string{EventResidueCustody}
				status.Message = "Waiting for an accepted residue custody record before valorization."
			}
			return status, nil
		case 3:
			status.NextAllowed = []string{EventUsefulOutput, EventReturnOrSale}
			status.Message = "Additional useful outputs may be recorded, or the workflow may continue to return or sale."
			return status, nil
		case 4:
			status.NextAllowed = []string{EventReturnOrSale, EventEnvAccounting}
			status.Message = "Additional destinations may be recorded, or environmental accounting may complete the workflow."
			return status, nil
		}
	}

	status.NextAllowed = []string{stages[current+1]}
	status.Message = fmt.Sprintf("Next required step: %s.", stageLabel(workflow, stages[current+1]))
	return status, nil
}

func validateWorkflowTransition(ctx contractapi.TransactionContextInterface, eventType, subjectID string, payload map[string]interface{}) error {
	if eventType == EventCorrection || eventType == EventRewardIssued || eventType == EventReviewFlag || eventType == EventReviewResolution {
		return nil
	}

	if eventType == EventConsumerVerification {
		events, err := subjectWorkflowEvents(ctx, subjectID)
		if err != nil {
			return err
		}
		status, err := analyzeWorkflow(subjectID, events)
		if err != nil {
			return err
		}
		if !status.Exists || status.Workflow != WorkflowProduct || !status.Complete {
			return fmt.Errorf("consumer verification is allowed only after batch %s reaches distribution_retail", subjectID)
		}
		return nil
	}

	workflow, stages, managed := workflowForEvent(eventType)
	if !managed {
		return nil
	}

	if workflow == WorkflowCircular {
		if eventType != EventResidueGeneration {
			residueID := strings.TrimSpace(asString(payload["residue_id"]))
			if residueID == "" || residueID != strings.TrimSpace(subjectID) {
				return fmt.Errorf("%s requires payload residue_id to match subject_id %s", eventType, subjectID)
			}
		}
		if eventType == EventResidueGeneration {
			originBatch := strings.TrimSpace(asString(payload["origin_batch"]))
			if originBatch == "" {
				return fmt.Errorf("residue_generation requires origin_batch")
			}
			batchEvents, err := subjectWorkflowEvents(ctx, originBatch)
			if err != nil {
				return err
			}
			batchStatus, err := analyzeWorkflow(originBatch, batchEvents)
			if err != nil {
				return err
			}
			millingIndex := workflowIndex(productWorkflow, EventMilling)
			if !batchStatus.Exists || batchStatus.Workflow != WorkflowProduct || batchStatus.CurrentStepNumber < millingIndex+1 {
				return fmt.Errorf("residue %s cannot be generated before origin batch %s reaches milling", subjectID, originBatch)
			}
		}
	}

	events, err := subjectWorkflowEvents(ctx, subjectID)
	if err != nil {
		return err
	}
	status, err := analyzeWorkflow(subjectID, events)
	if err != nil {
		return err
	}
	if !status.Valid {
		return fmt.Errorf("cannot advance %s: %s", subjectID, status.Message)
	}

	if !status.Exists {
		if eventType != stages[0] {
			return fmt.Errorf("%s has not started; first required event is %s, not %s", subjectID, stages[0], eventType)
		}
		return nil
	}
	if status.Workflow != workflow {
		return fmt.Errorf("subject %s belongs to %s workflow, not %s", subjectID, status.Workflow, workflow)
	}
	if status.Complete {
		return fmt.Errorf("%s workflow for %s is already complete; %s is not allowed", workflow, subjectID, eventType)
	}
	if containsString(status.NextAllowed, eventType) {
		return nil
	}
	if status.CurrentStep == eventType {
		return fmt.Errorf("%s already has step %s; next allowed event is %s", subjectID, eventType, strings.Join(status.NextAllowed, " or "))
	}
	return fmt.Errorf(
		"workflow order violation for %s: current step is %s; next allowed event is %s; cannot submit %s",
		subjectID, status.CurrentStep, strings.Join(status.NextAllowed, " or "), eventType,
	)
}

func (c *OliveChainContract) GetSubjectStatus(ctx contractapi.TransactionContextInterface, subjectID string) (*WorkflowStatus, error) {
	events, err := subjectWorkflowEvents(ctx, subjectID)
	if err != nil {
		return nil, err
	}
	return analyzeWorkflow(subjectID, events)
}

func (c *OliveChainContract) GetWorkflowStatuses(ctx contractapi.TransactionContextInterface) ([]WorkflowStatus, error) {
	events, err := listEventsFromIndex(ctx, eventObjectType, nil, false)
	if err != nil {
		return nil, err
	}
	bySubject := map[string][]*Event{}
	for _, event := range events {
		if _, _, ok := workflowForEvent(event.EventType); !ok {
			continue
		}
		bySubject[event.SubjectID] = append(bySubject[event.SubjectID], event)
	}
	subjects := make([]string, 0, len(bySubject))
	for subjectID := range bySubject {
		subjects = append(subjects, subjectID)
	}
	sort.Strings(subjects)
	statuses := make([]WorkflowStatus, 0, len(subjects))
	for _, subjectID := range subjects {
		status, err := analyzeWorkflow(subjectID, bySubject[subjectID])
		if err != nil {
			return nil, err
		}
		statuses = append(statuses, *status)
	}
	return statuses, nil
}

func (c *OliveChainContract) GetWorkflowDefinitions(ctx contractapi.TransactionContextInterface) ([]WorkflowDefinition, error) {
	return []WorkflowDefinition{
		{Name: WorkflowProduct, Steps: append([]string{}, productWorkflow...), Repeatable: []string{EventConsumerVerification}},
		{Name: WorkflowCircular, Steps: append([]string{}, circularWorkflow...), Repeatable: []string{EventResidueCustody, EventUsefulOutput, EventReturnOrSale}},
	}, nil
}

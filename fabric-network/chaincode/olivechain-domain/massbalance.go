// SPDX-License-Identifier: Apache-2.0
package main

import (
	"fmt"
	"math"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const defaultMassBalanceTolerance = 0.05

func (c *OliveChainContract) ReconcileResidue(ctx contractapi.TransactionContextInterface, residueID string) (*Reconciliation, error) {
	events, err := c.GetEventsForSubject(ctx, residueID, false)
	if err != nil {
		return nil, err
	}
	return reconcileFromEvents(ctx, residueID, events, defaultMassBalanceTolerance)
}

func reconcileFromEvents(ctx contractapi.TransactionContextInterface, residueID string, events []*Event, tolerance float64) (*Reconciliation, error) {
	rec := &Reconciliation{ResidueID: residueID, Outputs: map[string]float64{}, Issues: []string{}}
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return nil, err
		}
		p := effective.Payload
		switch effective.EventType {
		case EventResidueGeneration:
			rec.GeneratedKg += asFloat(p["weight_kg"])
		case EventResidueCustody:
			rec.TransferredKg += asFloat(p["weight_kg"])
			if asBool(p["accepted"]) {
				rec.AcceptedKg += asFloat(p["weight_kg"])
			}
		case EventValorization:
			rec.TransformedKg += asFloat(p["input_kg"])
			rec.RejectedKg += asFloat(p["rejected_kg"])
			outputs, _ := p["outputs"].([]interface{})
			for _, raw := range outputs {
				output, _ := raw.(map[string]interface{})
				key := asString(output["output_type"])
				rec.Outputs[key] += asFloat(output["quantity"])
			}
		}
	}
	within := func(a, b float64) bool {
		max := math.Max(a, b)
		if max == 0 {
			return true
		}
		return math.Abs(a-b)/max <= tolerance
	}
	if rec.GeneratedKg == 0 {
		rec.Issues = append(rec.Issues, "no residue generation recorded")
	}
	if rec.TransferredKg != 0 && !within(rec.GeneratedKg, rec.TransferredKg) {
		rec.Issues = append(rec.Issues, fmt.Sprintf("transfer/generation mismatch: generated %vkg, transferred %vkg", rec.GeneratedKg, rec.TransferredKg))
	}
	if rec.AcceptedKg != 0 && !within(rec.TransferredKg, rec.AcceptedKg) {
		rec.Issues = append(rec.Issues, fmt.Sprintf("acceptance mismatch: transferred %vkg, accepted %vkg", rec.TransferredKg, rec.AcceptedKg))
	}
	accountedKg := rec.TransformedKg + rec.RejectedKg
	if accountedKg != 0 && !within(rec.AcceptedKg, accountedKg) {
		rec.Issues = append(rec.Issues, fmt.Sprintf(
			"transformation mismatch: accepted %vkg, transformed %vkg, rejected %vkg, accounted %vkg",
			rec.AcceptedKg,
			rec.TransformedKg,
			rec.RejectedKg,
			accountedKg,
		))
	}
	if accountedKg == 0 && rec.AcceptedKg > 0 {
		rec.Issues = append(rec.Issues, "residue accepted but no valorization recorded")
	}
	rec.Balanced = len(rec.Issues) == 0
	if rec.GeneratedKg > 0 {
		rec.RecoveryPct = round2(100 * rec.TransformedKg / rec.GeneratedKg)
	}
	return rec, nil
}

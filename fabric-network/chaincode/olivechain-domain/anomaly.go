// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const (
	plausibleOilYieldLow      = 0.05
	plausibleOilYieldHigh     = 0.30
	plausibleResidueRatioLow  = 0.20
	plausibleResidueRatioHigh = 0.90
)

func (c *OliveChainContract) ScanAnomalies(ctx contractapi.TransactionContextInterface) ([]Finding, error) {
	events, err := c.GetAllEvents(ctx, false)
	if err != nil {
		return nil, err
	}
	findings := make([]Finding, 0)
	seen := map[string]string{}
	holders := map[string]string{}
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return nil, err
		}
		p := effective.Payload
		if effective.EventType == EventMilling {
			received := asFloat(p["received_kg"])
			oilL := asFloat(p["oil_yield_l"])
			if received > 0 {
				ratio := oilL / received
				if ratio < plausibleOilYieldLow || ratio > plausibleOilYieldHigh {
					findings = append(findings, Finding{"implausible_oil_yield", effective.EventID,
						fmt.Sprintf("%v l oil from %v kg olives (ratio %.3f l/kg outside [%.2f, %.2f])", oilL, received, ratio, plausibleOilYieldLow, plausibleOilYieldHigh)})
				}
				residues, _ := p["residues_declared"].([]interface{})
				total := 0.0
				for _, raw := range residues {
					residue, _ := raw.(map[string]interface{})
					total += asFloat(residue["weight_kg"])
				}
				if total > 0 {
					residueRatio := total / received
					if residueRatio < plausibleResidueRatioLow || residueRatio > plausibleResidueRatioHigh {
						findings = append(findings, Finding{"implausible_residue_ratio", effective.EventID,
							fmt.Sprintf("%v kg residues from %v kg olives (ratio %.2f outside [%.2f, %.2f])", total, received, residueRatio, plausibleResidueRatioLow, plausibleResidueRatioHigh)})
					}
				}
			}
		}
		if effective.EventType != EventConsumerVerification && effective.EventType != EventCorrection {
			payloadBytes, _ := json.Marshal(effective.Payload)
			key := effective.EventType + "|" + effective.SubjectID + "|" + effective.ActorOrg + "|" + string(payloadBytes)
			if original, exists := seen[key]; exists {
				findings = append(findings, Finding{"duplicate_record", effective.EventID, "duplicates event " + original})
			} else {
				seen[key] = effective.EventID
			}
		}
		if effective.EventType == EventResidueCustody {
			rid := asString(p["residue_id"])
			from := asString(p["from_org"])
			to := asString(p["to_org"])
			if current, exists := holders[rid]; exists && current != from {
				findings = append(findings, Finding{"conflicting_custody", effective.EventID,
					fmt.Sprintf("%s: transfer claimed from %s but current holder is %s", rid, from, current)})
			}
			holders[rid] = to
		}
	}
	sort.SliceStable(findings, func(i, j int) bool {
		if findings[i].Rule == findings[j].Rule {
			return findings[i].SubjectEvent < findings[j].SubjectEvent
		}
		return findings[i].Rule < findings[j].Rule
	})
	return findings, nil
}

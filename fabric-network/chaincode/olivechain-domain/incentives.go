// SPDX-License-Identifier: Apache-2.0
package main

import (
	"fmt"
	"sort"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

func (c *OliveChainContract) GetDueRewards(ctx contractapi.TransactionContextInterface) ([]RewardDue, error) {
	events, err := c.GetAllEvents(ctx, false)
	if err != nil {
		return nil, err
	}
	flagged, err := openFlaggedEvents(ctx, events)
	if err != nil {
		return nil, err
	}
	due := make([]RewardDue, 0)
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return nil, err
		}
		for _, rule := range rewardRules {
			if rule.EventType != effective.EventType {
				continue
			}
			rewarded, err := alreadyRewarded(ctx, events, effective.EventID, rule.RuleID)
			if err != nil {
				return nil, err
			}
			if rewarded || flagged[effective.EventID] {
				continue
			}
			if rule.RequiresMassBalance {
				residueID := asString(effective.Payload["residue_id"])
				if residueID == "" {
					continue
				}
				rec, err := c.ReconcileResidue(ctx, residueID)
				if err != nil || !rec.Balanced {
					continue
				}
			}
			if rule.RuleID == "quality_criteria" {
				quality := asString(effective.Payload["quality_class"])
				if quality != "extra_virgin" && quality != "organic_extra_virgin" {
					continue
				}
			}
			due = append(due, RewardDue{
				Recipient: effective.ActorOrg, Amount: rule.Amount, RewardRule: rule.RuleID,
				RuleDescription: rule.Description, BasisEvents: []string{effective.EventID}, Transferable: false,
			})
		}
	}
	sort.Slice(due, func(i, j int) bool {
		if due[i].Recipient == due[j].Recipient {
			return due[i].RewardRule < due[j].RewardRule
		}
		return due[i].Recipient < due[j].Recipient
	})
	return due, nil
}

func alreadyRewarded(ctx contractapi.TransactionContextInterface, events []*Event, basisEventID, ruleID string) (bool, error) {
	for _, event := range events {
		if event.EventType != EventRewardIssued {
			continue
		}
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return false, err
		}
		if asString(effective.Payload["reward_rule"]) == ruleID && containsString(asStringSlice(effective.Payload["basis_events"]), basisEventID) {
			return true, nil
		}
	}
	return false, nil
}

func openFlaggedEvents(ctx contractapi.TransactionContextInterface, events []*Event) (map[string]bool, error) {
	flags := map[string]string{}
	resolved := map[string]bool{}
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return nil, err
		}
		switch effective.EventType {
		case EventReviewFlag:
			flags[asString(effective.Payload["subject_event"])] = effective.EventID
		case EventReviewResolution:
			resolved[asString(effective.Payload["flag_event"])] = true
		}
	}
	open := map[string]bool{}
	for subject, flagID := range flags {
		if !resolved[flagID] {
			open[subject] = true
		}
	}
	return open, nil
}

func (c *OliveChainContract) GetRewardBalances(ctx contractapi.TransactionContextInterface) (map[string]int, error) {
	events, err := c.GetEventsByType(ctx, EventRewardIssued, false)
	if err != nil {
		return nil, err
	}
	balances := map[string]int{}
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return nil, err
		}
		recipient := asString(effective.Payload["recipient"])
		balances[recipient] += int(asFloat(effective.Payload["amount"]))
	}
	return balances, nil
}

func (c *OliveChainContract) validateRewardProposal(ctx contractapi.TransactionContextInterface, payload map[string]interface{}) error {
	due, err := c.GetDueRewards(ctx)
	if err != nil {
		return err
	}
	recipient := asString(payload["recipient"])
	rule := asString(payload["reward_rule"])
	amount := int(asFloat(payload["amount"]))
	basis := asStringSlice(payload["basis_events"])
	for _, candidate := range due {
		if candidate.Recipient == recipient && candidate.RewardRule == rule && candidate.Amount == amount && len(basis) == 1 && basis[0] == candidate.BasisEvents[0] {
			return nil
		}
	}
	return fmt.Errorf("reward is not currently due under the adapted incentive rules")
}

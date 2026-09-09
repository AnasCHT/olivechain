// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const (
	walletAssetsKeyPrefix = "wallet-assets:"
	tokenTxKeyPrefix      = "wallet-token-tx:"
	tokenRewardKeyPrefix  = "wallet-token-reward:"
	ecoPerKWh             = 0.1
	verifiedTrustBase     = 50
)

func walletAssetsKey(address string) string {
	return walletAssetsKeyPrefix + strings.TrimSpace(address)
}
func tokenTxKey(address, txID string) string {
	return tokenTxKeyPrefix + strings.TrimSpace(address) + ":" + strings.TrimSpace(txID)
}
func tokenRewardKey(kind, basis string) string {
	return tokenRewardKeyPrefix + strings.TrimSpace(kind) + ":" + strings.TrimSpace(basis)
}

func ensureWalletAssets(ctx contractapi.TransactionContextInterface, address string) (*WalletAssets, error) {
	raw, err := ctx.GetStub().GetState(walletAssetsKey(address))
	if err != nil {
		return nil, err
	}
	if raw != nil {
		var assets WalletAssets
		if err := json.Unmarshal(raw, &assets); err != nil {
			return nil, err
		}
		return &assets, nil
	}
	assets := &WalletAssets{DocType: "wallet_assets", WalletAddress: address, EcoToken: 0, OliveToken: 0, TrustScore: 0}
	if err := putJSON(ctx, walletAssetsKey(address), assets); err != nil {
		return nil, err
	}
	return assets, nil
}

func initializeVerifiedTrust(ctx contractapi.TransactionContextInterface, address string) (*WalletAssets, error) {
	assets, err := ensureWalletAssets(ctx, address)
	if err != nil {
		return nil, err
	}
	if assets.TrustScore >= verifiedTrustBase {
		return assets, nil
	}
	delta := verifiedTrustBase - assets.TrustScore
	return adjustTrust(ctx, address, delta, "organization_role_verified", address, "", "trust-base:"+address)
}

func (c *OliveChainContract) GetWalletAssets(ctx contractapi.TransactionContextInterface, walletAddress string) (*WalletAssets, error) {
	if _, err := getWallet(ctx, walletAddress); err != nil {
		return nil, err
	}
	return ensureWalletAssets(ctx, walletAddress)
}

func (c *OliveChainContract) GetWalletTokenTransactions(ctx contractapi.TransactionContextInterface, walletAddress string) ([]TokenTransaction, error) {
	prefix := tokenTxKeyPrefix + strings.TrimSpace(walletAddress) + ":"
	iter, err := ctx.GetStub().GetStateByRange(prefix, prefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()
	out := make([]TokenTransaction, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var tx TokenTransaction
		if err := json.Unmarshal(row.Value, &tx); err != nil {
			return nil, err
		}
		out = append(out, tx)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Timestamp > out[j].Timestamp })
	return out, nil
}

func (c *OliveChainContract) GetTokenTransactionsForSubject(ctx contractapi.TransactionContextInterface, subjectID string) ([]TokenTransaction, error) {
	iter, err := ctx.GetStub().GetStateByRange(tokenTxKeyPrefix, tokenTxKeyPrefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()
	out := make([]TokenTransaction, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var tx TokenTransaction
		if err := json.Unmarshal(row.Value, &tx); err != nil {
			return nil, err
		}
		if tx.BasisSubject == subjectID || tx.OriginBatch == subjectID {
			out = append(out, tx)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Timestamp < out[j].Timestamp })
	return out, nil
}

func (c *OliveChainContract) GetTokenPolicy(ctx contractapi.TransactionContextInterface) (*TokenPolicy, error) {
	return &TokenPolicy{
		EcoTokenPerVerifiedKWh:       ecoPerKWh,
		OliveTokenPerMilestone:       1,
		TrustBaseVerifiedRole:        verifiedTrustBase,
		TrustPerAcceptedEvent:        1,
		TrustProductCompletionBonus:  4,
		TrustCircularCompletionBonus: 5,
		EcoTransferable:              false,
		OliveTransferable:            false,
		TrustTransferable:            false,
	}, nil
}

func applyWalletIncentives(ctx contractapi.TransactionContextInterface, event *Event) error {
	if event == nil || event.ActorWallet == "" {
		return nil
	}
	wallet, err := getWallet(ctx, event.ActorWallet)
	if err != nil || wallet.RoleStatus != "active" {
		return nil
	}

	productMilestone := map[string]bool{
		EventCultivation: true, EventHarvest: true, EventCollectionTransport: true,
		EventMilling: true, EventLabVerification: true, EventBottling: true,
		EventDistributionRetail: true,
	}
	if productMilestone[event.EventType] {
		if _, err := creditToken(ctx, event.ActorWallet, "OLIVE", 1,
			"verified_"+event.EventType, event.SubjectID, event.EventID, "", "olive:"+event.EventID); err != nil {
			return err
		}
	}

	// Every accepted operational event by a wallet-bound Fabric identity adds
	// a small reputation increment. Completion bonuses are intentionally
	// non-transferable and capped at 100.
	if event.EventType != EventCorrection && event.EventType != EventRewardIssued && event.EventType != EventReviewFlag && event.EventType != EventReviewResolution {
		if _, err := adjustTrust(ctx, event.ActorWallet, 1, "accepted_event", event.SubjectID, event.EventID, "trust-event:"+event.EventID); err != nil {
			return err
		}
	}
	if event.EventType == EventDistributionRetail {
		if _, err := adjustTrust(ctx, event.ActorWallet, 4, "product_workflow_completed", event.SubjectID, event.EventID, "trust-product:"+event.SubjectID); err != nil {
			return err
		}
	}
	if event.EventType == EventEnvAccounting {
		rec, err := cReconcileResidue(ctx, event.SubjectID)
		if err == nil && rec.Balanced {
			if _, err := adjustTrust(ctx, event.ActorWallet, 5, "verified_circular_workflow_completed", event.SubjectID, event.EventID, "trust-circular:"+event.SubjectID); err != nil {
				return err
			}
			if err := mintEcoForCompletedResidue(ctx, event.SubjectID, event.EventID); err != nil {
				return err
			}
		}
	}
	return nil
}

// Local helper avoids constructing a contract receiver merely to call the
// deterministic reconciliation function.
func cReconcileResidue(ctx contractapi.TransactionContextInterface, residueID string) (*Reconciliation, error) {
	contract := &OliveChainContract{}
	return contract.ReconcileResidue(ctx, residueID)
}

func mintEcoForCompletedResidue(ctx contractapi.TransactionContextInterface, residueID, basisEventID string) error {
	rewardKey := tokenRewardKey("eco", residueID)
	if raw, err := ctx.GetStub().GetState(rewardKey); err != nil {
		return err
	} else if raw != nil {
		return nil
	}
	events, err := (&OliveChainContract{}).GetEventsForSubject(ctx, residueID, false)
	if err != nil {
		return err
	}
	originBatch := ""
	energyKWh := 0.0
	for _, event := range events {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return err
		}
		if effective.EventType == EventResidueGeneration {
			originBatch = asString(effective.Payload["origin_batch"])
		}
		if effective.EventType == EventUsefulOutput && asString(effective.Payload["output_type"]) == "bioenergy_kwh" {
			energyKWh += asFloat(effective.Payload["quantity"])
		}
	}
	if originBatch == "" || energyKWh <= 0 {
		return nil
	}
	batchEvents, err := (&OliveChainContract{}).GetEventsForSubject(ctx, originBatch, false)
	if err != nil {
		return err
	}
	makerWallet := ""
	for _, event := range batchEvents {
		effective, err := effectiveEvent(ctx, event)
		if err != nil {
			return err
		}
		if effective.EventType == EventMilling && effective.ActorWallet != "" {
			makerWallet = effective.ActorWallet
		}
	}
	if makerWallet == "" {
		return nil
	}
	amount := math.Round((energyKWh*ecoPerKWh)*100) / 100
	if amount <= 0 {
		return nil
	}
	if _, err := creditToken(ctx, makerWallet, "ECO", amount, "verified_bioenergy_recovery", residueID, basisEventID, originBatch, "eco:"+residueID); err != nil {
		return err
	}
	return ctx.GetStub().PutState(rewardKey, []byte(makerWallet))
}

func creditToken(ctx contractapi.TransactionContextInterface, walletAddress, token string, amount float64, reason, basisSubject, basisEvent, originBatch, idempotency string) (*WalletAssets, error) {
	if amount <= 0 {
		return ensureWalletAssets(ctx, walletAddress)
	}
	rewardKey := tokenRewardKey(token, idempotency)
	if raw, err := ctx.GetStub().GetState(rewardKey); err != nil {
		return nil, err
	} else if raw != nil {
		return ensureWalletAssets(ctx, walletAddress)
	}
	assets, err := ensureWalletAssets(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	switch token {
	case "ECO":
		assets.EcoToken = round2(assets.EcoToken + amount)
	case "OLIVE":
		assets.OliveToken = round2(assets.OliveToken + amount)
	default:
		return nil, fmt.Errorf("unsupported token %q", token)
	}
	_, stamp, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	assets.UpdatedAt = stamp
	if err := putJSON(ctx, walletAssetsKey(walletAddress), assets); err != nil {
		return nil, err
	}
	tx := TokenTransaction{
		DocType: "wallet_token_tx", TokenTxID: "TOK-" + ctx.GetStub().GetTxID() + "-" + strings.ToLower(token),
		WalletAddress: walletAddress, Token: token, Amount: round2(amount), BalanceAfter: tokenBalance(assets, token),
		Reason: reason, BasisSubject: basisSubject, BasisEvent: basisEvent, OriginBatch: originBatch,
		Timestamp: stamp, FabricTxID: ctx.GetStub().GetTxID(),
	}
	if err := putJSON(ctx, tokenTxKey(walletAddress, tx.TokenTxID), tx); err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(rewardKey, []byte(tx.TokenTxID)); err != nil {
		return nil, err
	}
	return assets, nil
}

func adjustTrust(ctx contractapi.TransactionContextInterface, walletAddress string, delta int, reason, basisSubject, basisEvent, idempotency string) (*WalletAssets, error) {
	rewardKey := tokenRewardKey("TRUST", idempotency)
	if raw, err := ctx.GetStub().GetState(rewardKey); err != nil {
		return nil, err
	} else if raw != nil {
		return ensureWalletAssets(ctx, walletAddress)
	}
	assets, err := ensureWalletAssets(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	before := assets.TrustScore
	after := before + delta
	if after < 0 {
		after = 0
	}
	if after > 100 {
		after = 100
	}
	applied := after - before
	assets.TrustScore = after
	_, stamp, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	assets.UpdatedAt = stamp
	if err := putJSON(ctx, walletAssetsKey(walletAddress), assets); err != nil {
		return nil, err
	}
	tx := TokenTransaction{
		DocType: "wallet_token_tx", TokenTxID: "TOK-" + ctx.GetStub().GetTxID() + "-trust-" + fmt.Sprint(after),
		WalletAddress: walletAddress, Token: "TRUST", Amount: float64(applied), BalanceAfter: float64(after),
		Reason: reason, BasisSubject: basisSubject, BasisEvent: basisEvent,
		Timestamp: stamp, FabricTxID: ctx.GetStub().GetTxID(),
	}
	if err := putJSON(ctx, tokenTxKey(walletAddress, tx.TokenTxID), tx); err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(rewardKey, []byte(tx.TokenTxID)); err != nil {
		return nil, err
	}
	return assets, nil
}

func tokenBalance(assets *WalletAssets, token string) float64 {
	if token == "ECO" {
		return assets.EcoToken
	}
	if token == "OLIVE" {
		return assets.OliveToken
	}
	return float64(assets.TrustScore)
}

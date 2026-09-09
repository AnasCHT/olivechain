// SPDX-License-Identifier: Apache-2.0
package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

const (
	walletKeyPrefix       = "wallet:"
	walletClientKeyPrefix = "walletclient:"
	roleRequestKeyPrefix  = "wallet-role-request:"
	roleGrantKeyPrefix    = "wallet-role-grant:"
)

var publicSignupRoles = map[string]string{
	RoleFarmer:      "farmer-org",
	RoleCollector:   "courier-org",
	RoleDistributor: "courier-org",
	RoleRetailer:    "courier-org",
}

var restrictedWalletRoles = map[string]string{
	RoleMill:       "maker-org",
	RoleLaboratory: "maker-org",
	RoleBottler:    "maker-org",
	RoleProcessor:  "recycler-org",
}

func walletKey(address string) string { return walletKeyPrefix + strings.TrimSpace(address) }
func walletClientKey(clientIDHash string) string {
	return walletClientKeyPrefix + strings.TrimSpace(clientIDHash)
}
func roleRequestKey(requestID string) string {
	return roleRequestKeyPrefix + strings.TrimSpace(requestID)
}
func roleGrantKey(grantID string) string { return roleGrantKeyPrefix + strings.TrimSpace(grantID) }

func expectedWalletAddress(publicKeySPKI string) (string, error) {
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(publicKeySPKI))
	if err != nil || len(raw) < 32 {
		return "", fmt.Errorf("wallet public key must be base64-encoded SPKI DER")
	}
	digest := sha256.Sum256(raw)
	return "OLIVE-" + strings.ToUpper(hex.EncodeToString(digest[:12])), nil
}

func walletRoleOrg(role string) (string, bool) {
	if org, ok := publicSignupRoles[role]; ok {
		return org, true
	}
	if org, ok := restrictedWalletRoles[role]; ok {
		return org, true
	}
	return "", false
}

func walletRoleAllowedForOrg(role, orgID string) bool {
	expected, ok := walletRoleOrg(role)
	return ok && expected == orgID
}

func getWallet(ctx contractapi.TransactionContextInterface, address string) (*WalletIdentity, error) {
	raw, err := ctx.GetStub().GetState(walletKey(address))
	if err != nil {
		return nil, fmt.Errorf("read wallet %q: %w", address, err)
	}
	if raw == nil {
		return nil, fmt.Errorf("wallet %q does not exist", address)
	}
	var wallet WalletIdentity
	if err := json.Unmarshal(raw, &wallet); err != nil {
		return nil, fmt.Errorf("decode wallet %q: %w", address, err)
	}
	return &wallet, nil
}

func (c *OliveChainContract) RegisterWallet(ctx contractapi.TransactionContextInterface, address, publicKeySPKI, displayName string) (*WalletIdentity, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	// Registration is intentionally open to any already trusted Fabric service
	// identity. FastAPI currently submits public registrations with the static
	// consumer-portal identity; the wallet itself becomes the human identity.
	_ = caller
	address = strings.TrimSpace(address)
	displayName = strings.TrimSpace(displayName)
	if displayName == "" || len(displayName) > 120 {
		return nil, fmt.Errorf("display_name is required (max 120 characters)")
	}
	expected, err := expectedWalletAddress(publicKeySPKI)
	if err != nil {
		return nil, err
	}
	if address != expected {
		return nil, fmt.Errorf("wallet address does not match the submitted public key")
	}
	if existing, err := ctx.GetStub().GetState(walletKey(address)); err != nil {
		return nil, err
	} else if existing != nil {
		return nil, fmt.Errorf("wallet %s is already registered", address)
	}
	_, stamp, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	wallet := &WalletIdentity{
		DocType: "wallet", WalletAddress: address, PublicKeySPKI: strings.TrimSpace(publicKeySPKI),
		DisplayName: displayName, Status: "active", Role: RoleConsumer, RoleStatus: "consumer",
		CreatedAt: stamp, UpdatedAt: stamp, CreatedByMSP: caller.MSPID,
	}
	if err := putJSON(ctx, walletKey(address), wallet); err != nil {
		return nil, err
	}
	if _, err := ensureWalletAssets(ctx, address); err != nil {
		return nil, err
	}
	return wallet, nil
}

func (c *OliveChainContract) GetWallet(ctx contractapi.TransactionContextInterface, address string) (*WalletIdentity, error) {
	return getWallet(ctx, address)
}

func (c *OliveChainContract) GetWalletByClientIDHash(ctx contractapi.TransactionContextInterface, clientIDHash string) (*WalletIdentity, error) {
	addressRaw, err := ctx.GetStub().GetState(walletClientKey(clientIDHash))
	if err != nil {
		return nil, err
	}
	if addressRaw == nil {
		return nil, fmt.Errorf("no wallet is bound to client identity %s", clientIDHash)
	}
	return getWallet(ctx, string(addressRaw))
}

func (c *OliveChainContract) GetWallets(ctx contractapi.TransactionContextInterface) ([]WalletIdentity, error) {
	iter, err := ctx.GetStub().GetStateByRange(walletKeyPrefix, walletKeyPrefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()
	out := make([]WalletIdentity, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var wallet WalletIdentity
		if err := json.Unmarshal(row.Value, &wallet); err != nil {
			return nil, err
		}
		out = append(out, wallet)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].WalletAddress < out[j].WalletAddress })
	return out, nil
}

func (c *OliveChainContract) RequestWalletRole(ctx contractapi.TransactionContextInterface, walletAddress, requestedRole string) (*WalletRoleRequest, error) {
	if _, err := callerIdentity(ctx); err != nil {
		return nil, err
	}
	requestedRole = strings.TrimSpace(requestedRole)
	orgID, allowed := publicSignupRoles[requestedRole]
	if !allowed {
		return nil, fmt.Errorf("role %q cannot be requested through public sign-up", requestedRole)
	}
	wallet, err := getWallet(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	if wallet.Status != "active" {
		return nil, fmt.Errorf("wallet is not active")
	}
	if wallet.RoleStatus == "active" {
		return nil, fmt.Errorf("wallet already has active role %s", wallet.Role)
	}
	requests, err := c.GetWalletRoleRequests(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	for _, row := range requests {
		if row.Status == "pending" {
			return nil, fmt.Errorf("wallet already has pending role request %s", row.RequestID)
		}
	}
	_, stamp, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	request := &WalletRoleRequest{
		DocType: "wallet_role_request", RequestID: "WRR-" + ctx.GetStub().GetTxID(),
		WalletAddress: walletAddress, RequestedRole: requestedRole, RequestedOrgID: orgID,
		Status: "pending", RequestedAt: stamp,
	}
	if err := putJSON(ctx, roleRequestKey(request.RequestID), request); err != nil {
		return nil, err
	}
	wallet.RoleStatus = "pending"
	wallet.PendingRequestID = request.RequestID
	wallet.UpdatedAt = stamp
	if err := putJSON(ctx, walletKey(walletAddress), wallet); err != nil {
		return nil, err
	}
	return request, nil
}

func (c *OliveChainContract) GetWalletRoleRequest(ctx contractapi.TransactionContextInterface, requestID string) (*WalletRoleRequest, error) {
	raw, err := ctx.GetStub().GetState(roleRequestKey(requestID))
	if err != nil {
		return nil, err
	}
	if raw == nil {
		return nil, fmt.Errorf("role request %q does not exist", requestID)
	}
	var request WalletRoleRequest
	if err := json.Unmarshal(raw, &request); err != nil {
		return nil, err
	}
	return &request, nil
}

func (c *OliveChainContract) GetWalletRoleRequests(ctx contractapi.TransactionContextInterface, walletAddress string) ([]WalletRoleRequest, error) {
	all, err := c.listWalletRoleRequests(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]WalletRoleRequest, 0)
	for _, row := range all {
		if row.WalletAddress == walletAddress {
			out = append(out, row)
		}
	}
	return out, nil
}

func (c *OliveChainContract) GetRoleRequestsForOrg(ctx contractapi.TransactionContextInterface, orgID string) ([]WalletRoleRequest, error) {
	all, err := c.listWalletRoleRequests(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]WalletRoleRequest, 0)
	for _, row := range all {
		if row.RequestedOrgID == orgID {
			out = append(out, row)
		}
	}
	return out, nil
}

func (c *OliveChainContract) listWalletRoleRequests(ctx contractapi.TransactionContextInterface) ([]WalletRoleRequest, error) {
	iter, err := ctx.GetStub().GetStateByRange(roleRequestKeyPrefix, roleRequestKeyPrefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()
	out := make([]WalletRoleRequest, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var request WalletRoleRequest
		if err := json.Unmarshal(row.Value, &request); err != nil {
			return nil, err
		}
		out = append(out, request)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].RequestedAt > out[j].RequestedAt })
	return out, nil
}

func requireWalletOrgAdminOrBootstrap(ctx contractapi.TransactionContextInterface, caller *IdentityInfo) error {
	if err := requireRole(caller, RoleOrgAdmin); err != nil {
		return err
	}
	// Unbound orgadmin Fabric identities are kept only for bootstrap/recovery.
	// Once an orgadmin is wallet-bound, the wallet binding must still be active;
	// a revoked wallet must not be able to administer roles by using an old cert.
	if strings.TrimSpace(caller.WalletAddress) == "" {
		return nil
	}
	_, err := validateActiveWalletBinding(ctx, caller)
	return err
}

func closeOtherPendingRoleRequests(ctx contractapi.TransactionContextInterface, walletAddress, exceptRequestID, decidedByMSP, stamp string) error {
	iter, err := ctx.GetStub().GetStateByRange(roleRequestKeyPrefix, roleRequestKeyPrefix+"\uffff")
	if err != nil {
		return err
	}
	defer iter.Close()
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return err
		}
		var request WalletRoleRequest
		if err := json.Unmarshal(row.Value, &request); err != nil {
			return err
		}
		if request.WalletAddress != walletAddress || request.Status != "pending" || request.RequestID == exceptRequestID {
			continue
		}
		request.Status = "superseded"
		request.DecidedAt = stamp
		request.DecidedByMSP = decidedByMSP
		request.DecisionReason = "superseded by another approved organizational role"
		if err := putJSON(ctx, roleRequestKey(request.RequestID), &request); err != nil {
			return err
		}
	}
	return nil
}

func (c *OliveChainContract) ApproveWalletRoleRequest(ctx contractapi.TransactionContextInterface, requestID, clientIDHash, identityAlias string) (*WalletIdentity, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireWalletOrgAdminOrBootstrap(ctx, caller); err != nil {
		return nil, err
	}
	request, err := c.GetWalletRoleRequest(ctx, requestID)
	if err != nil {
		return nil, err
	}
	if request.Status != "pending" {
		return nil, fmt.Errorf("role request %s is %s", requestID, request.Status)
	}
	org, err := getOrganizationByMSP(ctx, caller.MSPID)
	if err != nil || org == nil {
		return nil, fmt.Errorf("caller MSP is not mapped to an OliveChain organization")
	}
	if org.OrgID != request.RequestedOrgID {
		return nil, fmt.Errorf("request belongs to %s, not caller organization %s", request.RequestedOrgID, org.OrgID)
	}
	wallet, err := grantWalletRole(ctx, caller, request.WalletAddress, request.RequestedRole, clientIDHash, identityAlias, "approved_request", requestID)
	if err != nil {
		return nil, err
	}
	_, stamp, _, _ := txTime(ctx)
	request.Status = "approved"
	request.DecidedAt = stamp
	request.DecidedByMSP = caller.MSPID
	request.DecisionReason = "approved"
	if err := putJSON(ctx, roleRequestKey(requestID), request); err != nil {
		return nil, err
	}
	return wallet, nil
}

func (c *OliveChainContract) RejectWalletRoleRequest(ctx contractapi.TransactionContextInterface, requestID, reason string) (*WalletRoleRequest, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireWalletOrgAdminOrBootstrap(ctx, caller); err != nil {
		return nil, err
	}
	request, err := c.GetWalletRoleRequest(ctx, requestID)
	if err != nil {
		return nil, err
	}
	if request.Status != "pending" {
		return nil, fmt.Errorf("role request %s is %s", requestID, request.Status)
	}
	org, _ := getOrganizationByMSP(ctx, caller.MSPID)
	if org == nil || org.OrgID != request.RequestedOrgID {
		return nil, fmt.Errorf("caller organization cannot decide this request")
	}
	wallet, err := getWallet(ctx, request.WalletAddress)
	if err != nil {
		return nil, err
	}
	_, stamp, _, _ := txTime(ctx)
	request.Status = "rejected"
	request.DecidedAt = stamp
	request.DecidedByMSP = caller.MSPID
	request.DecisionReason = strings.TrimSpace(reason)
	wallet.Role = RoleConsumer
	wallet.RoleStatus = "consumer"
	wallet.PendingRequestID = ""
	wallet.UpdatedAt = stamp
	if err := putJSON(ctx, roleRequestKey(requestID), request); err != nil {
		return nil, err
	}
	if err := putJSON(ctx, walletKey(wallet.WalletAddress), wallet); err != nil {
		return nil, err
	}
	return request, nil
}

// GrantWalletRole is used for restricted roles that are deliberately hidden
// from public sign-up. An organization administrator must perform the grant.
// orgadmin itself is bootstrap-only: only a privileged bootstrap Fabric identity
// (which has no olivechain.wallet attribute) can grant it.
func (c *OliveChainContract) GrantWalletRole(ctx contractapi.TransactionContextInterface, walletAddress, role, clientIDHash, identityAlias string) (*WalletIdentity, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireWalletOrgAdminOrBootstrap(ctx, caller); err != nil {
		return nil, err
	}
	return grantWalletRole(ctx, caller, walletAddress, role, clientIDHash, identityAlias, "admin_grant", "")
}

func grantWalletRole(ctx contractapi.TransactionContextInterface, caller *IdentityInfo, walletAddress, role, clientIDHash, identityAlias, source, requestID string) (*WalletIdentity, error) {
	orgID, valid := walletRoleOrg(role)
	if role == RoleOrgAdmin {
		org, err := getOrganizationByMSP(ctx, caller.MSPID)
		if err != nil || org == nil {
			return nil, fmt.Errorf("caller MSP is not mapped to an OliveChain organization")
		}
		orgID = org.OrgID
		valid = true
		if caller.WalletAddress != "" {
			return nil, fmt.Errorf("orgadmin role can only be bootstrapped by an unbound privileged Fabric identity")
		}
	}
	if !valid {
		return nil, fmt.Errorf("role %q is not a wallet-assignable role", role)
	}
	org, err := getOrganizationByMSP(ctx, caller.MSPID)
	if err != nil || org == nil {
		return nil, fmt.Errorf("caller MSP is not mapped to an OliveChain organization")
	}
	if org.OrgID != orgID {
		return nil, fmt.Errorf("role %s belongs to %s, not caller organization %s", role, orgID, org.OrgID)
	}
	if role != RoleOrgAdmin && !walletRoleAllowedForOrg(role, orgID) {
		return nil, fmt.Errorf("role %s is not valid for %s", role, orgID)
	}
	if strings.TrimSpace(clientIDHash) == "" || strings.TrimSpace(identityAlias) == "" {
		return nil, fmt.Errorf("client_id_hash and identity_alias are required")
	}
	wallet, err := getWallet(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	if wallet.Status != "active" {
		return nil, fmt.Errorf("wallet is not active")
	}
	if wallet.RoleStatus == "active" && wallet.ClientIDHash != clientIDHash {
		return nil, fmt.Errorf("wallet already has active role %s", wallet.Role)
	}
	if existing, err := ctx.GetStub().GetState(walletClientKey(clientIDHash)); err != nil {
		return nil, err
	} else if existing != nil && string(existing) != walletAddress {
		return nil, fmt.Errorf("Fabric client identity is already bound to another wallet")
	}
	_, stamp, _, err := txTime(ctx)
	if err != nil {
		return nil, err
	}
	wallet.OrgID = orgID
	wallet.MSPID = caller.MSPID
	wallet.Role = role
	wallet.RoleStatus = "active"
	wallet.IdentityAlias = identityAlias
	wallet.ClientIDHash = clientIDHash
	wallet.PendingRequestID = ""
	wallet.ApprovedByMSP = caller.MSPID
	wallet.ApprovedAt = stamp
	wallet.UpdatedAt = stamp
	if err := putJSON(ctx, walletKey(walletAddress), wallet); err != nil {
		return nil, err
	}
	if err := closeOtherPendingRoleRequests(ctx, walletAddress, requestID, caller.MSPID, stamp); err != nil {
		return nil, err
	}
	if err := ctx.GetStub().PutState(walletClientKey(clientIDHash), []byte(walletAddress)); err != nil {
		return nil, err
	}
	grant := &WalletRoleGrant{
		DocType: "wallet_role_grant", GrantID: "WRG-" + ctx.GetStub().GetTxID(),
		WalletAddress: walletAddress, OrgID: orgID, MSPID: caller.MSPID, Role: role,
		ClientIDHash: clientIDHash, IdentityAlias: identityAlias, GrantedByMSP: caller.MSPID,
		GrantedAt: stamp, Source: source, RequestID: requestID, Active: true,
	}
	if err := putJSON(ctx, roleGrantKey(grant.GrantID), grant); err != nil {
		return nil, err
	}
	if _, err := initializeVerifiedTrust(ctx, walletAddress); err != nil {
		return nil, err
	}
	return wallet, nil
}

func (c *OliveChainContract) RevokeWalletRole(ctx contractapi.TransactionContextInterface, walletAddress, reason string) (*WalletIdentity, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireWalletOrgAdminOrBootstrap(ctx, caller); err != nil {
		return nil, err
	}
	wallet, err := getWallet(ctx, walletAddress)
	if err != nil {
		return nil, err
	}
	if wallet.RoleStatus != "active" {
		return nil, fmt.Errorf("wallet has no active organizational role")
	}
	if wallet.MSPID != caller.MSPID {
		return nil, fmt.Errorf("only %s may revoke this role", wallet.MSPID)
	}
	_, stamp, _, _ := txTime(ctx)
	if wallet.ClientIDHash != "" {
		if err := ctx.GetStub().DelState(walletClientKey(wallet.ClientIDHash)); err != nil {
			return nil, err
		}
	}
	wallet.RoleStatus = "revoked"
	wallet.RevokedAt = stamp
	wallet.RevokedByMSP = caller.MSPID
	wallet.RevocationReason = strings.TrimSpace(reason)
	wallet.UpdatedAt = stamp
	if err := putJSON(ctx, walletKey(walletAddress), wallet); err != nil {
		return nil, err
	}
	return wallet, nil
}

func validateActiveWalletBinding(ctx contractapi.TransactionContextInterface, caller *IdentityInfo) (*WalletIdentity, error) {
	if strings.TrimSpace(caller.WalletAddress) == "" {
		return nil, fmt.Errorf("caller certificate is not bound to an OliveChain wallet")
	}
	wallet, err := getWallet(ctx, caller.WalletAddress)
	if err != nil {
		return nil, err
	}
	if wallet.Status != "active" || wallet.RoleStatus != "active" {
		return nil, fmt.Errorf("wallet %s has no active organizational role", wallet.WalletAddress)
	}
	if wallet.MSPID != caller.MSPID || wallet.Role != caller.Role || wallet.ClientIDHash != caller.ClientIDHash {
		return nil, fmt.Errorf("Fabric certificate does not match the active wallet binding")
	}
	return wallet, nil
}

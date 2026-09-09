// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"
)

// InitOrganizations adapts registry.py to Fabric MSP identities. It writes
// public organization names/roles only; MSP certificates remain the source of
// cryptographic identity.
func (c *OliveChainContract) InitOrganizations(ctx contractapi.TransactionContextInterface) ([]Organization, error) {
	caller, err := callerIdentity(ctx)
	if err != nil {
		return nil, err
	}
	if err := requireRole(caller, RoleOrgAdmin); err != nil {
		return nil, err
	}
	for _, org := range defaultOrganizations {
		existing, err := ctx.GetStub().GetState(orgKey(org.OrgID))
		if err != nil {
			return nil, err
		}
		if existing != nil {
			continue
		}
		org.Metadata = map[string]interface{}{"architecture": "four-peer-consortium"}
		if err := putJSON(ctx, orgKey(org.OrgID), org); err != nil {
			return nil, err
		}
		if err := ctx.GetStub().PutState(mspOrgKey(org.MSPID), []byte(org.OrgID)); err != nil {
			return nil, err
		}
	}
	return c.GetOrganizations(ctx)
}

func getOrganizationByMSP(ctx contractapi.TransactionContextInterface, mspID string) (*Organization, error) {
	orgID, err := ctx.GetStub().GetState(mspOrgKey(mspID))
	if err != nil {
		return nil, err
	}
	if orgID == nil {
		return nil, nil
	}
	raw, err := ctx.GetStub().GetState(orgKey(string(orgID)))
	if err != nil || raw == nil {
		return nil, err
	}
	var org Organization
	if err := json.Unmarshal(raw, &org); err != nil {
		return nil, err
	}
	return &org, nil
}

func (c *OliveChainContract) GetOrganization(ctx contractapi.TransactionContextInterface, orgID string) (*Organization, error) {
	raw, err := ctx.GetStub().GetState(orgKey(orgID))
	if err != nil {
		return nil, err
	}
	if raw == nil {
		return nil, fmt.Errorf("organization %q does not exist", orgID)
	}
	var org Organization
	if err := json.Unmarshal(raw, &org); err != nil {
		return nil, err
	}
	return &org, nil
}

func (c *OliveChainContract) GetOrganizations(ctx contractapi.TransactionContextInterface) ([]Organization, error) {
	iter, err := ctx.GetStub().GetStateByRange(orgKeyPrefix, orgKeyPrefix+"\uffff")
	if err != nil {
		return nil, err
	}
	defer iter.Close()
	out := make([]Organization, 0)
	for iter.HasNext() {
		row, err := iter.Next()
		if err != nil {
			return nil, err
		}
		var org Organization
		if err := json.Unmarshal(row.Value, &org); err != nil {
			return nil, err
		}
		out = append(out, org)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].OrgID < out[j].OrgID })
	return out, nil
}

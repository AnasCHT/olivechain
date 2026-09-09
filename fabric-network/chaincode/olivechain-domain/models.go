// SPDX-License-Identifier: Apache-2.0
package main

// This file is the Fabric adaptation of olivechain/models.py. Event names,
// roles, permission rules and required fields intentionally remain aligned
// with the existing application model.

const (
	RoleFarmer      = "farmer"
	RoleCollector   = "collector"
	RoleMill        = "mill"
	RoleLaboratory  = "laboratory"
	RoleBottler     = "bottler"
	RoleDistributor = "distributor"
	RoleRetailer    = "retailer"
	RoleProcessor   = "processor"
	RoleAuthority   = "authority"
	RoleConsumer    = "consumer"
	RoleOrgAdmin    = "orgadmin"
)

const (
	EventCultivation          = "cultivation"
	EventHarvest              = "harvest"
	EventCollectionTransport  = "collection_transport"
	EventMilling              = "milling"
	EventLabVerification      = "lab_verification"
	EventBottling             = "bottling"
	EventDistributionRetail   = "distribution_retail"
	EventConsumerVerification = "consumer_verification"
	EventResidueGeneration    = "residue_generation"
	EventResidueCustody       = "residue_custody"
	EventValorization         = "valorization"
	EventUsefulOutput         = "useful_output"
	EventReturnOrSale         = "return_or_sale"
	EventEnvAccounting        = "env_accounting"
	EventCorrection           = "correction"
	EventRewardIssued         = "reward_issued"
	EventReviewFlag           = "review_flag"
	EventReviewResolution     = "review_resolution"
)

var allEventTypes = []string{
	EventCultivation, EventHarvest, EventCollectionTransport, EventMilling,
	EventLabVerification, EventBottling, EventDistributionRetail,
	EventConsumerVerification, EventResidueGeneration, EventResidueCustody,
	EventValorization, EventUsefulOutput, EventReturnOrSale, EventEnvAccounting,
	EventCorrection, EventRewardIssued, EventReviewFlag, EventReviewResolution,
}

var permissions = map[string]map[string]bool{
	EventCultivation:          {RoleFarmer: true},
	EventHarvest:              {RoleFarmer: true},
	EventCollectionTransport:  {RoleCollector: true},
	EventMilling:              {RoleMill: true},
	EventLabVerification:      {RoleLaboratory: true},
	EventBottling:             {RoleBottler: true},
	EventDistributionRetail:   {RoleDistributor: true, RoleRetailer: true},
	EventConsumerVerification: {RoleConsumer: true, RoleRetailer: true},
	EventResidueGeneration:    {RoleMill: true},
	EventResidueCustody:       {RoleCollector: true, RoleProcessor: true},
	EventValorization:         {RoleProcessor: true},
	EventUsefulOutput:         {RoleProcessor: true},
	EventReturnOrSale:         {RoleProcessor: true, RoleDistributor: true},
	EventEnvAccounting:        {RoleAuthority: true, RoleProcessor: true},
	EventCorrection: {
		RoleFarmer: true, RoleCollector: true, RoleMill: true,
		RoleLaboratory: true, RoleBottler: true, RoleDistributor: true,
		RoleRetailer: true, RoleProcessor: true, RoleConsumer: true,
		RoleAuthority: true,
	},
	EventRewardIssued:     {RoleAuthority: true},
	EventReviewFlag:       {RoleAuthority: true},
	EventReviewResolution: {RoleAuthority: true},
}

var requiredFields = map[string][]string{
	EventCultivation:          {"farm_id", "plot_id", "cultivar", "practices"},
	EventHarvest:              {"date", "quantity_kg", "method", "location"},
	EventCollectionTransport:  {"from_org", "to_org", "weight_kg", "container_ids"},
	EventMilling:              {"received_kg", "extraction_method", "temperature_c", "oil_yield_l", "residues_declared"},
	EventLabVerification:      {"quality_class", "results"},
	EventBottling:             {"lot_id", "bottle_count", "fill_date", "label_claims"},
	EventDistributionRetail:   {"from_org", "to_org", "destination"},
	EventConsumerVerification: {"channel"},
	EventResidueGeneration:    {"residue_type", "weight_kg", "moisture_pct", "origin_batch"},
	EventResidueCustody:       {"residue_id", "weight_kg", "measurement_method", "from_org", "to_org", "accepted"},
	EventValorization:         {"residue_id", "input_kg", "method", "outputs", "rejected_kg"},
	EventUsefulOutput:         {"residue_id", "output_type", "quantity", "unit"},
	EventReturnOrSale:         {"residue_id", "output_type", "quantity", "unit", "destination"},
	EventEnvAccounting:        {"residue_id", "recovery_pct", "avoided_disposal_kg"},
	EventCorrection:           {"supersedes_event", "reason", "corrected_payload"},
	EventRewardIssued:         {"recipient", "amount", "reward_rule", "basis_events"},
	EventReviewFlag:           {"subject_event", "rule", "detail"},
	EventReviewResolution:     {"flag_event", "decision", "rationale"},
}

var mspAllowedRoles = map[string]map[string]bool{
	"FarmerOrgMSP": {
		RoleFarmer: true, RoleOrgAdmin: true,
	},
	"MakerOrgMSP": {
		RoleMill: true, RoleLaboratory: true, RoleBottler: true, RoleOrgAdmin: true,
	},
	"CourierOrgMSP": {
		RoleCollector: true, RoleDistributor: true, RoleRetailer: true,
		RoleConsumer: true, RoleOrgAdmin: true,
	},
	"RecyclerOrgMSP": {
		RoleProcessor: true, RoleOrgAdmin: true,
	},
}

var defaultOrganizations = []Organization{
	{DocType: "organization", OrgID: "farmer-org", Name: "Farmer Cooperative", MSPID: "FarmerOrgMSP", Roles: []string{RoleFarmer}},
	{DocType: "organization", OrgID: "maker-org", Name: "Olive Mill", MSPID: "MakerOrgMSP", Roles: []string{RoleMill, RoleLaboratory, RoleBottler}},
	{DocType: "organization", OrgID: "courier-org", Name: "Green Logistics", MSPID: "CourierOrgMSP", Roles: []string{RoleCollector, RoleDistributor, RoleRetailer, RoleConsumer}},
	{DocType: "organization", OrgID: "recycler-org", Name: "BioEnergy Recovery", MSPID: "RecyclerOrgMSP", Roles: []string{RoleProcessor}},
}

var residueTypes = map[string]bool{
	"pomace": true, "alpeorujo": true, "stones": true, "leaves": true,
	"pruning": true, "wastewater": true,
}

var outputTypes = map[string]bool{
	"bioenergy_kwh": true, "compost_kg": true, "biochar_kg": true,
	"polyphenols_g": true, "fertilizer_kg": true, "feedstock_kg": true,
	"adsorbent_kg": true,
}

type RewardRule struct {
	RuleID              string `json:"rule_id"`
	Description         string `json:"description"`
	EventType           string `json:"event_type"`
	Amount              int    `json:"amount"`
	RequiresMassBalance bool   `json:"requires_mass_balance"`
}

var rewardRules = []RewardRule{
	{"residue_delivery", "delivering a measured residue quantity to an authorized processor", EventResidueCustody, 10, false},
	{"quality_criteria", "meeting validated quality or sustainability criteria", EventLabVerification, 15, false},
	{"soil_return", "returning recovered compost, biochar, or fertilizer to agricultural use", EventReturnOrSale, 20, true},
	{"verified_recovery", "producing independently verified renewable energy or recovered material", EventUsefulOutput, 25, true},
	{"prompt_records", "completing reliable records promptly", EventMilling, 5, false},
	{"circular_participation", "participating in packaging return, verified feedback, or other circular activities", EventConsumerVerification, 1, false},
}

// SPDX-License-Identifier: Apache-2.0
package main

type EvidenceRef struct {
	Name   string `json:"name"`
	SHA256 string `json:"sha256"`
	URI    string `json:"uri"`
}

type Event struct {
	DocType        string                 `json:"docType"`
	EventID        string                 `json:"event_id"`
	EventType      string                 `json:"event_type"`
	SubjectID      string                 `json:"subject_id"`
	ActorOrg       string                 `json:"actor_org"`
	ActorMSP       string                 `json:"actor_msp"`
	ActorRole      string                 `json:"actor_role"`
	ActorWallet    string                 `json:"actor_wallet"`
	ClientIDHash   string                 `json:"client_id_hash"`
	Timestamp      float64                `json:"timestamp"`
	TimestampRFC   string                 `json:"timestamp_rfc3339"`
	Payload        map[string]interface{} `json:"payload"`
	Evidence       []EvidenceRef          `json:"evidence"`
	FabricTxID     string                 `json:"fabric_tx_id"`
	EventHash      string                 `json:"event_hash"`
	SignedByFabric bool                   `json:"signed_by_fabric"`
	SupersededBy   string                 `json:"superseded_by"`
}

type Organization struct {
	DocType  string                 `json:"docType"`
	OrgID    string                 `json:"org_id"`
	Name     string                 `json:"name"`
	MSPID    string                 `json:"msp_id"`
	Roles    []string               `json:"roles"`
	Metadata map[string]interface{} `json:"metadata"`
}

type IdentityInfo struct {
	MSPID         string `json:"msp_id"`
	Role          string `json:"role"`
	WalletAddress string `json:"wallet_address"`
	ClientIDHash  string `json:"client_id_hash"`
	OrgID         string `json:"org_id"`
}

type SchemaEntry struct {
	EventType      string   `json:"event_type"`
	AllowedRoles   []string `json:"allowed_roles"`
	RequiredFields []string `json:"required_fields"`
}

type ContractInfo struct {
	Name                string `json:"name"`
	Version             string `json:"version"`
	SourceModel         string `json:"source_model"`
	IdentityModel       string `json:"identity_model"`
	GovernanceThreshold int    `json:"governance_threshold"`
}

type Reconciliation struct {
	ResidueID     string             `json:"residue_id"`
	GeneratedKg   float64            `json:"generated_kg"`
	TransferredKg float64            `json:"transferred_kg"`
	AcceptedKg    float64            `json:"accepted_kg"`
	TransformedKg float64            `json:"transformed_kg"`
	RejectedKg    float64            `json:"rejected_kg"`
	Outputs       map[string]float64 `json:"outputs"`
	Issues        []string           `json:"issues"`
	Balanced      bool               `json:"balanced"`
	RecoveryPct   float64            `json:"recovery_pct"`
}

type Finding struct {
	Rule         string `json:"rule"`
	SubjectEvent string `json:"subject_event"`
	Detail       string `json:"detail"`
}

type RewardDue struct {
	Recipient       string   `json:"recipient"`
	Amount          int      `json:"amount"`
	RewardRule      string   `json:"reward_rule"`
	RuleDescription string   `json:"rule_description"`
	BasisEvents     []string `json:"basis_events"`
	Transferable    bool     `json:"transferable"`
}

type GovernanceApproval struct {
	MSPID        string `json:"msp_id"`
	ClientIDHash string `json:"client_id_hash"`
	ApprovedAt   string `json:"approved_at"`
}

type GovernanceProposal struct {
	DocType       string                 `json:"docType"`
	ProposalID    string                 `json:"proposal_id"`
	EventType     string                 `json:"event_type"`
	SubjectID     string                 `json:"subject_id"`
	Payload       map[string]interface{} `json:"payload"`
	Evidence      []EvidenceRef          `json:"evidence"`
	ProposedByMSP string                 `json:"proposed_by_msp"`
	CreatedAt     string                 `json:"created_at"`
	Approvals     []GovernanceApproval   `json:"approvals"`
	Finalized     bool                   `json:"finalized"`
	FinalEventID  string                 `json:"final_event_id"`
}

type SellableProduct struct {
	BatchID       string                 `json:"batch_id"`
	LotID         string                 `json:"lot_id"`
	BottleCount   float64                `json:"bottle_count"`
	FillDate      string                 `json:"fill_date"`
	LabelClaims   interface{}            `json:"label_claims"`
	QualityClass  string                 `json:"quality_class"`
	Destination   string                 `json:"destination"`
	CurrentHolder string                 `json:"current_holder"`
	Details       map[string]interface{} `json:"details"`
}

type WorkflowStatus struct {
	DocType           string   `json:"docType"`
	SubjectID         string   `json:"subject_id"`
	Workflow          string   `json:"workflow"`
	Exists            bool     `json:"exists"`
	CurrentStep       string   `json:"current_step"`
	CurrentLabel      string   `json:"current_label"`
	CurrentStepNumber int      `json:"current_step_number"`
	TotalSteps        int      `json:"total_steps"`
	ProgressPct       float64  `json:"progress_pct"`
	NextAllowed       []string `json:"next_allowed"`
	Complete          bool     `json:"complete"`
	Valid             bool     `json:"valid"`
	Message           string   `json:"message"`
	LastEventID       string   `json:"last_event_id"`
	UpdatedAt         string   `json:"updated_at"`
	OriginBatch       string   `json:"origin_batch"`
}

type WorkflowDefinition struct {
	Name       string   `json:"name"`
	Steps      []string `json:"steps"`
	Repeatable []string `json:"repeatable"`
}

// WalletIdentity is the user-level identity registry. Fabric MSP remains the
// organization-level authority; the wallet key authenticates the human user.
type WalletIdentity struct {
	DocType          string `json:"docType"`
	WalletAddress    string `json:"wallet_address"`
	PublicKeySPKI    string `json:"public_key_spki"`
	DisplayName      string `json:"display_name"`
	Status           string `json:"status"`
	OrgID            string `json:"org_id"`
	MSPID            string `json:"msp_id"`
	Role             string `json:"role"`
	RoleStatus       string `json:"role_status"`
	IdentityAlias    string `json:"identity_alias"`
	ClientIDHash     string `json:"client_id_hash"`
	PendingRequestID string `json:"pending_request_id"`
	CreatedAt        string `json:"created_at"`
	UpdatedAt        string `json:"updated_at"`
	CreatedByMSP     string `json:"created_by_msp"`
	ApprovedByMSP    string `json:"approved_by_msp"`
	ApprovedAt       string `json:"approved_at"`
	RevokedByMSP     string `json:"revoked_by_msp"`
	RevokedAt        string `json:"revoked_at"`
	RevocationReason string `json:"revocation_reason"`
}

type WalletRoleRequest struct {
	DocType        string `json:"docType"`
	RequestID      string `json:"request_id"`
	WalletAddress  string `json:"wallet_address"`
	RequestedRole  string `json:"requested_role"`
	RequestedOrgID string `json:"requested_org_id"`
	Status         string `json:"status"`
	RequestedAt    string `json:"requested_at"`
	DecidedAt      string `json:"decided_at"`
	DecidedByMSP   string `json:"decided_by_msp"`
	DecisionReason string `json:"decision_reason"`
}

type WalletRoleGrant struct {
	DocType       string `json:"docType"`
	GrantID       string `json:"grant_id"`
	WalletAddress string `json:"wallet_address"`
	OrgID         string `json:"org_id"`
	MSPID         string `json:"msp_id"`
	Role          string `json:"role"`
	ClientIDHash  string `json:"client_id_hash"`
	IdentityAlias string `json:"identity_alias"`
	GrantedByMSP  string `json:"granted_by_msp"`
	GrantedAt     string `json:"granted_at"`
	Source        string `json:"source"`
	RequestID     string `json:"request_id"`
	Active        bool   `json:"active"`
}

type WalletAssets struct {
	DocType       string  `json:"docType"`
	WalletAddress string  `json:"wallet_address"`
	EcoToken      float64 `json:"eco_token"`
	OliveToken    float64 `json:"olive_token"`
	TrustScore    int     `json:"trust_score"`
	UpdatedAt     string  `json:"updated_at"`
}

type TokenTransaction struct {
	DocType       string  `json:"docType"`
	TokenTxID     string  `json:"token_tx_id"`
	WalletAddress string  `json:"wallet_address"`
	Token         string  `json:"token"`
	Amount        float64 `json:"amount"`
	BalanceAfter  float64 `json:"balance_after"`
	Reason        string  `json:"reason"`
	BasisSubject  string  `json:"basis_subject"`
	BasisEvent    string  `json:"basis_event"`
	OriginBatch   string  `json:"origin_batch"`
	Timestamp     string  `json:"timestamp"`
	FabricTxID    string  `json:"fabric_tx_id"`
}

type TokenPolicy struct {
	EcoTokenPerVerifiedKWh       float64 `json:"eco_token_per_verified_kwh"`
	OliveTokenPerMilestone       float64 `json:"olive_token_per_milestone"`
	TrustBaseVerifiedRole        int     `json:"trust_base_verified_role"`
	TrustPerAcceptedEvent        int     `json:"trust_per_accepted_event"`
	TrustProductCompletionBonus  int     `json:"trust_product_completion_bonus"`
	TrustCircularCompletionBonus int     `json:"trust_circular_completion_bonus"`
	EcoTransferable              bool    `json:"eco_transferable"`
	OliveTransferable            bool    `json:"olive_transferable"`
	TrustTransferable            bool    `json:"trust_transferable"`
}

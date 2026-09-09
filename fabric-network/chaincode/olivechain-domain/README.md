# OliveChain Fabric domain adapter — 0.2.0

This is **not a new business model**. It is a Fabric adaptation of the existing
OliveChain Python modules:

| Existing application source | Fabric adaptation |
|---|---|
| `olivechain/models.py` | `models.go`: same roles, 18 event types, permission matrix and required fields |
| `olivechain/registry.py` | `registry.go`: organization metadata keyed to Fabric MSP IDs |
| `olivechain/ledger.py` | `contract.go` + `helpers.go`: append, queries, corrections and effective payloads |
| `olivechain/massbalance.py` | `massbalance.go`: same 5% default and reconciliation gates |
| `olivechain/incentives.py` | `incentives.go`: same reward catalogue, idempotency, review and mass-balance gates |
| `olivechain/anomaly.py` | `anomaly.go`: same yield, residue-ratio, duplicate and custody checks |
| `olivechain/passport.py` | remains in FastAPI; it will read Fabric events through the later adapter |
| PDF, QR, VC, translations, evidence files | remain in the application layer |

## Architecture-specific adaptations

1. Fabric transaction certificates replace the local Ed25519 organization
   signature for ledger authorization. Each client certificate must contain
   `olivechain.role`.
2. Fabric ordering and block hashes replace the old single-process `prev_hash`
   head, avoiding concurrency conflicts across four machines.
3. Former `authority` events are created only after approvals from three
   distinct business MSPs through `ProposeGovernanceEvent`,
   `ApproveGovernanceProposal`, and `FinalizeGovernanceProposal`.
4. Event documents are JSON and include CouchDB indexes, while composite-key
   indexes make deterministic subject/type/actor queries available on every peer.
5. The original seller catalogue requirement is exposed as
   `GetSellableProducts` once a batch has a distribution/retail event.

## Main transactions

- `InitOrganizations`
- `WhoAmI`
- `GetSchema`
- `SubmitEvent`
- `CorrectEvent`
- `GetEvent`, `GetEffectiveEvent`
- `GetAllEvents`, `GetEventsForSubject`, `GetEventsByType`, `GetEventsByActor`
- `ReconcileResidue`
- `ScanAnomalies`
- `GetDueRewards`, `GetRewardBalances`
- `ProposeGovernanceEvent`, `ApproveGovernanceProposal`, `FinalizeGovernanceProposal`
- `GetGovernanceProposal`
- `GetSellableProducts`

## Deliberately outside chaincode

The dashboard, actor portal, consumer verification UI, passports, PDF signing,
QR labels, localization, W3C credentials, off-chain evidence storage, backup
and HTTP compatibility remain in the current FastAPI application. A later
`FabricLedgerAdapter` will make those features consume these transactions
without changing their visible behavior.

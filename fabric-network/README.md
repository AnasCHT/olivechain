# OliveChain multi-machine Fabric network

This directory is the first decentralization increment. It adds a Hyperledger
Fabric network beside the existing Python application without changing the
current dashboard, portal, passport, reward, evidence or audit behavior.

## Target topology

| Machine | Peer organization | Peer | Ordering organization | Orderer |
|---|---|---|---|---|
| machine1 | FarmerOrgMSP | peer0.farmer.olivechain.local | OrdererOrg1MSP | orderer1.ordererorg1.olivechain.local |
| machine2 | MakerOrgMSP | peer0.maker.olivechain.local | OrdererOrg2MSP | orderer2.ordererorg2.olivechain.local |
| machine3 | CourierOrgMSP | peer0.courier.olivechain.local | OrdererOrg3MSP | orderer3.ordererorg3.olivechain.local |
| machine4 | RecyclerOrgMSP | peer0.recycler.olivechain.local | — | — |

Each peer has its own CouchDB. The three orderers form one Raft consenter set,
but each orderer belongs to a distinct ordering organization and MSP.

## Security model of this scaffold

- Each organization runs and enrolls against its own local Fabric CA.
- Private keys remain under `fabric-network/runtime/<machine>/crypto` on the
  machine that owns them.
- Only public MSP material and orderer TLS certificates are exchanged.
- The generated channel block contains all four peer organizations and all
  three ordering organizations.
- CouchDB has no public host port and is reachable only by its local peer.
- Fabric node traffic and the orderer administration endpoint use TLS.

This is a development/academic deployment scaffold. Before an Internet-facing
production deployment, move secrets to a secret manager, firewall all ports,
use CA database persistence and backups, use real DNS certificates where
appropriate, and consider HSM-backed CA and node keys.

## Pinned versions

The initial scaffold pins:

- Hyperledger Fabric 2.5.16
- Fabric CA 1.5.22
- CouchDB 3.4.2

Edit `versions.env` only through a coordinated consortium upgrade.

## Repository layout

```text
fabric-network/
├── configtx/configtx.yaml        channel and Raft configuration
├── machines/machine*/            per-machine Docker Compose definitions
├── scripts/                      bootstrap, enrollment, exchange and join tools
├── runtime/                      local generated keys and node data (ignored)
├── public-artifacts/             public MSP exchange area (ignored)
└── channel-artifacts/            generated olivechannel block (ignored)
```

## Required host ports

Expose only the peer and orderer transport ports between the four machines. The CA and administration ports are bound to localhost by the supplied Compose files:

| Port | Purpose | Machines |
|---:|---|---|
| 7050/tcp | Raft/orderer broadcast and deliver | machine1–machine3 |
| 7051/tcp | Peer gateway, endorsement and gossip | all four |
| 7054/tcp | Business-organization CA during enrollment | localhost only |
| 8054/tcp | Ordering-organization CA during enrollment | localhost only on machine1–machine3 |
| 7053/tcp | Orderer admin API | bind locally or tightly firewall |
| 9443/tcp | Peer operations/metrics | bind locally or tightly firewall |
| 9444/tcp | Orderer operations/metrics | bind locally or tightly firewall |

CouchDB port 5984 is not published.

## Deployment sequence

The same repository copy must exist on all four machines.

### 1. Configure hostnames and machine environment

On every machine, add the final addresses from `hosts.example` to `/etc/hosts`
or configure equivalent DNS records.

Then create the local environment file:

```bash
cd fabric-network/machines/machine1   # select the local machine number
cp .env.example .env
chmod 600 .env
# edit all IP addresses and replace every example secret; keep values shell/.env compatible
```

Repeat with `machine2`, `machine3`, and `machine4` on their respective hosts.

### 2. Install the pinned Fabric tools

Run on every machine:

```bash
./fabric-network/scripts/install-tools.sh
export PATH="$PWD/fabric-network/bin:$PATH"
```

### 3. Start local CA services and create local identities

Run the matching commands on each machine:

```bash
./fabric-network/scripts/start-cas.sh machine1
./fabric-network/scripts/enroll-machine.sh machine1
```

Use the corresponding machine number on the other hosts. The enrollment script
creates the peer/orderer node identities, TLS identities, organization admins,
application client identity, and OSN administration identity where applicable.

### 4. Export only public organization material

On each machine:

```bash
./fabric-network/scripts/export-public.sh machine1
```

This creates `fabric-network/public-artifacts/outbox/machine1-public.tar.gz`.
Exchange the four archives using a secure file-transfer method. No private key
is included.

### 5. Build the shared consortium package on machine1

Copy all four public archives into:

```text
fabric-network/public-artifacts/inbox/
```

Then run:

```bash
./fabric-network/scripts/import-public.sh
./fabric-network/scripts/generate-channel.sh
./fabric-network/scripts/package-consortium.sh
```

The result is:

```text
fabric-network/public-artifacts/outbox/olivechain-consortium.tar.gz
```

It contains the public MSPs and the `olivechannel` genesis block. Copy it to all
four machines and import it there:

```bash
./fabric-network/scripts/import-consortium.sh /path/to/olivechain-consortium.tar.gz
```

### 6. Start local peer/orderer nodes

On each machine:

```bash
./fabric-network/scripts/start-node.sh machine1
```

Machine4 starts only its peer and CouchDB.

### 7. Join orderers and peers to `olivechannel`

On machine1–machine3:

```bash
./fabric-network/scripts/join-orderer.sh machine1
```

On all four machines:

```bash
./fabric-network/scripts/join-peer.sh machine1
```

Use the local machine number in each command.

### 8. Verify

```bash
./fabric-network/scripts/status.sh machine1
```

The first network milestone is reached when:

- all three orderers report `olivechannel` as active;
- all four peers return channel information for `olivechannel`;
- the four peers converge on the same block height.

## Application compatibility boundary

No existing application file is replaced in this increment. The current local
`olivechain.ledger.Ledger` remains active until the network is validated.
The next increment will add a ledger-backend interface and a Fabric adapter so
existing API routes and frontend pages keep the same behavior while writes and
queries move to chaincode.

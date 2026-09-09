import http from 'node:http';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { TextDecoder } from 'node:util';

import * as grpc from '@grpc/grpc-js';
import { connect, signers } from '@hyperledger/fabric-gateway';

const decoder = new TextDecoder();
const port = Number(process.env.OLIVECHAIN_AGENT_PORT ?? '9080');
const host = process.env.OLIVECHAIN_AGENT_BIND ?? '127.0.0.1';
const token = process.env.OLIVECHAIN_AGENT_TOKEN ?? '';
const channelName = process.env.FABRIC_CHANNEL_NAME ?? 'olivechannel';
const chaincodeName = process.env.FABRIC_CHAINCODE_NAME ?? 'olivechain';
const peerEndpoint = process.env.FABRIC_PEER_ENDPOINT ?? 'localhost:7051';
const peerHostAlias = required('FABRIC_PEER_HOST_ALIAS');
const mspId = required('FABRIC_MSP_ID');
const tlsCertPath = required('FABRIC_TLS_CERT_PATH');
const identityRoot = required('FABRIC_IDENTITY_ROOT');
const staticIdentityMap = parseJsonEnv('FABRIC_IDENTITY_MAP');
const dynamicIdentityFile = required('FABRIC_DYNAMIC_IDENTITY_FILE');
const identityAdminScript = required('FABRIC_IDENTITY_ADMIN_SCRIPT');
const machineName = required('OLIVECHAIN_MACHINE');
const maxBodyBytes = Number(process.env.OLIVECHAIN_AGENT_MAX_BODY_BYTES ?? 1024 * 1024);

if (!token) throw new Error('OLIVECHAIN_AGENT_TOKEN is required');

const evaluateAllowlist = new Set([
  'GetContractInfo', 'WhoAmI', 'GetSchema', 'GetOrganization', 'GetOrganizations',
  'GetEvent', 'GetEffectiveEvent', 'GetAllEvents', 'GetEventsForSubject',
  'GetEventsByType', 'GetEventsByActor', 'GetSellableProducts', 'ReconcileResidue',
  'ScanAnomalies', 'GetDueRewards', 'GetRewardBalances', 'GetGovernanceProposal',
  'GetSubjectStatus', 'GetWorkflowStatuses', 'GetWorkflowDefinitions',
  'GetWallet', 'GetWalletByClientIDHash', 'GetWallets', 'GetWalletRoleRequest',
  'GetWalletRoleRequests', 'GetRoleRequestsForOrg', 'GetWalletAssets',
  'GetWalletTokenTransactions', 'GetTokenTransactionsForSubject', 'GetTokenPolicy'
]);
const submitAllowlist = new Set([
  'SubmitEvent', 'CorrectEvent', 'InitOrganizations', 'ProposeGovernanceEvent',
  'ApproveGovernanceProposal', 'FinalizeGovernanceProposal', 'RegisterWallet',
  'RequestWalletRole', 'ApproveWalletRoleRequest', 'RejectWalletRoleRequest',
  'GrantWalletRole', 'RevokeWalletRole'
]);

const sessions = new Map();

function required(name) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function parseJsonEnv(name) {
  const raw = required(name);
  try {
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('must be an object');
    }
    return value;
  } catch (error) {
    throw new Error(`${name} is not valid JSON: ${error.message}`);
  }
}

function loadDynamicIdentities() {
  try {
    const value = JSON.parse(fs.readFileSync(dynamicIdentityFile, 'utf8'));
    return value?.identities && typeof value.identities === 'object'
      ? value.identities : {};
  } catch (error) {
    if (error.code === 'ENOENT') return {};
    throw new Error(`cannot read dynamic identities: ${error.message}`);
  }
}

function publicDynamicIdentities() {
  return Object.values(loadDynamicIdentities()).map((row) => ({
    identity_alias: row.identity_alias,
    username: row.username,
    display_name: row.display_name,
    role: row.role,
    msp_id: row.msp_id,
    wallet_address: row.wallet_address ?? '',
    active: row.active !== false,
    created_at: row.created_at,
    updated_at: row.updated_at
  }));
}

function secureEquals(expected, actual) {
  const left = Buffer.from(expected);
  const right = Buffer.from(actual);
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function authorized(req) {
  const value = req.headers.authorization ?? '';
  const supplied = value.startsWith('Bearer ') ? value.slice(7) : '';
  return secureEquals(token, supplied);
}

function firstFile(directory) {
  const names = fs.readdirSync(directory).filter((name) => !name.startsWith('.')).sort();
  if (names.length === 0) throw new Error(`no files found in ${directory}`);
  return path.join(directory, names[0]);
}

function identityDirectory(alias) {
  const staticRelative = staticIdentityMap[alias];
  if (typeof staticRelative === 'string' && staticRelative) {
    return path.isAbsolute(staticRelative)
      ? staticRelative : path.join(identityRoot, staticRelative);
  }
  const row = loadDynamicIdentities()[alias];
  if (!row) throw new Error(`identity alias ${alias} is not configured on this agent`);
  if (row.active === false) throw new Error(`identity alias ${alias} is disabled`);
  const relative = row.relative_dir;
  if (!relative || typeof relative !== 'string') {
    throw new Error(`identity alias ${alias} has no MSP directory`);
  }
  return path.isAbsolute(relative) ? relative : path.join(identityRoot, relative);
}

function closeSession(alias) {
  const session = sessions.get(alias);
  if (!session) return;
  try { session.gateway.close(); } catch {}
  try { session.client.close(); } catch {}
  sessions.delete(alias);
}

function getSession(alias) {
  const root = identityDirectory(alias); // re-check active status on every request
  const cached = sessions.get(alias);
  if (cached) return cached;

  const certificate = fs.readFileSync(firstFile(path.join(root, 'msp', 'signcerts')));
  const privateKeyPem = fs.readFileSync(firstFile(path.join(root, 'msp', 'keystore')));
  const privateKey = crypto.createPrivateKey(privateKeyPem);
  const signer = signers.newPrivateKeySigner(privateKey);
  const tlsRootCert = fs.readFileSync(tlsCertPath);

  const client = new grpc.Client(
    peerEndpoint,
    grpc.credentials.createSsl(tlsRootCert),
    {
      'grpc.ssl_target_name_override': peerHostAlias,
      'grpc.default_authority': peerHostAlias,
      'grpc.keepalive_time_ms': 60_000,
      'grpc.keepalive_timeout_ms': 20_000,
      'grpc.keepalive_permit_without_calls': 1
    }
  );
  const gateway = connect({
    client,
    identity: { mspId, credentials: certificate },
    signer,
    evaluateOptions: () => ({ deadline: Date.now() + 20_000 }),
    endorseOptions: () => ({ deadline: Date.now() + 30_000 }),
    submitOptions: () => ({ deadline: Date.now() + 20_000 }),
    commitStatusOptions: () => ({ deadline: Date.now() + 60_000 })
  });
  const network = gateway.getNetwork(channelName);
  const contract = network.getContract(chaincodeName);
  const session = { client, gateway, contract };
  sessions.set(alias, session);
  return session;
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBodyBytes) throw new HttpError(413, 'request body too large');
    chunks.push(chunk);
  }
  if (chunks.length === 0) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new HttpError(400, 'request body must be valid JSON');
  }
}

function validateCall(body, allowlist) {
  if (!body || typeof body !== 'object') throw new HttpError(400, 'JSON object required');
  if (typeof body.identity !== 'string' || !body.identity) throw new HttpError(422, 'identity is required');
  if (typeof body.transaction !== 'string' || !allowlist.has(body.transaction)) {
    throw new HttpError(403, 'transaction is not allowed by this agent');
  }
  if (!Array.isArray(body.args) || body.args.some((arg) => typeof arg !== 'string')) {
    throw new HttpError(422, 'args must be an array of strings');
  }
}

function validateNewIdentity(body) {
  if (!body || typeof body !== 'object') throw new HttpError(400, 'JSON object required');
  if (!/^[a-z0-9][a-z0-9_-]{2,63}$/.test(body.username ?? '')) {
    throw new HttpError(422, 'invalid username');
  }
  if (typeof body.display_name !== 'string' || !body.display_name.trim() || body.display_name.length > 120) {
    throw new HttpError(422, 'invalid display_name');
  }
  if (typeof body.role !== 'string' || !body.role) throw new HttpError(422, 'role is required');
  if (body.wallet_address !== undefined && body.wallet_address !== '' && !/^OLIVE-[A-F0-9]{24}$/.test(body.wallet_address)) {
    throw new HttpError(422, 'invalid wallet_address');
  }
}

function runIdentityAdmin(args) {
  const result = spawnSync(identityAdminScript, args, {
    env: process.env,
    encoding: 'utf8',
    timeout: 120_000,
    maxBuffer: 1024 * 1024
  });
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) throw new Error(`identity administration failed: ${result.error.message}`);
  if (result.status !== 0) {
    throw new HttpError(422, (result.stderr || result.stdout || 'identity administration failed').trim());
  }
  try {
    return JSON.parse(result.stdout.trim() || '{}');
  } catch {
    throw new Error('identity administration returned malformed JSON');
  }
}

function decodeResult(bytes) {
  if (!bytes || bytes.length === 0) return null;
  const text = decoder.decode(bytes);
  try { return JSON.parse(text); } catch { return text; }
}

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function send(res, status, body) {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': data.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  });
  res.end(data);
}

async function handler(req, res) {
  if (!authorized(req)) {
    send(res, 401, { error: 'unauthorized' });
    return;
  }
  try {
    if (req.method === 'GET' && req.url === '/health') {
      const dynamic = publicDynamicIdentities().filter((row) => row.active).map((row) => row.identity_alias);
      send(res, 200, {
        status: 'ok', msp_id: mspId, peer: peerEndpoint,
        channel: channelName, chaincode: chaincodeName,
        identities: [...Object.keys(staticIdentityMap), ...dynamic]
      });
      return;
    }
    if (req.method === 'GET' && req.url === '/admin/identities') {
      send(res, 200, { identities: publicDynamicIdentities() });
      return;
    }
    if (req.method === 'POST' && req.url === '/admin/identities') {
      const body = await readJson(req);
      validateNewIdentity(body);
      const created = runIdentityAdmin([
        'create', machineName, body.username, body.role, body.display_name.trim(), body.wallet_address ?? ''
      ]);
      const { contract } = getSession(created.identity_alias);
      const who = decodeResult(await contract.evaluateTransaction('WhoAmI'));
      send(res, 201, { ...created, client_id_hash: who?.client_id_hash ?? '' });
      return;
    }
    if (req.method === 'POST' && req.url === '/admin/identities/status') {
      const body = await readJson(req);
      if (typeof body.identity_alias !== 'string' || !body.identity_alias.startsWith('user:')) {
        throw new HttpError(422, 'dynamic identity_alias is required');
      }
      if (typeof body.active !== 'boolean') throw new HttpError(422, 'active must be boolean');
      const row = runIdentityAdmin([
        'status', machineName, body.identity_alias, body.active ? 'true' : 'false'
      ]);
      if (!body.active) closeSession(body.identity_alias);
      send(res, 200, row);
      return;
    }
    if (req.method === 'POST' && req.url === '/evaluate') {
      const body = await readJson(req);
      validateCall(body, evaluateAllowlist);
      const { contract } = getSession(body.identity);
      const result = await contract.evaluateTransaction(body.transaction, ...body.args);
      send(res, 200, { result: decodeResult(result) });
      return;
    }
    if (req.method === 'POST' && req.url === '/submit') {
      const body = await readJson(req);
      validateCall(body, submitAllowlist);
      const { contract } = getSession(body.identity);
      const result = await contract.submitTransaction(body.transaction, ...body.args);
      send(res, 200, { result: decodeResult(result) });
      return;
    }
    send(res, 404, { error: 'not found' });
  } catch (error) {
    const status = error instanceof HttpError ? error.status : 500;
    console.error(error);
    send(res, status, { error: error.message, name: error.name });
  }
}

const server = http.createServer(handler);
server.listen(port, host, () => {
  console.log(`OliveChain Gateway Agent listening on http://${host}:${port}`);
  console.log(`MSP ${mspId}; peer ${peerEndpoint}; static identities ${Object.keys(staticIdentityMap).join(', ')}`);
  console.log(`Dynamic identity store ${dynamicIdentityFile}`);
});

function shutdown() {
  for (const alias of sessions.keys()) closeSession(alias);
  server.close(() => process.exit(0));
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

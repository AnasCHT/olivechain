# OliveChain Fabric Gateway Agent

Run one agent on each of the four machines. It connects to the local peer and
loads only client identities stored on that machine. The FastAPI application
sends role-routed evaluate/submit requests; private keys never leave their
owning organization.

```bash
cd fabric-gateway-agent
npm ci
export OLIVECHAIN_AGENT_TOKEN='replace-with-a-long-random-value'
./start-agent.sh machine1
```

Use the same token on all four agents and the FastAPI process. Restrict TCP
9080 to Machine 1 at the host firewall. This initial bridge uses bearer-token
HTTP on the private lab network; add HTTPS or mTLS before production use.

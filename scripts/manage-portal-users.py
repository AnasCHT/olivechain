#!/usr/bin/env python3
"""Legacy command intentionally retired by OliveChain Wallet + Incentives 1.0."""
import sys

print(
    "Password-based portal accounts are retired.\n"
    "Create/connect a wallet at /portal. Public roles are requested there.\n"
    "For the first administrator wallet of an organization, run:\n"
    "  python3 scripts/bootstrap-wallet-admin.py <org-id> <OLIVE-wallet-address>\n",
    file=sys.stderr,
)
raise SystemExit(2)

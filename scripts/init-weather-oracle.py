#!/usr/bin/env python3
"""Create/reuse the Machine 1 weather-oracle key and bind its public key into chaincode."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=str(Path.home() / "olivechain-main"))
    args = parser.parse_args()
    project = Path(args.project).resolve()
    sys.path.insert(0, str(project))

    from olivechain.crypto import KeyPair

    key_path = project / "data" / "weather_oracle.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        signer = KeyPair.from_private_hex(key_path.read_text().strip())
        created = False
    else:
        signer = KeyPair.generate()
        key_path.write_text(signer.private_hex + "\n")
        os.chmod(key_path, 0o600)
        created = True

    config_path = (
        project / "fabric-network" / "chaincode" /
        "olivechain-domain" / "oracle_config.go"
    )
    if not config_path.exists():
        raise SystemExit(f"missing {config_path}")

    text = config_path.read_text()
    marker = "__OLIVECHAIN_WEATHER_ORACLE_PUBLIC_KEY__"
    import re
    pattern = r'const trustedWeatherOraclePublicKeyHex = "[0-9a-fA-F_\-]+"'
    replacement = f'const trustedWeatherOraclePublicKeyHex = "{signer.public_hex}"'
    if marker in text:
        text = text.replace(
            f'const trustedWeatherOraclePublicKeyHex = "{marker}"',
            replacement,
        )
    elif re.search(pattern, text):
        text = re.sub(pattern, replacement, text, count=1)
    else:
        raise SystemExit("oracle public-key constant not found")
    config_path.write_text(text)

    public_path = project / "data" / "weather_oracle_public_key.txt"
    public_path.write_text(signer.public_hex + "\n")
    print("Created weather oracle key." if created else "Reused existing weather oracle key.")
    print(f"Private key: {key_path} (do not copy or commit)")
    print(f"Public key:  {signer.public_hex}")
    print(f"Chaincode:   {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from pathlib import Path
import sys

valid_machines = {
    "machine1",
    "machine2",
    "machine3",
    "machine4",
}

if len(sys.argv) != 2 or sys.argv[1] not in valid_machines:
    raise SystemExit(
        "usage: enable-chaincode-runtime.py "
        "machine1|machine2|machine3|machine4"
    )

machine = sys.argv[1]
path = (
    Path("fabric-network")
    / "machines"
    / machine
    / "compose-node.yaml"
)

if not path.is_file():
    raise SystemExit(
        f"missing {path}; run this from olivechain-main"
    )

text = path.read_text()
network = f"olivechain-{machine}"

if "CORE_VM_ENDPOINT:" not in text:
    environment_marker = (
        '      CORE_PEER_PROFILE_ENABLED: "false"\n'
    )

    if environment_marker not in text:
        raise SystemExit(
            "peer environment insertion point not found"
        )

    text = text.replace(
        environment_marker,
        environment_marker
        + "      CORE_VM_ENDPOINT: "
          "unix:///host/var/run/docker.sock\n"
        + "      CORE_VM_DOCKER_HOSTCONFIG_NETWORKMODE: "
          f"{network}\n",
        1,
    )

socket_mount = (
    "      - /var/run/docker.sock:"
    "/host/var/run/docker.sock\n"
)

if (
    "/var/run/docker.sock:"
    "/host/var/run/docker.sock"
) not in text:
    volume_marker = (
        f"    volumes:\n"
        f"      - ../../runtime/{machine}/crypto/"
        "peerOrganizations/"
    )

    if volume_marker not in text:
        raise SystemExit(
            "peer volume insertion point not found"
        )

    text = text.replace(
        volume_marker,
        "    volumes:\n"
        + socket_mount
        + f"      - ../../runtime/{machine}/crypto/"
          "peerOrganizations/",
        1,
    )

path.write_text(text)

print(
    f"Enabled chaincode runtime in {path} "
    f"using Docker network {network}"
)

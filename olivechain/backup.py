"""Backup and restore for the ledger, registry, and off-chain evidence.

A backup is a gzipped tar containing `manifest.json` (with per-file SHA-256
checksums and a chain summary), `data/registry.json`, `data/ledger.jsonl`, and
every `evidence_store/` artifact. Restore is checksum-verified and guarded
against path traversal, so an archive can only ever write to `data/` and
`evidence_store/` under the destination.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import time

_ALLOWED_TOP = ("data/", "evidence_store/")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def make_backup(registry_path: str | None, ledger_path: str | None,
                evidence_root: str | None, *, extra: dict | None = None) -> bytes:
    """Build a gzipped-tar backup and return its bytes."""
    files: list[tuple[str, str]] = []
    if registry_path and os.path.isfile(registry_path):
        files.append((registry_path, "data/registry.json"))
    if ledger_path and os.path.isfile(ledger_path):
        files.append((ledger_path, "data/ledger.jsonl"))
    if evidence_root and os.path.isdir(evidence_root):
        for name in sorted(os.listdir(evidence_root)):
            p = os.path.join(evidence_root, name)
            if os.path.isfile(p):
                files.append((p, f"evidence_store/{name}"))

    manifest = {
        "format": "olivechain-backup/1",
        "exported_at": int(time.time()),
        "evidence_count": sum(1 for _, a in files if a.startswith("evidence_store/")),
        "files": {arc: _sha256_file(p) for p, arc in files},
    }
    if extra:
        manifest.update(extra)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        mb = json.dumps(manifest, indent=2).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(mb)
        ti.mtime = manifest["exported_at"]
        tar.addfile(ti, io.BytesIO(mb))
        for p, arc in files:
            tar.add(p, arcname=arc)
    return buf.getvalue()


def read_manifest(archive: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        f = tar.extractfile("manifest.json")
        if f is None:
            raise ValueError("archive has no manifest.json")
        return json.loads(f.read())


def restore_backup(archive: bytes, dest_dir: str) -> dict:
    """Extract a backup into dest_dir, verifying checksums. Only files under
    data/ and evidence_store/ are written; anything else is rejected."""
    dest = os.path.abspath(dest_dir)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        mf = tar.extractfile("manifest.json")
        if mf is None:
            raise ValueError("archive has no manifest.json")
        manifest = json.loads(mf.read())
        checksums = manifest.get("files", {})
        for member in tar.getmembers():
            name = member.name
            if name == "manifest.json":
                continue
            if not member.isfile():
                raise ValueError(f"unexpected non-file entry: {name}")
            if name.startswith("/") or ".." in name.split("/") or not name.startswith(_ALLOWED_TOP):
                raise ValueError(f"unsafe path in archive: {name}")
            target = os.path.join(dest, name)
            if not os.path.abspath(target).startswith(dest + os.sep):
                raise ValueError(f"path escapes destination: {name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tar.extractfile(member)
            with open(target, "wb") as out:
                out.write(src.read())
            want = checksums.get(name)
            if want and _sha256_file(target) != want:
                raise ValueError(f"checksum mismatch after restoring {name}")
    return manifest

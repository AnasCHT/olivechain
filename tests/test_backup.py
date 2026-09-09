"""Backup / restore: round-trip integrity, checksum enforcement, and
path-traversal safety."""
import io
import tarfile

import pytest

from olivechain import EvidenceStore, Ledger, Registry
from olivechain.backup import make_backup, read_manifest, restore_backup
from olivechain.models import EventType, Role


def _populate(tmp):
    registry = Registry(str(tmp / "registry.json"))
    ledger = Ledger(registry, str(tmp / "ledger.jsonl"))
    store = EvidenceStore(str(tmp / "evidence"))
    kp = registry.register("coop", "Coop", [Role.FARMER])
    ref = store.put("cert.pdf", b"%PDF- demo evidence")
    ledger.append(EventType.CULTIVATION, "BATCH-1", "coop",
                  {"farm_id": "f", "plot_id": "p", "cultivar": "Picholine",
                   "practices": ["organic"]}, kp, evidence=[ref])
    ledger.append(EventType.HARVEST, "BATCH-1", "coop",
                  {"date": "2026-01-01", "quantity_kg": 100, "method": "hand",
                   "location": "x"}, kp)
    return registry, ledger, store


def test_backup_restore_roundtrip(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    registry, ledger, store = _populate(src)
    archive = make_backup(registry.path, ledger.path, store.root,
                          extra={"height": len(ledger)})

    manifest = read_manifest(archive)
    assert manifest["format"] == "olivechain-backup/1"
    assert manifest["evidence_count"] == 1
    assert manifest["height"] == 2

    restore_backup(archive, str(dst))
    # the restored ledger loads and verifies independently
    r2 = Registry(str(dst / "data" / "registry.json"))
    l2 = Ledger(r2, str(dst / "data" / "ledger.jsonl"))
    ok, problems = l2.verify_chain()
    assert ok, problems
    assert len(l2) == 2
    assert (dst / "evidence_store").is_dir()
    assert any((dst / "evidence_store").iterdir())


def test_restore_detects_tampered_file(tmp_path):
    src = tmp_path / "src"
    registry, ledger, store = _populate(src)
    archive = make_backup(registry.path, ledger.path, store.root)

    # rewrite the ledger entry inside the tar without updating the manifest
    buf_in = io.BytesIO(archive)
    out = io.BytesIO()
    with tarfile.open(fileobj=buf_in, mode="r:gz") as tin, \
            tarfile.open(fileobj=out, mode="w:gz") as tout:
        for m in tin.getmembers():
            data = tin.extractfile(m).read()
            if m.name == "data/ledger.jsonl":
                data = data + b'{"tampered":true}\n'
                m.size = len(data)
            tout.addfile(m, io.BytesIO(data))
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_backup(out.getvalue(), str(tmp_path / "dst"))


def test_restore_rejects_path_traversal(tmp_path):
    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w:gz") as tar:
        mb = b'{"format":"olivechain-backup/1","files":{}}'
        ti = tarfile.TarInfo("manifest.json"); ti.size = len(mb)
        tar.addfile(ti, io.BytesIO(mb))
        payload = b"pwned"
        ev = tarfile.TarInfo("../../escape.txt"); ev.size = len(payload)
        tar.addfile(ev, io.BytesIO(payload))
    with pytest.raises(ValueError, match="unsafe path"):
        restore_backup(evil.getvalue(), str(tmp_path / "dst"))

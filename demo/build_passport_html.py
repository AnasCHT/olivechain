"""Render the consumer passport HTML from the generated passport JSON."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
with open(os.path.join(ROOT, "data", "passport_BATCH-2025-001.json"), encoding="utf-8") as f:
    passport = json.load(f)
with open(os.path.join(ROOT, "frontend", "passport_template.html"), encoding="utf-8") as f:
    tpl = f.read()

out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "frontend", "passport_BATCH-2025-001.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(tpl.replace("__PASSPORT_JSON__", json.dumps(passport)))
print("wrote", out_path)

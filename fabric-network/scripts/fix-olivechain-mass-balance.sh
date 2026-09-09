#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-$HOME/olivechain-main}"

GO_FILE="$PROJECT/fabric-network/chaincode/olivechain-domain/massbalance.go"
PY_FILE="$PROJECT/olivechain/massbalance.py"
UI_FILE="$PROJECT/frontend/index.html"

for file in "$GO_FILE" "$PY_FILE" "$UI_FILE"; do
  [[ -f "$file" ]] || {
    echo "Required file not found: $file" >&2
    exit 1
  }
done

stamp="$(date +%Y%m%d-%H%M%S)"
cp "$GO_FILE" "$GO_FILE.before-mass-balance-fix-$stamp"
cp "$PY_FILE" "$PY_FILE.before-mass-balance-fix-$stamp"
cp "$UI_FILE" "$UI_FILE.before-mass-balance-fix-$stamp"

python3 - "$GO_FILE" "$PY_FILE" "$UI_FILE" <<'PY'
from pathlib import Path
import sys

go_path = Path(sys.argv[1])
py_path = Path(sys.argv[2])
ui_path = Path(sys.argv[3])

# ---------- Go chaincode ----------
go = go_path.read_text()

old_go_check = '''	if rec.TransformedKg != 0 && !within(rec.AcceptedKg, rec.TransformedKg) {
		rec.Issues = append(rec.Issues, fmt.Sprintf("transformation mismatch: accepted %vkg, transformed %vkg", rec.AcceptedKg, rec.TransformedKg))
	}
	if rec.TransformedKg == 0 && rec.AcceptedKg > 0 {
		rec.Issues = append(rec.Issues, "residue accepted but no valorization recorded")
	}
	rec.Balanced = len(rec.Issues) == 0
	if rec.GeneratedKg > 0 {
		rec.RecoveryPct = round2(100 * (rec.TransformedKg - rec.RejectedKg) / rec.GeneratedKg)
	}
'''

new_go_check = '''	accountedKg := rec.TransformedKg + rec.RejectedKg
	if accountedKg != 0 && !within(rec.AcceptedKg, accountedKg) {
		rec.Issues = append(rec.Issues, fmt.Sprintf(
			"transformation mismatch: accepted %vkg, transformed %vkg, rejected %vkg, accounted %vkg",
			rec.AcceptedKg,
			rec.TransformedKg,
			rec.RejectedKg,
			accountedKg,
		))
	}
	if accountedKg == 0 && rec.AcceptedKg > 0 {
		rec.Issues = append(rec.Issues, "residue accepted but no valorization recorded")
	}
	rec.Balanced = len(rec.Issues) == 0
	if rec.GeneratedKg > 0 {
		rec.RecoveryPct = round2(100 * rec.TransformedKg / rec.GeneratedKg)
	}
'''

if old_go_check in go:
    go = go.replace(old_go_check, new_go_check, 1)
elif "accountedKg := rec.TransformedKg + rec.RejectedKg" not in go:
    raise SystemExit("Could not locate the expected Go reconciliation block")

go_path.write_text(go)

# ---------- Python compatibility/backend ----------
py = py_path.read_text()

old_py_pct = '''    def recovery_pct(self) -> float:
        if self.generated_kg <= 0:
            return 0.0
        return round(100.0 * (self.transformed_kg - self.rejected_kg) / self.generated_kg, 2)
'''

new_py_pct = '''    def recovery_pct(self) -> float:
        if self.generated_kg <= 0:
            return 0.0
        return round(100.0 * self.transformed_kg / self.generated_kg, 2)
'''

if old_py_pct in py:
    py = py.replace(old_py_pct, new_py_pct, 1)
elif "100.0 * self.transformed_kg / self.generated_kg" not in py:
    raise SystemExit("Could not locate Python recovery_pct implementation")

old_py_check = '''    if rec.transformed_kg and not within(rec.accepted_kg, rec.transformed_kg):
        rec.issues.append(
            f"transformation mismatch: accepted {rec.accepted_kg}kg, transformed {rec.transformed_kg}kg"
        )
    if rec.transformed_kg == 0 and rec.accepted_kg > 0:
        rec.issues.append("residue accepted but no valorization recorded")
'''

new_py_check = '''    accounted_kg = rec.transformed_kg + rec.rejected_kg
    if accounted_kg and not within(rec.accepted_kg, accounted_kg):
        rec.issues.append(
            "transformation mismatch: "
            f"accepted {rec.accepted_kg}kg, "
            f"transformed {rec.transformed_kg}kg, "
            f"rejected {rec.rejected_kg}kg, "
            f"accounted {accounted_kg}kg"
        )
    if accounted_kg == 0 and rec.accepted_kg > 0:
        rec.issues.append("residue accepted but no valorization recorded")
'''

if old_py_check in py:
    py = py.replace(old_py_check, new_py_check, 1)
elif "accounted_kg = rec.transformed_kg + rec.rejected_kg" not in py:
    raise SystemExit("Could not locate Python reconciliation check")

py_path.write_text(py)

# ---------- Dashboard percentage ----------
ui = ui_path.read_text()

old_ui = '''    const r = await api("/residues/"+encodeURIComponent(rid)+"/balance");
    const pct = Math.max(0, Math.min(100, r.recovery_pct));
'''

new_ui = '''    const r = await api("/residues/"+encodeURIComponent(rid)+"/balance");
    const generatedKg = Number(r.generated_kg ?? 0);
    const transformedKg = Number(r.transformed_kg ?? 0);
    const apiPct = Number(r.recovery_pct);
    const rawPct = Number.isFinite(apiPct)
      ? apiPct
      : (generatedKg > 0 ? (100 * transformedKg / generatedKg) : 0);
    const pct = Math.max(0, Math.min(100, rawPct));
'''

if old_ui in ui:
    ui = ui.replace(old_ui, new_ui, 1)
elif "const rawPct = Number.isFinite(apiPct)" not in ui:
    raise SystemExit("Could not locate dashboard percentage calculation")

ui = ui.replace(
    '<div class="barlab">${r.recovery_pct}% of generated mass verifiably recovered</div>',
    '<div class="barlab">${fmt(rawPct)}% of generated mass verifiably recovered</div>',
    1,
)

ui_path.write_text(ui)

print("Patched:")
print(f"  {go_path}")
print(f"  {py_path}")
print(f"  {ui_path}")
PY

echo
echo "Mass-balance correction applied."
echo "Rule now used:"
echo "  accepted = transformed + rejected"
echo "  recovery % = transformed / generated × 100"
echo
echo "Backups use timestamp: $stamp"

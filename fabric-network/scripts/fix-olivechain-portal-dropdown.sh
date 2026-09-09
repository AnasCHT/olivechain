#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-$HOME/olivechain-main}"
PORTAL="$PROJECT/frontend/portal.html"

[[ -f "$PORTAL" ]] || {
  echo "Portal file not found: $PORTAL" >&2
  exit 1
}

backup="$PORTAL.before-dropdown-fix-$(date +%Y%m%d-%H%M%S)"
cp "$PORTAL" "$backup"

python3 - "$PORTAL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

if "async function loadAgentHealth()" not in text:
    marker = "function renderProfile(){"
    if marker not in text:
        raise SystemExit("Could not find renderProfile() insertion point")

    function = r'''
async function loadAgentHealth(){
  const state=$("agentState");
  if(!state)return;
  try{
    const health=await api("/portal/agent-health");
    state.textContent=`Online · ${health.msp_id||"Gateway ready"}`;
    state.style.color="var(--ok)";
    state.title=`${health.peer||""} · ${health.channel||""} · ${health.chaincode||""}`;
  }catch(e){
    state.textContent="Unavailable";
    state.style.color="var(--warn)";
    state.title=e.message;
  }
}
'''
    text = text.replace(marker, function + "\n" + marker, 1)

old = '''function renderSubmit(){const mine=allowedSchema();$("eventType").innerHTML=mine.map(s=>`<option value="${esc(s.event_type)}">${esc(NICE(s.event_type))}</option>`).join('');$("eventType").onchange=renderFields;renderFields();$("process").innerHTML=STAGES.map(stage=>{const item=schema.find(s=>s.event_type===stage);const allowed=item?.allowed_roles.includes(session.role);return `<div class="stage ${allowed?'allowed':''}"><b>${esc(NICE(stage))}</b><span>${allowed?'You can record':'Recorded by another actor'}</span></div>`}).join('')}'''

new = '''function renderSubmit(){const mine=allowedSchema();const select=$("eventType");if(!mine.length){select.innerHTML='<option value="" disabled selected>No event types available for this role</option>';$("eventHint").textContent=`No schema entries matched role ${session.role}`;$("fields").innerHTML="";}else{select.innerHTML=mine.map(s=>`<option value="${esc(s.event_type)}">${esc(NICE(s.event_type))}</option>`).join('');$("eventHint").textContent=`${mine.length} event type${mine.length===1?'':'s'} available for ${session.role}`;select.onchange=renderFields;renderFields();}$("process").innerHTML=STAGES.map(stage=>{const item=schema.find(s=>s.event_type===stage);const allowed=item?.allowed_roles.includes(session.role);return `<div class="stage ${allowed?'allowed':''}"><b>${esc(NICE(stage))}</b><span>${allowed?'You can record':'Recorded by another actor'}</span></div>`}).join('')}'''

if old in text:
    text = text.replace(old, new, 1)

path.write_text(text)
print(f"Patched {path}")
PY

echo "Backup: $backup"
echo "Portal event dropdown fix applied."

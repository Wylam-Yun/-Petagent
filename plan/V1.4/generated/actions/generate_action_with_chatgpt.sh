#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:?usage: generate_action_with_chatgpt.sh <action>}"
ROOT="/Users/wylam/Documents/workspace/Petagent/plan/V1.4/generated/actions"
BASE="$ROOT/$ACTION"
PROMPT_FILE="$BASE/${ACTION}_prompt.txt"
REF="/Users/wylam/Documents/workspace/Petagent/plan/V1.4/generated/reference_idle_frame_white.png"
OUT_LOG="$BASE/${ACTION}_opencli_output.txt"

mkdir -p "$BASE"
PROMPT="$(cat "$PROMPT_FILE")"

opencli chatgpt image "$PROMPT" \
  --image "$REF" \
  --op "$BASE" \
  --timeout 480 \
  --window background \
  -f yaml | tee "$OUT_LOG"

LINK="$(grep -o 'https://chatgpt.com/c/[A-Za-z0-9-]*' "$OUT_LOG" | tail -1)"
if [ -z "$LINK" ]; then
  echo "missing ChatGPT conversation link" >&2
  exit 1
fi
echo "$LINK" > "$BASE/${ACTION}_conversation_url.txt"

SESSION="v14_${ACTION}"
opencli browser "$SESSION" open "$LINK" >/dev/null

for i in $(seq 1 80); do
  STATE="$(opencli browser "$SESSION" eval "(()=>{const imgs=Array.from(document.images).map((img,i)=>({i,alt:img.alt||'',src:img.src||'',w:img.naturalWidth,h:img.naturalHeight,complete:img.complete})); const gen=imgs.find(x=>x.alt.includes('已生成图片') || (x.src.includes('backend-api/estuary/content') && x.w>800 && x.h>200 && !x.alt.includes('reference'))); return {ready:!!gen, gen, count:imgs.length};})()")"
  echo "poll $i: $STATE"
  if echo "$STATE" | grep -q '"ready": true'; then
    break
  fi
  sleep 15
done

opencli browser "$SESSION" screenshot "$BASE/${ACTION}_page_final.png" --full-page >/dev/null

opencli browser "$SESSION" eval "(async()=>{const imgs=Array.from(document.images); const img=imgs.find(i=>(i.alt||'').includes('已生成图片')) || imgs.find(i=>i.src.includes('backend-api/estuary/content') && i.naturalWidth>800 && i.naturalHeight>200 && !(i.alt||'').includes('reference')); if(!img) return {ready:false}; const res=await fetch(img.src); const blob=await res.blob(); const data=await new Promise((resolve,reject)=>{const r=new FileReader(); r.onload=()=>resolve(r.result); r.onerror=reject; r.readAsDataURL(blob);}); return {ready:true,w:img.naturalWidth,h:img.naturalHeight,type:blob.type,size:blob.size,alt:img.alt,data};})()" > "$BASE/${ACTION}_image_data.json"

python3 - <<PY
import json, base64, re
from pathlib import Path
base=Path("$BASE")
action="$ACTION"
obj=json.loads((base/f"{action}_image_data.json").read_text())
if not obj.get("ready"):
    raise SystemExit("generated image not ready")
m=re.match(r"data:(.*?);base64,(.*)", obj["data"])
if not m:
    raise SystemExit("no data url")
ext="png" if "png" in m.group(1) else "jpg"
out=base/f"{action}_chatgpt_web_actual.{ext}"
out.write_bytes(base64.b64decode(m.group(2)))
print(out)
print(obj.get("w"), obj.get("h"), obj.get("type"), obj.get("size"), obj.get("alt"))
PY

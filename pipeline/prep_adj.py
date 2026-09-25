#!/usr/bin/env python3
"""Pick repos whose first-pass classification is doubtful and write adjudication card files."""
import json, os, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "work")
OUTDIR = os.path.join(SCR, "adj")
os.makedirs(OUTDIR, exist_ok=True)
for f in os.listdir(OUTDIR):
    os.remove(os.path.join(OUTDIR, f))
KZ = timezone(timedelta(hours=5))
FINAL = datetime(2026, 9, 23, 0, 0, tzinfo=KZ)

ext = {json.loads(l)["name"]: json.loads(l) for l in open(os.path.join(SCR, "extracted.jsonl"))}
ana = json.load(open(os.path.join(SCR, "analysis.json")))
heur = json.load(open(os.path.join(SCR, "heuristic.json")))

disputed = []
for name, a in sorted(ana.items()):
    e = ext[name]
    h = heur.get(name, {})
    ht, hm = h.get("h_track"), h.get("h_margin", 0)
    last = datetime.fromisoformat(e["last_commit"]).astimezone(KZ) if e.get("last_commit") else None
    why = []
    if a["status"] == "case" and ht and a["track"] != ht:
        why.append(f"эвристика по ключевым словам (отрыв {hm}) указывает на кейс {ht}, а первый проход — на {a['track']}")
    if a["status"] == "case" and a.get("confidence") in ("low", "medium"):
        why.append(f"первый проход не вполне уверен в кейсе ({a.get('confidence')})")
    if a["status"] == "other_task" and ht and hm >= 8:
        why.append(f"помечено как другое задание, но эвристика заметно указывает на кейс {ht}")
    if a["status"] == "unclear":
        why.append("первый проход не смог определить кейс")
    if a["status"] == "other_task" and last and last >= FINAL:
        why.append(f"помечено как другое задание, но последние коммиты сделаны в день финала (эвристика: {ht})")
    if a["status"] == "no_content" and e.get("commits_human", 0) >= 8 and e.get("n_files", 0) >= 8:
        why.append("помечено как пустое, но есть ≥8 коммитов и ≥8 файлов")
    if why:
        disputed.append((name, a, ht, hm, why))

print("disputed:", len(disputed), file=sys.stderr)


def card(name, a, ht, why):
    e = ext[name]
    readme = e.get("readme") or ""
    if e.get("readme_is_template") or not readme.strip():
        readme = "\n\n".join(f"[{x['path']}]\n{x['text']}" for x in e.get("extra_readmes", [])) or readme
    tree = e.get("tree", [])
    lines = [
        f"########## REPO: {name}  (team: {e.get('team')})",
        f"commits={e.get('commits_human')} authors={e.get('n_authors')} files={e.get('n_files')} first={e.get('first_commit')} last={e.get('last_commit')}",
        f"FIRST PASS: status={a['status']} track={a['track']} confidence={a.get('confidence')} evidence={a.get('evidence')}",
        f"FIRST PASS summary: {a.get('summary')}",
        f"KEYWORD HEURISTIC suggests track: {ht}",
        f"WHY DISPUTED: {'; '.join(why)}",
        f"nested READMEs: {', '.join(e.get('nested_readmes', [])[:10]) or '-'}",
        f"--- README ({e.get('readme_path')}) ---",
        readme[:18000].strip() or "(нет README)",
        "--- FILE TREE ---", *tree[:300], *( [f"…ещё {len(tree) - 300}"] if len(tree) > 300 else []),
        "--- COMMIT SUBJECTS ---", *[c["s"] for c in e.get("commits", [])][:120],
        f"########## END {name}", "",
    ]
    return "\n".join(lines)


manifest, cur, size = [], [], 0
def flush():
    i = len(manifest)
    p = os.path.join(OUTDIR, f"adj_{i:03d}.md")
    open(p, "w").write("\n".join(c for _, c in cur))
    manifest.append({"path": p, "n": len(cur)})

for name, a, ht, hm, why in disputed:
    c = card(name, a, ht, why)
    if cur and (len(cur) >= 10 or size + len(c) > 150_000):
        flush(); cur, size = [], 0
    cur.append((name, c)); size += len(c)
if cur:
    flush()
json.dump([m["n"] for m in manifest], open(os.path.join(SCR, "adj_counts.json"), "w"))
# args for pipeline/workflows/02_adjudicate.js
json.dump({"dir": OUTDIR, "counts": [m["n"] for m in manifest]}, open(os.path.join(SCR, "adjudicate_args.json"), "w"))
print("adj batches:", len(manifest), [m["n"] for m in manifest], file=sys.stderr)

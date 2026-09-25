#!/usr/bin/env python3
"""Per-track dossiers (analysis of every repo) + README bundles for the synthesis workflow."""
import json, os, statistics as st, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "work")
OUTDIR = os.path.join(SCR, "syn")
os.makedirs(OUTDIR, exist_ok=True)
S = json.load(open(os.path.join(SCR, "summary.json")))
ext = {}
for l in open(os.path.join(SCR, "extracted.jsonl")):
    r = json.loads(l)
    if r.get("commits_human"):
        ext[r["name"]] = r
MAT = {"polished": "доведено", "working_mvp": "рабочий MVP", "prototype": "прототип", "idea_only": "идея", "no_code": "нет кода"}

stats_lines = []
for t in S["tracks"]:
    rs = [r for r in S["repos"] if r["st"] == "case" and r["tr"] == t["id"]]
    rs.sort(key=lambda r: r["n"])
    mc = Counter(r["ma"] for r in rs)
    head = (f"TRACK {t['id']:02d} — {t['industry']} · {t['partner']}\nTask: {t['task']}\n"
            f"Teams: {len(rs)}; maturity: {', '.join(f'{MAT[k]} {v}' for k, v in mc.most_common())}; "
            f"median commits {t['med_commits']}, median authors {t['med_authors']}; with Docker {t['docker']}; report metrics {t['metrics']}\n"
            f"Providers: {', '.join(p['name'] + ' ' + str(p['n']) for p in t['providers'][:8])}\n"
            f"Models: {', '.join(m['name'] + ' ' + str(m['n']) for m in t.get('models', [])[:10])}\n"
            f"Top techniques: {', '.join(x['name'] + ' ' + str(x['n']) for x in t['top_tech'][:14])}\n")
    stats_lines.append(head)
    blocks = [head, "=" * 60]
    for r in rs:
        blocks.append("\n".join([
            f"### {r['n']} | team: {r['t']} | project: {r['pn']}",
            f"maturity={MAT.get(r['ma'], r['ma'])} readme_quality={r['rq']}/3 commits={r['c']} authors={r['a']} files={r['f']} run_instr={r['ru']} demo={r['de']} late_commits={r['late']}",
            f"core: {', '.join(r['co'])} | techniques: {', '.join(r['te'])}",
            f"llms: {', '.join(r['ll'])} | stack: {', '.join(r['sk'])}",
            f"metrics: {r['me'] or '-'}",
            f"summary: {r['su']}",
            f"approach: {r['ap']}",
            f"notable: {r['no'] or '-'}",
            f"flags: {', '.join(r['fl'])}",
            "",
        ]))
    open(os.path.join(OUTDIR, f"dossier_t{t['id']:02d}.md"), "w").write("\n".join(blocks))
    rb = []
    for r in rs:
        e = ext[r["n"]]
        txt = (e.get("readme") or "")[:9000]
        rb.append(f"########## README {r['n']} ({r['pn'] or r['t']})\n{txt}\n########## END {r['n']}\n")
    open(os.path.join(OUTDIR, f"readmes_t{t['id']:02d}.md"), "w").write("\n".join(rb))
    print(t["id"], len(rs), file=sys.stderr)

T = S["totals"]
glob = (f"GLOBAL: {T['repos']} repos in org; {T['active']} with participant commits; {T['bot_only']} only the bot's initial commit; "
        f"{T['case_repos']} solve one of the 12 final cases; {T['commits']} participant commits, {T['in_window_pct']}% inside 12:00–18:00 Astana on 2026-09-23; "
        f"median {T['median_commits']} commits/team; {T['authors_total']} unique commit authors; {T['late_repos']} repos have {T['late_commits']} commits after 18:00; "
        f"{T['ai_repos']} repos have commits with AI Co-Authored-By trailers ({T['claude_repos']} with Claude).\n"
        f"Tooling (share of {T['active']} active repos): " + "; ".join(f"{x['l']} {x['n']}" for x in S["tooling"]) + "\n"
        f"Providers across case solutions: " + ", ".join(f"{p['name']} {p['n']}" for p in S["providers"][:12]) + "\n"
        f"Models: " + ", ".join(f"{m['name']} {m['n']}" for m in S["models"][:16]) + "\n"
        f"Team sizes (distinct commit authors): " + ", ".join(f"{x['k']}: {x['n']}" for x in S["team_sizes"]) + "\n"
        f"Non-case active repos: " + ", ".join(f"{k} {v}" for k, v in Counter(r['st'] for r in S['repos'] if r['st'] != 'case').items()) + "\n")
open(os.path.join(OUTDIR, "global_stats.md"), "w").write(glob + "\n\n" + "\n".join(stats_lines))
# args for pipeline/workflows/03_synthesize.js
json.dump({"dir": OUTDIR, "tracks": [{"id": t["id"], "n": sum(1 for r in S["repos"] if r["st"] == "case" and r["tr"] == t["id"]),
                                      "title": f"{t['id']:02d} {t['industry']} · {t['partner']} — {t['task']}"} for t in S["tracks"]]},
          open(os.path.join(SCR, "synthesize_args.json"), "w"), ensure_ascii=False)
print(glob, file=sys.stderr)

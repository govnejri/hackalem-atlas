#!/usr/bin/env python3
"""Store a workflow's results where build_site.py expects them.

usage:
  save_results.py analyze    <journal.jsonl>          -> work/analysis.json      (merged by repo name)
  save_results.py adjudicate <result.json>            -> work/adjudication.json, work/adjudication_meta.json
  save_results.py synthesize <result.json>            -> work/synthesis.json, work/factcheck_changes.json

<journal.jsonl> is the workflow's transcript journal; <result.json> is the workflow's saved task output
(an object with "result", or the bare return value).
"""
import json, os, sys

WORK = os.environ.get("WORK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")


def load_result(path):
    o = json.load(open(path))
    return o.get("result", o) if isinstance(o, dict) else o


def main():
    kind, src = sys.argv[1], sys.argv[2]
    if kind == "analyze":
        out = os.path.join(WORK, "analysis.json")
        res = json.load(open(out)) if os.path.exists(out) else {}
        n = 0
        for line in open(src):
            j = json.loads(line)
            r = j.get("result") if j.get("type") == "result" else None
            if isinstance(r, str):
                try: r = json.loads(r)
                except ValueError: r = None
            for x in (r or {}).get("repos", []) if isinstance(r, dict) else []:
                res[x["name"]] = x; n += 1
        json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
        print(f"{n} records merged, {len(res)} total -> {out}")
    elif kind == "adjudicate":
        r = load_result(src)
        dec = {d["name"]: d for d in r["decisions"]}
        json.dump(dec, open(os.path.join(WORK, "adjudication.json"), "w"), ensure_ascii=False, indent=1)
        json.dump({"disputed": len(dec)}, open(os.path.join(WORK, "adjudication_meta.json"), "w"))
        print(f"{len(dec)} decisions -> work/adjudication.json")
    elif kind == "synthesize":
        r = load_result(src)
        json.dump({"tracks": r["tracks"], "overview": r["overview"]}, open(os.path.join(WORK, "synthesis.json"), "w"), ensure_ascii=False, indent=1)
        json.dump(r.get("changes", []), open(os.path.join(WORK, "factcheck_changes.json"), "w"), ensure_ascii=False, indent=1)
        print(f"{len(r['tracks'])} tracks -> work/synthesis.json")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

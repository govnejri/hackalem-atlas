#!/usr/bin/env python3
"""Heuristic track guess + compact per-repo cards in batch files for LLM analysis."""
import json, os, re, sys
from collections import Counter

SCR = os.environ.get("WORK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")
BATCH_DIR = os.path.join(SCR, "batches")
os.makedirs(BATCH_DIR, exist_ok=True)
BATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 20

TRACKS = {
    1: ("Энергетика", "Самрук-Казына", [r"ветр", r"\bвэс\b", r"wind", r"turbine", r"турбин", r"выработк", r"генерац", r"электростанц", r"power\s*(output|forecast)", r"\bmw\b|мвт", r"погод", r"weather"]),
    2: ("Финансы", "Freedom", [r"\baml\b", r"граф денег", r"money\s*graph", r"отмыв", r"launder", r"транзакц", r"transaction", r"организованн", r"fraud", r"мошен", r"freedom"]),
    3: ("Менеджмент", "Halyk Bank (кейс 1)", [r"career\s*quest", r"карьер", r"career", r"навык", r"skill", r"\bidp\b", r"компетенц", r"сотрудник", r"\bhr\b"]),
    4: ("Телеком", "Beeline", [r"beeline", r"билайн", r"тариф", r"tariff", r"абонент", r"subscriber", r"\barpu\b", r"upsell", r"churn", r"отток"]),
    5: ("Логистика", "Электрокомплект (ekt.kz)", [r"поставщик", r"supplier", r"пополнени", r"replenish", r"склад", r"warehouse", r"inventory", r"остатк", r"закуп", r"purchase\s*order", r"reorder", r"safety\s*stock"]),
    6: ("Креативные индустрии", "Firebird", [r"firebird", r"#?79", r"подрядчик", r"contractor", r"vendor", r"мероприят", r"event", r"ивент"]),
    7: ("Образование", "AI Sana", [r"challenge\s*hub", r"ai\s*sana", r"студенческ", r"student", r"task\s*card", r"кейс для студ", r"задани"]),
    8: ("Инновации", "Самрук-Казына", [r"хаттама", r"hattama", r"khattama", r"протокол", r"совещан", r"meeting", r"поручени", r"minutes", r"transcri", r"транскриб", r"whisper", r"диаризац", r"diariz"]),
    9: ("Коммуникации", "Halyk Bank (кейс 2)", [r"voice\s*router", r"контакт.центр", r"call\s*cent", r"contact\s*cent", r"страхов", r"insurance", r"звонк", r"\bivr\b", r"маршрутиз", r"routing"]),
    10: ("Торговля", "Электрокомплект (ekt.kz)", [r"каталог", r"catalog", r"аналог", r"корзин", r"\bcart\b", r"товар", r"product", r"консультант", r"ekt\.kz"]),
    11: ("Спецтрек", "Казахтелеком", [r"казахтелеком", r"kazakhtelecom", r"оргструктур", r"org\s*structure", r"org\s*chart", r"реорганизац", r"reorg", r"штатн", r"подразделени"]),
    12: ("Спецтрек", "Astana Innovations", [r"аким", r"akim", r"astana\s*innovations", r"симулятор", r"simulat", r"бюджет", r"budget", r"район", r"district"]),
}
STRONG = {  # near-unique phrases
    1: [r"ветров", r"\bвэс\b", r"wind\s*(farm|power|turbine|energy)"],
    2: [r"\baml\b", r"граф денег", r"money\s*graph", r"отмыв", r"launder"],
    3: [r"career\s*quest", r"карьерн\w* (навигат|трек|путь)"],
    4: [r"\barpu\b", r"beeline|билайн"],
    5: [r"пополнени\w* склад", r"replenish", r"заказ\w* поставщик", r"reorder\s*point"],
    6: [r"firebird", r"79-lite", r"#79", r"подрядчик"],
    7: [r"challenge\s*hub", r"ai\s*sana"],
    8: [r"хаттама", r"hattama|khattama", r"протокол\w* совещан", r"meeting\s*minutes"],
    9: [r"voice\s*router", r"контакт.центр\w* страхов", r"insurance\s*(call|contact)"],
    10: [r"ekt\.kz.*(каталог|catalog|консультант)", r"(каталог|catalog).*(аналог|analog)", r"корзин"],
    11: [r"казахтелеком|kazakhtelecom", r"оргструктур", r"реорганизац"],
    12: [r"аким на 5", r"akim", r"городской симулятор", r"city\s*simulat", r"astana\s*innovations"],
}


def guess(text):
    t = text.lower()
    scores = {}
    for k, (_, _, kws) in TRACKS.items():
        s = sum(min(len(re.findall(kw, t)), 5) for kw in kws)
        s += 8 * sum(1 for kw in STRONG[k] if re.search(kw, t))
        scores[k] = s
    best = sorted(scores.items(), key=lambda kv: -kv[1])
    if best[0][1] == 0:
        return None, 0, scores
    margin = best[0][1] - best[1][1]
    return best[0][0], margin, scores


def main():
    recs = [json.loads(l) for l in open(os.path.join(SCR, "extracted.jsonl"))]
    work, skipped = [], Counter()
    for r in recs:
        if not r.get("clone_ok"):
            skipped["clone_failed"] += 1; continue
        if r.get("empty"):
            skipped["empty_repo"] += 1; continue
        if not r.get("commits_human"):
            skipped["bot_only"] += 1; continue
        text = " ".join([r.get("readme") or "", " ".join(x["text"] for x in r.get("extra_readmes", [])),
                         " ".join(r.get("tree", [])[:400]), " ".join(c["s"] for c in r.get("commits", [])[:200])])
        g, margin, scores = guess(text)
        r["h_track"], r["h_margin"] = g, margin
        work.append(r)
    print("skipped:", dict(skipped), "work:", len(work), file=sys.stderr)
    json.dump({r["name"]: {"h_track": r["h_track"], "h_margin": r["h_margin"]} for r in work},
              open(os.path.join(SCR, "heuristic.json"), "w"), ensure_ascii=False)
    # compact cards
    cards = []
    for r in work:
        tree = r.get("tree", [])
        readme = (r.get("readme") or "")
        if r.get("readme_is_template") or not readme.strip():
            readme = "\n\n".join(f"[{x['path']}]\n{x['text']}" for x in r.get("extra_readmes", [])) or readme
        card = {
            "name": r["name"], "team": r["team"],
            "commits": r["commits_human"], "authors": r["n_authors"], "files": r.get("n_files"),
            "first_commit": r.get("first_commit"), "last_commit": r.get("last_commit"),
            "flags": [k for k, v in (r.get("flags") or {}).items() if v],
            "ext": r.get("ext"),
            "readme_path": r.get("readme_path"), "readme_len": r.get("readme_len", 0),
            "readme_is_template": r.get("readme_is_template", False),
            "readme": readme[:10000] + ("\n…[README обрезан]" if len(readme) > 10000 else ""),
            "tree": tree[:150] + ([f"…ещё {len(tree) - 150} файлов"] if len(tree) > 150 else []),
            "commit_subjects": [c["s"] for c in r.get("commits", [])][:40],
        }
        cards.append(card)
    # order by name for stable batches
    cards.sort(key=lambda c: c["name"])
    for f in os.listdir(BATCH_DIR):
        os.remove(os.path.join(BATCH_DIR, f))

    def render(c):
        lines = [f"########## REPO: {c['name']}  (team: {c['team']})",
                 f"commits={c['commits']} authors={c['authors']} files={c['files']} first={c['first_commit']} last={c['last_commit']}",
                 f"flags: {', '.join(c['flags']) or '-'}",
                 f"extensions: {json.dumps(c['ext'], ensure_ascii=False)}",
                 f"--- README ({c['readme_path']}, {c['readme_len']} chars{', TEMPLATE ONLY' if c['readme_is_template'] else ''}) ---",
                 c["readme"].strip() or "(нет README)",
                 "--- FILE TREE ---", *c["tree"],
                 "--- COMMIT SUBJECTS (oldest first) ---", *c["commit_subjects"],
                 f"########## END {c['name']}", ""]
        return "\n".join(lines)

    manifest = []
    cur, cur_len, idx = [], 0, 0

    def flush():
        nonlocal_idx = len(manifest)
        path = os.path.join(BATCH_DIR, f"batch_{nonlocal_idx:03d}.md")
        open(path, "w").write("\n".join(render(x) for x in cur))
        manifest.append({"path": path, "names": [x["name"] for x in cur]})

    for c in cards:
        l = len(render(c))
        if cur and (len(cur) >= BATCH or cur_len + l > 160_000):
            flush(); cur, cur_len = [], 0
        cur.append(c); cur_len += l
    if cur:
        flush()
    json.dump(manifest, open(os.path.join(SCR, "manifest.json"), "w"), ensure_ascii=False)
    # args for pipeline/workflows/01_analyze.js
    json.dump({"dir": BATCH_DIR, "counts": [len(m["names"]) for m in manifest]}, open(os.path.join(SCR, "analyze_args.json"), "w"))
    print("batches:", len(manifest), "cards:", len(cards), file=sys.stderr)
    hc = Counter(r["h_track"] for r in work)
    print("heuristic distribution:", sorted(hc.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)), file=sys.stderr)


if __name__ == "__main__":
    main()

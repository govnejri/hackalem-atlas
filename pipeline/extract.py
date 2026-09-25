#!/usr/bin/env python3
"""Extract structure, README and commit metadata from blobless bare clones."""
import json, os, re, subprocess, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

SCR = os.environ.get("WORK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")
CLONES = os.path.join(SCR, "clones")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SCR, "extracted.jsonl")  # usage: extract.py [out.jsonl] [names.txt]

BOT_RE = re.compile(r"\[bot\]|noreply@github\.com$|^github-actions", re.I)
SKIP_DIRS = ("node_modules/", ".venv/", "venv/", "env/", "__pycache__/", ".next/", "dist/",
             "build/", ".git/", "site-packages/", ".idea/", ".vscode/", "vendor/", ".gradle/",
             "Pods/", ".dart_tool/", "target/", ".pytest_cache/", ".mypy_cache/", "coverage/")
README_RE = re.compile(r"^readme(\.(md|markdown|rst|txt|mdx))?$", re.I)
AI_TRAILERS = {
    "claude": re.compile(r"co-authored-by:.*(claude|anthropic)", re.I),
    "copilot": re.compile(r"co-authored-by:.*copilot", re.I),
    "cursor": re.compile(r"co-authored-by:.*cursor", re.I),
    "codex": re.compile(r"co-authored-by:.*(codex|openai|chatgpt)", re.I),
    "gemini": re.compile(r"co-authored-by:.*(gemini|google-labs|jules)", re.I),
    "devin": re.compile(r"co-authored-by:.*devin", re.I),
}
AI_MSG = re.compile(r"generated with \[?claude code|🤖 generated with|claude\.com/claude-code|cursor agent|codex", re.I)

meta = {}
with open(os.path.join(SCR, "all_repos.jsonl")) as f:
    for line in f:
        r = json.loads(line)
        meta[r["name"]] = r


def git(repo, *args, check=False):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                       errors="replace", timeout=600,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout


def is_skipped(path):
    p = "/" + path
    return any(("/" + d) in p for d in SKIP_DIRS)


def extract(name):
    m = meta.get(name, {})
    repo = os.path.join(CLONES, name)
    rec = {
        "name": name,
        "team": re.sub(r"^Hackathon team repository for ", "", m.get("description") or ""),
        "url": m.get("html_url"),
        "created_at": m.get("created_at"),
        "pushed_at": m.get("pushed_at"),
        "size_kb": m.get("size"),
        "gh_language": m.get("language"),
        "clone_ok": os.path.isfile(os.path.join(repo, "HEAD")),
    }
    if not rec["clone_ok"]:
        err = os.path.join(CLONES, name + ".err")
        rec["clone_error"] = open(err).read()[-500:] if os.path.exists(err) else "missing"
        return rec
    head = git(repo, "rev-parse", "--verify", "-q", "HEAD").strip()
    refs = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    rec["branches"] = refs
    rec["default_branch"] = git(repo, "symbolic-ref", "--short", "HEAD").strip()
    if not head:
        rec["empty"] = True
        return rec
    rec["empty"] = False

    # --- commits (all branches) ---
    SEP, FS = "\x1e", "\x1f"
    log = git(repo, "log", "--all",
              f"--format={SEP}%H{FS}%aI{FS}%cI{FS}%an{FS}%ae{FS}%P{FS}%s{FS}%b")
    commits = []
    for chunk in log.split(SEP)[1:]:
        parts = chunk.split(FS)
        if len(parts) < 8:
            continue
        sha, ad, cd, an, ae, parents, subj, body = parts[:8]
        commits.append({"sha": sha[:8], "ad": ad, "cd": cd, "an": an, "ae": ae.lower(),
                        "merge": len(parents.split()) > 1, "s": subj.strip()[:200],
                        "b": body.strip()})
    human = [c for c in commits if "[bot]" not in c["an"] and "[bot]" not in c["ae"]]
    rec["commits_all"] = len(commits)
    rec["commits_human"] = len(human)
    rec["commits_merge"] = sum(c["merge"] for c in human)
    rec["commits_default"] = int(git(repo, "rev-list", "--count", "HEAD").strip() or 0)
    authors = Counter()
    names = {}
    for c in human:
        key = c["ae"] or c["an"].lower()
        authors[key] += 1
        names.setdefault(key, c["an"])
    rec["authors"] = [{"name": names[k], "email": k, "commits": n} for k, n in authors.most_common()]
    # dedupe authors by display name too (same person, different emails)
    rec["n_authors"] = len({names[k].strip().lower() for k in authors}) if authors else 0
    if human:
        cds = sorted(c["cd"] for c in human)
        ads = sorted(c["ad"] for c in human)
        rec["first_commit"] = ads[0]
        rec["last_commit"] = cds[-1]
        rec["last_author_date"] = ads[-1]
    ai = Counter()
    for c in human:
        for k, rx in AI_TRAILERS.items():
            if rx.search(c["b"]):
                ai[k] += 1
        if AI_MSG.search(c["b"]) and not any(rx.search(c["b"]) for rx in AI_TRAILERS.values()):
            ai["ai_msg_other"] += 1
    rec["ai_coauthored"] = dict(ai)
    rec["commits"] = [{"sha": c["sha"], "d": c["cd"], "a": c["an"], "s": c["s"]} for c in
                      sorted(human, key=lambda c: c["cd"])]

    # --- primary ref: default branch, unless it is near-empty and another branch holds the work ---
    ref = "HEAD"
    def kept_count(r):
        ps = [p for p in git(repo, "ls-tree", "-r", "--name-only", "-z", r).split("\0") if p]
        return len([p for p in ps if not is_skipped(p)])
    if len(refs) > 1:
        base_n = kept_count("HEAD")
        if base_n <= 5:
            best = max(((kept_count(b), git(repo, "log", "-1", "--format=%cI", b).strip(), b) for b in refs), default=None)
            if best and best[0] > base_n + 3:
                ref = best[2]
    rec["ref"] = ref if ref != "HEAD" else rec["default_branch"]
    rec["ref_is_default"] = ref == "HEAD"

    # --- tree ---
    paths = [p for p in git(repo, "ls-tree", "-r", "--name-only", "-z", ref).split("\0") if p]
    rec["n_files_total"] = len(paths)
    kept = [p for p in paths if not is_skipped(p)]
    rec["n_files"] = len(kept)
    junk = Counter()
    for p in paths:
        if is_skipped(p):
            for d in SKIP_DIRS:
                if ("/" + d) in ("/" + p):
                    junk[d.rstrip("/")] += 1
                    break
    rec["junk_dirs"] = dict(junk)
    ext = Counter()
    for p in kept:
        base = p.rsplit("/", 1)[-1]
        e = base.rsplit(".", 1)[-1].lower() if "." in base.lstrip(".") else "(none)"
        ext[e] += 1
    rec["ext"] = dict(ext.most_common(25))
    rec["top_level"] = sorted({p.split("/", 1)[0] + ("/" if "/" in p else "") for p in paths})
    lower = [p.lower() for p in paths]
    base_l = [p.rsplit("/", 1)[-1] for p in lower]

    def has(pred):
        return any(pred(p, b) for p, b in zip(lower, base_l))

    rec["flags"] = {
        "dockerfile": has(lambda p, b: b == "dockerfile" or b.endswith(".dockerfile")),
        "compose": has(lambda p, b: b.startswith("docker-compose") or b.startswith("compose.y")),
        "requirements": has(lambda p, b: b == "requirements.txt"),
        "pyproject": has(lambda p, b: b == "pyproject.toml"),
        "package_json": has(lambda p, b: b == "package.json" and "node_modules/" not in p),
        "notebook": has(lambda p, b: b.endswith(".ipynb")),
        "go_mod": has(lambda p, b: b == "go.mod"),
        "tests": has(lambda p, b: "/tests/" in "/" + p or "/test/" in "/" + p or b.startswith("test_") or ".test." in b or ".spec." in b or b.endswith("_test.go")),
        "ci": has(lambda p, b: p.startswith(".github/workflows/")),
        "env_committed": has(lambda p, b: b == ".env" or (b.startswith(".env.") and not any(x in b for x in ("example", "sample", "template", "dist")))),
        "env_example": has(lambda p, b: b.startswith(".env") and any(x in b for x in ("example", "sample", "template"))),
        "claude_md": has(lambda p, b: b == "claude.md" or p.startswith(".claude/")),
        "agents_md": has(lambda p, b: b == "agents.md"),
        "cursor": has(lambda p, b: p.startswith(".cursor/") or b == ".cursorrules"),
        "node_modules": "node_modules" in junk,
        "venv": any(k in junk for k in (".venv", "venv", "env", "site-packages")),
        "models": has(lambda p, b: b.endswith((".pt", ".pth", ".pkl", ".joblib", ".onnx", ".h5", ".cbm", ".safetensors", ".gguf"))),
        "data_files": has(lambda p, b: b.endswith((".csv", ".xlsx", ".parquet", ".json.gz"))),
        "audio": has(lambda p, b: b.endswith((".wav", ".mp3", ".ogg", ".m4a", ".webm", ".flac"))),
        "pdf_docs": has(lambda p, b: b.endswith((".pdf", ".docx", ".pptx"))),
        "makefile": has(lambda p, b: b in ("makefile", "justfile")),
        "tf_k8s": has(lambda p, b: b.endswith(".tf") or "/k8s/" in "/" + p or b == "helm"),
    }
    # tree for display: kept paths, capped
    rec["tree"] = kept[:3000]
    rec["tree_truncated"] = len(kept) > 3000

    # --- README ---
    root_readmes = [p for p in paths if "/" not in p and README_RE.match(p)]
    nested = sorted([p for p in kept if "/" in p and README_RE.match(p.rsplit("/", 1)[-1])],
                    key=lambda p: (p.count("/"), len(p)))
    rec["nested_readmes"] = nested[:30]
    pick = None
    if root_readmes:
        pick = sorted(root_readmes, key=lambda p: (not p.lower().endswith(".md"), p != "README.md"))[0]
    elif nested:
        pick = nested[0]
    rec["readme_path"] = pick
    if pick:
        txt = git(repo, "show", f"{ref}:{pick}")
        rec["readme_len"] = len(txt)
        rec["readme"] = txt[:80000]
        rec["readme_truncated"] = len(txt) > 80000
        tpl = f"# {name}\nHackathon team repository for {rec['team']}".strip()
        rec["readme_is_template"] = txt.strip() == tpl or (len(txt.strip()) < 120 and "Hackathon team repository for" in txt)
    # a couple of nested READMEs (short) for projects whose root README is template/empty
    if (not pick or rec.get("readme_is_template")) and nested:
        extra = []
        for p in nested[:3]:
            t = git(repo, "show", f"{ref}:{p}")
            extra.append({"path": p, "text": t[:30000]})
        rec["extra_readmes"] = extra
    return rec


def main():
    names = sorted(meta)
    if len(sys.argv) > 2:
        names = [n.strip() for n in open(sys.argv[2]) if n.strip()]
    with ThreadPoolExecutor(24) as ex, open(OUT, "w") as out:
        for i, rec in enumerate(ex.map(extract, names)):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 250 == 0:
                print(i, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Merge git extraction + LLM analysis (+ adjudication, synthesis) into the static site."""
import glob, json, os, re, statistics as st, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.join(ROOT, "work")
SCR = sys.argv[1] if len(sys.argv) > 1 else WORK             # folder with extracted.jsonl
ANALYSIS = os.path.join(WORK, "analysis.json")                # {name: repo analysis}
ADJ = os.path.join(WORK, "adjudication.json")                 # {name: {status, track, confidence, reason}}
SYN = os.path.join(WORK, "synthesis.json")                    # {tracks: {id: {...}}, overview: {...}}
OUT = os.path.join(ROOT, "site")
ART = os.path.join(ROOT, "artifact")                          # same page as a claude.ai Artifact fragment
KZ = timezone(timedelta(hours=5))
DEADLINE = datetime(2026, 9, 23, 18, 0, tzinfo=KZ)
WIN0 = datetime(2026, 9, 23, 12, 0, tzinfo=KZ)

TRACKS = [
    (1, "Энергетика", "Самрук-Казына", "Прогноз ветровой генерации", "AI-агент, прогнозирующий выработку ветровой электростанции по погодным данным"),
    (2, "Финансы", "Freedom", "«Граф денег» (AML)", "«Граф денег»: восстановить структуру организованной группы по сети транзакций (AML)"),
    (3, "Менеджмент", "Halyk Bank · кейс 1", "Career Quest", "«Career Quest»: AI-навигатор, связывающий навыки сотрудника с шагами развития"),
    (4, "Телеком", "Beeline", "Тарифы и ARPU", "Агент, который решает, каким абонентам какой тариф предложить (чистый прирост ARPU)"),
    (5, "Логистика", "Электрокомплект · ekt.kz", "Пополнение склада", "Автоматический расчёт заказов поставщикам для пополнения склада, с утверждением менеджером"),
    (6, "Креативные индустрии", "Firebird", "#79-lite: подрядчики", "«#79-lite»: подобрать до 3 подрядчиков для мероприятия и объяснить выбор"),
    (7, "Образование", "AI Sana", "Challenge Hub", "Challenge Hub: превратить задачу бизнеса в задание для студенческих команд"),
    (8, "Инновации", "Самрук-Казына", "«Хаттама»: протоколы", "«Хаттама»: протокол и поручения по аудиозаписи совещания (каз./рус./смешанная речь)"),
    (9, "Коммуникации", "Halyk Bank · кейс 2", "Voice Router", "«Voice Router»: голосовой AI, маршрутизирующий звонки в контакт-центре страховой компании"),
    (10, "Торговля", "Электрокомплект · ekt.kz", "AI-консультант по каталогу", "AI-консультант по каталогу ekt.kz: товары, аналоги, цены, остатки, корзина"),
    (11, "Спецтрек", "Казахтелеком", "Сравнение оргструктур", "Агент, сравнивающий документы оргструктуры до и после реорганизации"),
    (12, "Спецтрек", "Astana Innovations", "«Аким на 5 часов»", "«Аким на 5 часов»: городской симулятор, распределяющий бюджет по 5 направлениям и 5 районам"),
]

# provider normalisation: first match wins per pattern, a repo can have several providers
PROVIDERS = [
    ("OpenAI GPT", r"gpt|openai|chatgpt|\bo[134](-mini)?\b|text-embedding|responses api|4o|4\.1"),
    ("Anthropic Claude", r"claude|anthropic|sonnet|opus|haiku"),
    ("Google Gemini/Gemma", r"gemini|gemma|google|vertex"),
    ("Whisper (STT)", r"whisper"),
    ("Meta Llama", r"llama"),
    ("Qwen", r"qwen"),
    ("DeepSeek", r"deepseek"),
    ("Mistral", r"mistral|mixtral|pixtral"),
    ("KazLLM / ISSAI / AlemLLM", r"kazllm|issai|alem|sherkala|kaz-?llm|kazakh.?llm"),
    ("Groq", r"\bgroq\b"),
    ("xAI Grok", r"\bgrok\b"),
    ("OpenRouter", r"openrouter"),
    ("Ollama (локально)", r"ollama"),
    ("Yandex", r"yandex|yagpt|speechkit"),
    ("NVIDIA NIM", r"nvidia|\bnim\b|nemotron"),
    ("GigaChat", r"gigachat|sber"),
    ("ElevenLabs", r"elevenlabs"),
    ("Hugging Face", r"hugging ?face|sentence-transformers|\bbge\b|e5-|minilm|multilingual-e5"),
    ("pyannote (диаризация)", r"pyannote"),
]
MODEL_RX = re.compile(
    r"(gpt-?[0-9][0-9.]*o?(?:-(?:mini|nano|luna|sol|astra|turbo|pro|transcribe|tts|realtime|search|codex|audio))*)"
    r"|(o[134](?:-mini)?)(?![\w.])"
    r"|(text-embedding-3-(?:small|large))"
    r"|((?:faster-)?whisper[- ]?(?:large-v3-turbo|large-v3|large-v2|large|medium|small|base|tiny|turbo)?)"
    r"|(claude[- ](?:opus|sonnet|haiku)?[- ]?[0-9.]*(?:[- ](?:opus|sonnet|haiku))?)"
    r"|(gemini[- ][0-9.]+[- ]?(?:flash-lite|flash|pro)?)"
    r"|(llama[- ]?[0-9.]+(?:-[0-9]+b)?)"
    r"|(qwen[0-9.]*(?:-[0-9.]+b)?)"
    r"|(deepseek(?:-[a-z0-9]+)?)"
    r"|(pyannote)", re.I)


def models_of(llms):
    out = []
    for s in llms or []:
        for m in MODEL_RX.finditer(s):
            v = m.group(0).lower().strip(" -").replace("faster-whisper", "whisper").replace(" ", "-")
            if v.startswith("gpt") and not v.startswith("gpt-"):
                v = "gpt-" + v[3:]
            if v in ("whisper", "whisper-"):
                v = "whisper"
            if v not in out:
                out.append(v)
    return out


OTHER_GROUPS = [
    ("FAQ-бот в терминале", r"faq"),
    ("Классификатор обращений", r"классификатор|classif"),
    ("Фильтр алертов «Тихий пульт»", r"алерт|alert|тихий пульт"),
    ("Детектор дефектов (OK/DEFECT)", r"дефект|defect"),
    ("Трекер расходов студента", r"расход|expense|бюджет студент"),
    ("Учебные материалы по лекции", r"лекци|конспект|карточ"),
]


def other_groups(desc):
    d = (desc or "").lower()
    g = [name for name, rx in OTHER_GROUPS if re.search(rx, d)]
    return g or ["Другое"]


def flags_from_tree(tree, old):
    lower = [p.lower() for p in tree]
    base = [p.rsplit("/", 1)[-1] for p in lower]
    pairs = list(zip(lower, base))
    has = lambda f: any(f(p, b) for p, b in pairs)
    f = dict(old or {})
    f.update({
        "dockerfile": has(lambda p, b: b == "dockerfile" or b.endswith(".dockerfile")),
        "compose": has(lambda p, b: b.startswith("docker-compose") or b.startswith("compose.y")),
        "requirements": has(lambda p, b: b == "requirements.txt"),
        "pyproject": has(lambda p, b: b == "pyproject.toml"),
        "package_json": has(lambda p, b: b == "package.json"),
        "notebook": has(lambda p, b: b.endswith(".ipynb")),
        "go_mod": has(lambda p, b: b == "go.mod"),
        "tests": has(lambda p, b: "/tests/" in "/" + p or "/test/" in "/" + p or "/__tests__/" in "/" + p or b.startswith("test_") or ".test." in b or ".spec." in b or b.endswith("_test.go") or b.endswith("_test.py")),
        "ci": has(lambda p, b: p.startswith(".github/workflows/")),
        "models": has(lambda p, b: b.endswith((".pt", ".pth", ".pkl", ".joblib", ".onnx", ".h5", ".cbm", ".safetensors", ".gguf"))),
        "data_files": has(lambda p, b: b.endswith((".csv", ".xlsx", ".parquet", ".json.gz"))),
        "audio": has(lambda p, b: b.endswith((".wav", ".mp3", ".ogg", ".m4a", ".webm", ".flac"))),
        "pdf_docs": has(lambda p, b: b.endswith((".pdf", ".docx", ".pptx"))),
    })
    return f


# ---- redaction: never point at repos with committed secrets, never name teams for timing suspicions ----
SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ«(`*h])")
SECRET_WHAT = re.compile(r"(\.env\b|api[_ -]?key|(?<!без )(?<!без api-)(?<!без api )(?<![а-яё])ключ(?!ев)|(?<![а-яё])токен(?!из)|\btoken\b|секрет|secret|(?<![а-яё])парол|password|credential)", re.I)
SECRET_HOW = re.compile(r"(закоммич|коммит\w* с ключ|лежит в (дереве|репозитори|корне)|в дереве|в истори|утеч|утек|открытым текстом|опубликован|выложен|передава|раздава|оказал\w* в репозитори|попал\w* в (репозитори|git)|включ[её]н\w* \.env|hardcod|захардкож|committed|в git\b|в публичн)", re.I)
SECRET_IDS = set()   # repo ids with committed .env / masked keys — filled in main()
TIMING_WHAT = re.compile(r"(коммит|залит|залива|заливк|импортир|перенес)", re.I)
TIMING_WHEN = re.compile(r"(после 18:00|до старта|до начала|перед дедлайном|в конце дня|за последние|после окончания|в 07:\d\d|одним коммитом|тремя коммитами|3[–-]4 коммитами|за \d+ минут|с 22\.09|готового кода)", re.I)
NAME_RX = re.compile(r"`?hack-[0-9a-f]{8}[a-z0-9-]*`?")
HIDDEN = "[скрыто]"


def is_secret_sentence(x):
    if not SECRET_WHAT.search(x):
        return False
    if SECRET_HOW.search(x):
        return True
    # any sentence that talks about keys/.env and names a repo known to hold secrets
    return any(m.group(0).strip("`").split("-")[1] in SECRET_IDS for m in NAME_RX.finditer(x))


def redact_names(text):
    if not text:
        return text
    out = []
    for sent in SENT_SPLIT.split(text):
        if is_secret_sentence(sent) or (TIMING_WHAT.search(sent) and TIMING_WHEN.search(sent)):
            sent = NAME_RX.sub(HIDDEN, sent)
            sent = re.sub(r"\[скрыто\](?:(?:,\s*|\s+и\s+|,\s*а также\s+)\[скрыто\])+", "[скрыто]", sent)
        out.append(sent)
    return " ".join(out)


def drop_secret_sentences(text):
    """Remove sentences about committed secrets (used for per-repo texts and standout blurbs)."""
    if not text:
        return text
    return " ".join(x for x in SENT_SPLIT.split(text) if not is_secret_sentence(x)).strip()


def redact_syn(syn):
    for t in syn.get("tracks", {}).values():
        t["headline"] = redact_names(t["headline"])
        for k in ("tips", "pitfalls", "organizers"):
            t[k] = [redact_names(x) for x in t.get(k, [])]
        for a in t.get("approaches", []):
            a["description"] = redact_names(a["description"])
        for so in t.get("standouts", []):
            so["why"] = redact_names(drop_secret_sentences(so["why"]))
    ov = syn.get("overview", {})
    for k in list(ov):
        ov[k] = [redact_names(x) for x in ov[k]]
    return syn


KEY_PATTERNS = [
    re.compile(r"\bsk-(?:proj-|svcacct-|admin-|ant-(?:api\d+-)?)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\br8_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
KEY_ASSIGN = re.compile(r"((?:[A-Za-z0-9_]*(?:api[_-]?key|apikey|access[_-]?key|_key|secret|token|password|passwd|pwd)|пароль|ключ|токен)[\"'`*_]*\s*[:=][\s\"'`*_]*)([A-Za-z0-9_\-\.\/+]{8,})", re.I)
URL_USERINFO = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)@(?!(?:localhost|127\.0\.0\.1|0\.0\.0\.0|db|postgres|redis|mongo|mysql|rabbitmq|minio)[:/])", re.I)
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
EMAIL_KEEP_DOMAIN = re.compile(r"(^|\.)(example\.[a-z]+|[a-z0-9-]+\.(test|local|invalid|example|localhost)|localhost|github\.com|users\.noreply\.github\.com|noreply\.[a-z.]+|demo\.kz|test\.kz|mail\.test)$", re.I)
EMAIL_KEEP_LOCAL = re.compile(r"^(demo|admin|user|test|owner|analyst|example|info|support|noreply|no-reply|manager|jury|hr|review[\w-]*|first|second|guest|e\d+|user\d+|demo\d+|git)$", re.I)


def mask_email(text, all_=False):
    def m(x):
        v = x.group(0)
        local, dom = v.rsplit("@", 1)
        if not all_ and (EMAIL_KEEP_DOMAIN.search(dom) or EMAIL_KEEP_LOCAL.match(local)):
            return v
        MASKED[0] += 1
        return "[email скрыт]"
    return EMAIL_RX.sub(m, text or "")
KEY_LABEL = re.compile(r"((?<!\w)(?:guest\s+)?(?:парол[ьяие]|password|passwd)(?!\w)[^\n`|]{0,24}?[:=]?\s*[*_]*\s*`|(?<!\w)(?:токен\s+по\s+умолчанию|token|secret|ключ(?:\s+api)?|api[ _-]?key)(?!\w)\s*[*_]*\s*[:=]\s*[*_]*\s*`)([^`\s]{8,})(`)", re.I)
KEY_PAIR = re.compile(r"((?:логин|login|user(?:name)?)[^\n]{0,90}?`[^`\s]{2,40}`\s*/\s*`)([^`\s]{8,})(`)", re.I)
KEY_QUERY = re.compile(r"([?&](?:key|api_key|apikey|token|access_token)=)([A-Za-z0-9_\-]{16,})", re.I)
MASKED = [0]


def audit(summary, details):
    """Fail the build if anything that must never be published slipped through."""
    problems = []
    texts = []
    for t in summary["tracks"]:
        y = t.get("syn") or {}
        texts += [y.get("headline", "")] + y.get("tips", []) + y.get("pitfalls", []) + y.get("organizers", [])
        texts += [a["description"] for a in y.get("approaches", [])] + [so["why"] for so in y.get("standouts", [])]
    for v in (summary.get("overview") or {}).values():
        texts += v
    for x in texts:
        for sent in SENT_SPLIT.split(x):
            if SECRET_WHAT.search(sent) and any(m.group(0).strip("`").split("-")[1] in SECRET_IDS for m in NAME_RX.finditer(sent)):
                problems.append("secret repo named: " + sent[:120])
    for r in summary["repos"]:
        for k in ("su", "ap", "no", "ev"):
            if any(is_secret_sentence(x) for x in SENT_SPLIT.split(r.get(k) or "")):
                problems.append(f"secret sentence in {r['id']}.{k}")
    for tk, D in details.items():
        for rid, d in D.items():
            blob = " ".join([d["rd"]] + [x["t"] for x in d["rx"]])
            for rx in KEY_PATTERNS:
                if rx.search(blob):
                    problems.append(f"key pattern left in {rid}")
            for n, _ in d["au"]:
                if EMAIL_RX.search(n or ""):
                    problems.append(f"author e-mail in {rid}")
            for c in d["cm"]:
                if EMAIL_RX.search(c[1] or "") or EMAIL_RX.search(c[2] or ""):
                    problems.append(f"commit e-mail in {rid}")
    if problems:
        raise SystemExit("AUDIT FAILED:\n  " + "\n  ".join(problems[:40]))


def safe_author(name):
    return "автор (email скрыт)" if EMAIL_RX.search(name or "") else name


def mask_keys(text):
    if not text:
        return text
    def m(x):
        MASKED[0] += 1
        return x.group(0)[:6] + "…[ключ скрыт]"
    for rx in KEY_PATTERNS:
        text = rx.sub(m, text)
    def is_placeholder(v):
        low = v.lower()
        return bool(re.fullmatch(r"(your|xxx|<|example|changeme|placeholder|test|dummy|sk-\.\.\.)[\w\-\.]*", v, re.I)
                    or low.startswith(("your_", "your-", "xxxx", "replace", "insert", "put_", "change", "none", "null", "true", "false",
                                       "http", "localhost", "os.", "env.", "process.", "settings.", "config.", "self.", "st.secrets", "${", "$("))
                    or re.fullmatch(r"[a-z]+(?:[-_.][a-z]+)*", v)      # plain words: hr-demo, secret_value
                    or re.fullmatch(r"[A-Z_]+", v)                     # env var names: OPENAI_API_KEY
                    or re.fullmatch(r"[A-Z][a-z]+-[A-Z][A-Za-z]+", v)  # PowerShell cmdlets: Read-Host
                    or "/" in v or re.search(r"\.(json|env|md|py|ts|js|txt|ya?ml|toml|local|example)$", v, re.I))  # paths and files

    def ma(x):
        v = x.group(2)
        if is_placeholder(v):
            return x.group(0)
        MASKED[0] += 1
        return x.group(1) + "[скрыто]" + (x.group(3) if x.re in (KEY_LABEL, KEY_PAIR) else "")
    text = URL_USERINFO.sub(lambda x: (MASKED.__setitem__(0, MASKED[0] + 1), x.group(1) + "[скрыто]@")[1], text)
    text = KEY_PAIR.sub(ma, text)
    text = KEY_LABEL.sub(ma, text)
    text = KEY_ASSIGN.sub(ma, text)
    text = KEY_QUERY.sub(ma, text)
    text = mask_email(text)
    # personal identifiers: IIN-shaped numbers (YYMMDD + 6 digits) and non-dummy KZ phone numbers
    def iin(x):
        v = x.group(0)
        mm, dd = int(v[2:4]), int(v[4:6])
        if 1 <= mm <= 12 and 1 <= dd <= 31 and len(set(v[6:])) > 2:
            MASKED[0] += 1
            return "[ИИН скрыт]"
        return v
    text = re.sub(r"(?<![\d-])\d{12}(?![\d-])", iin, text)
    def phone(x):
        digits = re.sub(r"\D", "", x.group(0))
        if re.search(r"0{5,}|(\d)\1{5,}", digits[1:]):
            return x.group(0)
        MASKED[0] += 1
        return "[телефон скрыт]"
    text = re.sub(r"(?:\+7|(?<!\d)8)[\s(-]*7\d{2}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)", phone, text)
    return text


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#0B6E69"/>
<g fill="#DCEFEC">
<rect x="11" y="10" width="11" height="9" rx="2"/><rect x="26.5" y="10" width="11" height="9" rx="2"/><rect x="42" y="10" width="11" height="9" rx="2"/>
<rect x="11" y="22" width="11" height="9" rx="2"/><rect x="26.5" y="22" width="11" height="9" rx="2"/><rect x="42" y="22" width="11" height="9" rx="2" fill="#E2AF47"/>
<rect x="11" y="34" width="11" height="9" rx="2"/><rect x="26.5" y="34" width="11" height="9" rx="2"/><rect x="42" y="34" width="11" height="9" rx="2"/>
<rect x="11" y="46" width="11" height="9" rx="2"/><rect x="26.5" y="46" width="11" height="9" rx="2"/><rect x="42" y="46" width="11" height="9" rx="2"/>
</g></svg>
"""


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def loc(s):
    return datetime.fromisoformat(s).astimezone(KZ)


def main():
    ext = {}
    for line in open(os.path.join(SCR, "extracted.jsonl")):
        r = json.loads(line)
        ext[r["name"]] = r
    ana = json.load(open(ANALYSIS))
    adj = json.load(open(ADJ)) if os.path.exists(ADJ) else {}
    for name, e in ext.items():
        if not e.get("commits_human"):
            continue
        before = MASKED[0]
        mask_keys(e.get("readme") or "")
        tree_env = any(re.search(r"(^|/)\.env(\.(?!example|sample|template|dist)[\w.-]+)?$", p) for p in e.get("tree", []))
        if (e.get("flags") or {}).get("env_committed") or tree_env or MASKED[0] > before:
            SECRET_IDS.add(name.split("-")[1])
        MASKED[0] = before
    syn = redact_syn(json.load(open(SYN))) if os.path.exists(SYN) else {"tracks": {}, "overview": {}}

    repos, details = [], defaultdict(dict)
    all_authors = set()
    pulse_start = datetime(2026, 9, 23, 11, 0, tzinfo=KZ)
    nb = 8 * 6  # 11:00 → 19:00 in 10-min bins
    pulse = [0] * nb
    pulse_repos = [set() for _ in range(nb)]
    total_commits = in_window = 0
    late_repos = late_commits = 0
    bot_only = 0

    for name, e in sorted(ext.items()):
        if not e.get("commits_human"):
            bot_only += 1
            continue
        a = ana.get(name)
        if a is None:
            print("WARN no analysis for", name, file=sys.stderr)
            a = {"status": "unclear", "track": 0, "confidence": "low", "evidence": "нет анализа"}
        a = dict(a)
        if name in adj:
            j = adj[name]
            a["status"], a["track"], a["confidence"] = j["status"], j["track"], j.get("confidence", a.get("confidence"))
            a["evidence"] = j.get("reason") or a.get("evidence")
            a["_adj"] = True
        if a["status"] != "case":
            a["track"] = 0
        rid = name.split("-")[1]
        commits = e.get("commits", [])
        late = pre = last10 = 0
        for c in commits:
            d = loc(c["d"])
            if DEADLINE - timedelta(minutes=10) <= d < DEADLINE:
                last10 += 1
            total_commits += 1
            if WIN0 <= d < DEADLINE:
                in_window += 1
            if d >= DEADLINE:
                late += 1
            if d < WIN0:
                pre += 1
            i = int((d - pulse_start).total_seconds() // 600)
            if 0 <= i < nb:
                pulse[i] += 1
                pulse_repos[i].add(rid)
        if late:
            late_repos += 1
            late_commits += late
        for au in e.get("authors", []):
            all_authors.add(au["email"] or au["name"].lower())
        llm_text = " ".join(a.get("llms") or []).lower()
        prov = [p for p, rx in PROVIDERS if re.search(rx, llm_text)]
        mdl = models_of(a.get("llms"))
        ai = e.get("ai_coauthored") or {}
        rec = {
            "id": rid, "n": name, "t": e.get("team") or name, "tr": a["track"], "st": a["status"],
            "cf": a.get("confidence"), "ev": drop_secret_sentences(a.get("evidence", "")), "adj": bool(a.get("_adj")),
            "pn": a.get("project_name") or "", "su": drop_secret_sentences(a.get("summary") or ""), "ap": drop_secret_sentences(a.get("approach") or ""),
            "co": a.get("core") or [], "te": a.get("techniques") or [], "ll": a.get("llms") or [],
            "sk": a.get("stack") or [], "ma": a.get("maturity") or "prototype", "rq": a.get("readme_quality", 0),
            "ru": bool(a.get("has_run_instructions")), "de": bool(a.get("has_demo_link")),
            "me": a.get("metrics") or "", "no": drop_secret_sentences(a.get("notable") or ""), "la": a.get("readme_lang"),
            "ot": a.get("other_task_desc") or "", "pv": prov, "md": mdl,
            "og": other_groups(a.get("other_task_desc")) if a["status"] == "other_task" else [],
            "c": e["commits_human"], "cm": e.get("commits_merge", 0), "a": e.get("n_authors", 0),
            "f": e.get("n_files", 0), "br": len(e.get("branches") or []),
            "fc": loc(e["first_commit"]).isoformat()[:16] if e.get("first_commit") else None,
            "lc": loc(e["last_commit"]).isoformat()[:16] if e.get("last_commit") else None,
            "late": late, "pre": pre, "l10": last10, "ai": sum(v for k, v in ai.items()), "aik": sorted(k for k in ai if k != "ai_msg_other") or (["другое"] if ai else []),
            "fl": [k for k, v in flags_from_tree(e.get("tree", []), e.get("flags")).items() if v and k != "env_committed"],
            "rf": e.get("ref") if e.get("ref_is_default") is False else None,
            "ex": dict(list((e.get("ext") or {}).items())[:12]), "rl": e.get("readme_len", 0) if not e.get("readme_is_template") else 0,
        }
        repos.append(rec)
        tkey = rec["tr"] if rec["st"] == "case" else 0
        details[tkey][rid] = {
            "rd": mask_keys(e.get("readme") or ""), "rp": e.get("readme_path"), "rtr": bool(e.get("readme_truncated")),
            "rx": [{"p": x["path"], "t": mask_keys(x["text"])} for x in e.get("extra_readmes", [])],
            "tr": e.get("tree", [])[:3000], "tt": bool(e.get("tree_truncated")), "jk": e.get("junk_dirs") or {},
            "cm": [[loc(c["d"]).isoformat()[:16], safe_author(c["a"]), mask_email(mask_keys(c["s"]), all_=True)] for c in commits],
            "au": [[safe_author(x["name"]), x["commits"]] for x in e.get("authors", [])],
            "bn": e.get("branches") or [],
        }

    case = [r for r in repos if r["st"] == "case"]
    tracks = []
    for tid, ind, partner, short, task in TRACKS:
        rs = [r for r in case if r["tr"] == tid]
        n = len(rs)
        pc = Counter(p for r in rs for p in r["pv"])
        mc = Counter(m for r in rs for m in r["md"])
        tc = Counter()
        for r in rs:
            for t in dict.fromkeys(x.strip() for x in r["te"]):
                tc[t] += 1
        cc = Counter(c for r in rs for c in r["co"] if c != "other")
        tracks.append({
            "id": tid, "industry": ind, "partner": partner, "short": short, "task": task, "n": n,
            "med_commits": round(st.median([r["c"] for r in rs])) if rs else 0,
            "med_authors": round(st.median([r["a"] for r in rs])) if rs else 0,
            "mvp": sum(r["ma"] in ("working_mvp", "polished") for r in rs),
            "rq2": sum(r["rq"] >= 2 for r in rs),
            "docker": sum(("dockerfile" in r["fl"]) or ("compose" in r["fl"]) for r in rs),
            "metrics": sum(bool(r["me"]) for r in rs),
            "providers": [{"name": k, "n": v} for k, v in sorted(pc.items(), key=lambda kv: (-kv[1], kv[0]))],
            "top_tech": [{"name": k, "n": v} for k, v in sorted(tc.items(), key=lambda kv: (-kv[1], kv[0]))[:14] if v >= 2],
            "models": [{"name": k, "n": v} for k, v in sorted(mc.items(), key=lambda kv: (-kv[1], kv[0]))[:10]],
            "top_core": [k for k, _ in cc.most_common(2)],
            "syn": syn.get("tracks", {}).get(str(tid)),
        })

    active = len(repos)
    fl = Counter(f for r in repos for f in r["fl"])
    ai_repos = sum(1 for r in repos if r["ai"])
    claude_repos = sum(1 for r in repos if "claude" in r["aik"])
    tooling = [
        {"l": "Есть тесты", "n": fl["tests"]},
        {"l": ".env.example", "n": fl["env_example"]},
        {"l": "Dockerfile или compose", "n": sum(1 for r in repos if "dockerfile" in r["fl"] or "compose" in r["fl"])},
        {"l": "AGENTS.md", "n": fl["agents_md"]},
        {"l": "CLAUDE.md / .claude/", "n": fl["claude_md"]},
        {"l": "Коммиты с Co-Authored-By AI", "n": ai_repos},
        {"l": "CI (GitHub Actions)", "n": fl["ci"]},
        {"l": "Больше одной ветки", "n": sum(1 for r in repos if r["br"] > 1)},
        {"l": ".env закоммичен", "n": sum(1 for x in ext.values() if x.get("commits_human") and (x.get("flags") or {}).get("env_committed")), "warn": True},
        {"l": "node_modules / venv в git", "n": sum(1 for r in repos if "node_modules" in r["fl"] or "venv" in r["fl"]), "warn": True},
    ]
    sizes = Counter(min(r["a"], 6) for r in repos)

    def top(key, label, unit, k=3):
        rs = sorted(case, key=lambda r: -r[key])[:k]
        return {"label": label, "unit": unit, "items": [{"id": r["id"], "v": r[key]} for r in rs if r[key]]}
    records = [
        top("c", "Больше всего коммитов", "коммитов"),
        top("br", "Больше всего веток", "веток"),
        top("rl", "Самый длинный README", "символов"),
        top("f", "Больше всего файлов", "файлов"),
        top("ai", "Больше всего коммитов с AI-соавтором", "коммитов"),
        top("l10", "Больше всего коммитов за последние 10 минут", "коммитов"),
    ]
    prov_all = Counter(p for r in case for p in r["pv"])
    model_all = Counter(m for r in case for m in r["md"])
    # numbers for the "О разборе" page
    heur_p = os.path.join(WORK, "heuristic.json")
    fc_p = os.path.join(WORK, "factcheck_changes.json")
    about = {"masked": 0, "branch_fixed": sum(1 for x in ext.values() if x.get("commits_human") and x.get("ref_is_default") is False),
             "agents_analyze": 94,
             "disputed": json.load(open(os.path.join(WORK, "adjudication_meta.json")))["disputed"] if os.path.exists(os.path.join(WORK, "adjudication_meta.json")) else len(adj),
             "changed": sum(1 for n, j in adj.items() if n in ana and (ana[n]["status"], ana[n]["track"] if ana[n]["status"] == "case" else 0) != (j["status"], j["track"] if j["status"] == "case" else 0))}
    if os.path.exists(heur_p):
        heur = json.load(open(heur_p))
        cr = [(n, a) for n, a in ana.items() if a["status"] == "case" and n in heur]
        about["agree_pct"] = round(100 * sum(1 for n, a in cr if heur[n]["h_track"] == a["track"]) / max(1, len(cr)))
    if os.path.exists(fc_p):
        fc = json.load(open(fc_p))
        about["fixes_avg"] = round(sum(len(x["changes"]) for x in fc) / max(1, len(fc)))
    summary = {
        "generated": "2026-09-25",
        "about": about,
        "totals": {
            "repos": len(ext), "active": active, "bot_only": bot_only, "case_repos": len(case),
            "commits": total_commits, "in_window_pct": round(100 * in_window / max(1, total_commits)),
            "median_commits": round(st.median([r["c"] for r in repos])), "authors_total": len(all_authors),
            "late_repos": late_repos, "late_commits": late_commits, "ai_repos": ai_repos, "claude_repos": claude_repos,
        },
        "pulse": {"start": "11:00", "step": 10, "bins": pulse, "repos": [len(s) for s in pulse_repos],
                  "deadline_idx": 7 * 6},
        "tracks": tracks,
        "providers": [{"name": k, "n": v} for k, v in prov_all.most_common()],
        "models": [{"name": k, "n": v} for k, v in model_all.most_common(20)],
        "team_sizes": [{"k": str(k), "n": sizes[k]} for k in range(1, 7)],
        "tooling": tooling,
        "records": records,
        "overview": syn.get("overview", {}),
        "other_groups": [{"name": k, "n": v} for k, v in Counter(g for r in repos for g in r["og"]).most_common()],
        "repos": repos,
    }
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    for f in glob.glob(os.path.join(OUT, "data", "t*.json")):
        os.remove(f)
    for k, v in details.items():
        with open(os.path.join(OUT, "data", f"t{k}.json"), "w") as fh:
            fh.write(json.dumps(v, ensure_ascii=False, separators=(",", ":")).replace("\ufffd", ""))
    summary["about"]["masked"] = MASKED[0]
    audit(summary, details)
    tpl = open(os.path.join(HERE, "template.html")).read()
    blob = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\ufffd", "")
    head, body = tpl.replace("/*__SUMMARY__*/", blob).split("<!--BODY-->", 1)
    T = summary["totals"]
    nf = f"{T['case_repos']:,}".replace(",", "\u00a0")
    desc = (f"Как {nf} {plural(T['case_repos'], 'команда', 'команды', 'команд')} финала HackAlem.ai решали 12 кейсов: подходы, сильные решения, советы, "
            f"статистика и README, структура и коммиты каждого проекта.")
    standalone = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0B6E69">
<meta property="og:type" content="website">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="Атлас решений HackAlem">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<script>try{{var t=localStorage.getItem('theme');if(t==='dark'||t==='light')document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}</style>
{head.strip()}
</head>
<body data-standalone="1">
{body.strip()}
</body>
</html>
"""
    standalone = standalone.replace('<meta name="description" content="', '<meta name="description" content="', 1)
    open(os.path.join(OUT, "index.html"), "w").write(standalone)
    open(os.path.join(OUT, ".nojekyll"), "w").write("")
    open(os.path.join(OUT, "favicon.svg"), "w").write(FAVICON)
    html = head + body
    os.makedirs(ART, exist_ok=True)
    open(os.path.join(ART, "index.html"), "w").write(html)
    json.dump(summary, open(os.path.join(WORK, "summary.json"), "w"), ensure_ascii=False, indent=1)
    print(f"repos={active} case={len(case)} html={len(html)/1e6:.2f}MB masked_keys={MASKED[0]}", file=sys.stderr)
    for t in tracks:
        print(f"  t{t['id']:>2} {t['industry']:<22} {t['n']:>4}", file=sys.stderr)
    print("  other:", Counter(r["st"] for r in repos if r["st"] != "case"), file=sys.stderr)
    for k in sorted(details):
        p = os.path.join(OUT, "data", f"t{k}.json")
        print(f"  t{k}.json {os.path.getsize(p)/1e6:.2f}MB", file=sys.stderr)


if __name__ == "__main__":
    main()

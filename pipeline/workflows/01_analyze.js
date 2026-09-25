export const meta = {
  name: 'hackalem-repo-analyze',
  description: 'Classify every HackAlem.ai team repo into one of 12 case tracks and summarize how each team solved it (README + file tree + commit subjects)',
  phases: [
    { title: 'Analyze', detail: 'one agent per batch card file; classify + summarize each repo' },
    { title: 'Backfill', detail: 'retry repos a batch agent skipped' },
  ],
}

const DIR = args.dir // absolute path to work/batches
const COUNTS = args.counts

const TRACKS = `
The HackAlem.ai final (a 5-hour sprint on 2026-09-23, ~13:00–18:00 Astana time) had exactly 12 cases:
 1  Энергетика — Самрук-Казына — AI-агент, прогнозирующий выработку ВЕТРОВОЙ электростанции по погодным данным
 2  Финансы — Freedom — «Граф денег»: восстановить структуру организованной группы по сети транзакций (AML)
 3  Менеджмент — Halyk Bank (кейс 1) — «Career Quest»: AI-навигатор, связывающий навыки сотрудника с шагами развития
 4  Телеком — Beeline — агент, который решает, каким абонентам какой тариф предложить (чистый прирост ARPU)
 5  Логистика — Электрокомплект (ekt.kz) — автоматический расчёт заказов поставщикам для пополнения склада, с утверждением менеджером
 6  Креативные индустрии — Firebird — «#79-lite»: подобрать до 3 подрядчиков для мероприятия и объяснить выбор
 7  Образование — AI Sana — Challenge Hub: превратить задачу бизнеса в задание для студенческих команд
 8  Инновации — Самрук-Казына — «Хаттама»: протокол и поручения по аудиозаписи совещания (каз./рус./смешанная речь)
 9  Коммуникации — Halyk Bank (кейс 2) — «Voice Router»: голосовой AI, маршрутизирующий звонки в контакт-центре страховой компании
10  Торговля — Электрокомплект (ekt.kz) — AI-консультант по каталогу ekt.kz: товары, аналоги, цены, остатки, корзина
11  Спецтрек — Казахтелеком — агент, сравнивающий документы оргструктуры до и после реорганизации
12  Спецтрек — Astana Innovations — «Аким на 5 часов»: городской симулятор, распределяющий бюджет по 5 направлениям и 5 районам
Commonly confused pairs: 5 (supplier replenishment ORDERS, internal, manager approval) vs 10 (customer-facing CATALOG consultant/chat, cart);
3 (HR career/skills navigator) vs 9 (voice call routing in insurance contact centre); 1 (wind power forecast) vs 8 (meeting audio → protocol);
11 (compare org-structure documents before/after) vs anything HR-ish; 12 (city budget simulator game) vs generic dashboards.
Some repos are NOT final cases: e.g. a qualifier/warm-up round held earlier (commits on 2026-09-21 or earlier; tasks like message classifier,
terminal FAQ bot, alert filter, defect detector), unrelated projects, or empty/template-only repos.`

const REPO = {
  type: 'object',
  properties: {
    name: { type: 'string', description: 'exact repo name after "REPO:"' },
    status: { type: 'string', enum: ['case', 'other_task', 'no_content', 'unclear'], description: 'case = one of the 12 final cases; other_task = qualifier/other assignment/unrelated project; no_content = template/empty/near-empty; unclear = has content but case cannot be determined' },
    track: { type: 'integer', minimum: 0, maximum: 12, description: '1..12 when status=case, else 0' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    evidence: { type: 'string', description: 'short quote or concrete reason for the track (<=200 chars)' },
    project_name: { type: 'string', description: 'product/project name as the team calls it, or "" ' },
    summary: { type: 'string', description: 'RU, 1-2 sentences: what they built' },
    approach: { type: 'string', description: 'RU, 2-5 sentences: HOW it works — inputs/data → core logic/model/agent → outputs; key design decisions. Concrete, no fluff. "" if no_content' },
    core: { type: 'array', items: { type: 'string', enum: ['llm_agent_tools', 'llm_pipeline', 'rag', 'classic_ml', 'deep_learning', 'graph_analytics', 'optimization_rules', 'simulation_game', 'speech_stt_tts', 'dashboard_ui', 'other'] }, description: 'core solution types, 1-3 items' },
    techniques: { type: 'array', items: { type: 'string' }, description: 'specific algorithms/methods named: e.g. LightGBM, Louvain, NetworkX, pgvector RAG, Whisper large-v3, EOQ, OR-Tools, function calling, LangGraph' },
    llms: { type: 'array', items: { type: 'string' }, description: 'LLM / speech / embedding models or providers explicitly named (GPT-4o-mini, Claude Sonnet, Gemini 2.5 Flash, Llama via Ollama, Qwen, KazLLM, Whisper...)' },
    stack: { type: 'array', items: { type: 'string' }, description: 'languages/frameworks/infra: Python, FastAPI, React, Next.js, Streamlit, PostgreSQL, Docker...' },
    maturity: { type: 'string', enum: ['no_code', 'idea_only', 'prototype', 'working_mvp', 'polished'] },
    readme_quality: { type: 'integer', minimum: 0, maximum: 3, description: '0 none/template, 1 minimal, 2 decent (what+how to run), 3 excellent (architecture, run, results, design decisions)' },
    has_run_instructions: { type: 'boolean' },
    has_demo_link: { type: 'boolean', description: 'README links a deployed demo / video / presentation' },
    reports_metrics: { type: 'boolean' },
    metrics: { type: 'string', description: 'quantitative results reported (e.g. "MAE 1.8 MW, R² 0.91"), "" if none' },
    notable: { type: 'string', description: 'RU: what is genuinely interesting/unusual here that other participants could learn from; "" if nothing stands out' },
    readme_lang: { type: 'string', enum: ['ru', 'kk', 'en', 'mixed', 'none'] },
    other_task_desc: { type: 'string', description: 'if status=other_task: what task it is (RU, short); else ""' },
  },
  required: ['name', 'status', 'track', 'confidence', 'evidence', 'project_name', 'summary', 'approach', 'core', 'techniques', 'llms', 'stack', 'maturity', 'readme_quality', 'has_run_instructions', 'has_demo_link', 'reports_metrics', 'metrics', 'notable', 'readme_lang', 'other_task_desc'],
}
const SCHEMA = { type: 'object', properties: { repos: { type: 'array', items: REPO } }, required: ['repos'] }

function prompt(path, n, only) {
  return `You are analyzing hackathon team repositories for a report to participants and organizers.
${TRACKS}

Read the file ${path} COMPLETELY with the Read tool (it is long: page through it with offset/limit until you reach the end; do not stop early).
It contains ${n} repo cards, each starting with "########## REPO: <name>" and ending with "########## END <name>". Each card has: stats line (commits, authors, files, first/last commit time), flags detected from the file tree, file extension counts, the README text (may be truncated), the file tree (may be truncated), and commit subjects.
${only ? `Only analyze these repos (skip others): ${only.join(', ')}.` : `Return exactly one entry for EVERY one of the ${n} repos, in file order.`}

For each repo decide which final case it addresses (use README, file names, data files, commit messages — e.g. files like wind_*.csv, transactions.csv, tariffs, meeting audio, org-structure docx are strong signals). Base every claim ONLY on what is in the card; do not invent features. If the README is template-only, infer from tree + commits and lower the confidence.
Write summary/approach/notable in Russian, concise and concrete (name the actual algorithms, models, data flow). Keep evidence short.
Return via the structured output tool.`
}

phase('Analyze')
const results = await pipeline(
  COUNTS.map((n, i) => ({ i, n, path: `${DIR}/batch_${String(i).padStart(3, '0')}.md` })),
  b => agent(prompt(b.path, b.n), { label: `batch ${b.i} (${b.n})`, phase: 'Analyze', schema: SCHEMA }),
  async (r, b) => {
    const got = (r && r.repos) ? r.repos : []
    if (got.length >= b.n) return { i: b.i, n: b.n, repos: got, backfilled: 0 }
    // ask for the missing ones by reading the names from the file ourselves is impossible (no fs); ask agent to find which are missing
    const have = got.map(x => x.name)
    const extra = await agent(prompt(b.path, b.n, null) + `\n\nYou already returned these repos, DO NOT return them again: ${have.join(', ') || '(none)'}. Return only the remaining repos from the file.`,
      { label: `backfill ${b.i}`, phase: 'Backfill', schema: SCHEMA })
    const more = (extra && extra.repos) ? extra.repos.filter(x => !have.includes(x.name)) : []
    return { i: b.i, n: b.n, repos: got.concat(more), backfilled: more.length }
  },
)

const ok = results.filter(Boolean)
const total = ok.reduce((s, r) => s + r.repos.length, 0)
const short = ok.filter(r => r.repos.length < r.n).map(r => ({ i: r.i, n: r.n, got: r.repos.length }))
const failed = COUNTS.map((_, i) => i).filter(i => !ok.find(r => r.i === i))
log(`analyzed ${total} repos; batches short: ${short.length}; failed batches: ${failed.length}`)
const byTrack = {}
for (const r of ok) for (const x of r.repos) { const k = x.status === 'case' ? String(x.track) : x.status; byTrack[k] = (byTrack[k] || 0) + 1 }
return { total, short, failed, byTrack }

export const meta = {
  name: 'hackalem-adjudicate',
  description: 'Second-opinion classification of disputed HackAlem repos: two independent lenses per repo, tie-break where they disagree',
  phases: [
    { title: 'Judge', detail: 'README lens and artifacts lens judge each disputed batch independently' },
    { title: 'Tiebreak', detail: 'third agent settles repos where the two lenses disagree' },
  ],
}

const DIR = args.dir // absolute path to work/adj
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
Commonly confused: 5 (supplier replenishment orders, manager approval) vs 10 (customer-facing catalog consultant, cart); 3 (HR career navigator) vs 9 (insurance call routing);
1 (wind power forecast) vs 8 (meeting audio → protocol); 12 (city budget simulator) vs generic dashboards.
NOT final cases: qualifier/warm-up round tasks (commits on 2026-09-21 or earlier; e.g. message classifier, terminal FAQ bot, alert filter, defect detector), unrelated projects, empty/template repos.
The keyword heuristic is crude (it just counts words like "event", "budget", "transaction"), so it is a hint, not evidence.`

const DEC = {
  type: 'object',
  properties: {
    decisions: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          status: { type: 'string', enum: ['case', 'other_task', 'no_content', 'unclear'] },
          track: { type: 'integer', minimum: 0, maximum: 12 },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          reason: { type: 'string', description: 'RU, <=220 chars, cite the concrete evidence (quote, file name, data file, commit message)' },
        },
        required: ['name', 'status', 'track', 'confidence', 'reason'],
      },
    },
  },
  required: ['decisions'],
}

const LENSES = [
  { k: 'readme', p: 'Judge primarily from what the README says the product does and which business problem/partner it names; use files and commits to confirm.' },
  { k: 'artifacts', p: 'Judge primarily from hard artifacts: data file names, directory/module names, sample inputs, and commit messages; README prose is secondary (it can be generic, stale, or copied).' },
]

function judgePrompt(path, n, lens) {
  return `You are re-checking disputed case classifications of hackathon repositories.
${TRACKS}

Read ${path} COMPLETELY with the Read tool (page with offset/limit until the end). It holds ${n} repo cards ("########## REPO: <name>" … "########## END <name>").
Each card shows the FIRST PASS classification, the keyword-heuristic hint, and WHY it is disputed, then README, file tree and commit subjects.
${lens.p}
Make your OWN decision for every repo — do not defer to the first pass or the heuristic. status=case requires concrete evidence of one specific case;
use unclear only if the content genuinely does not identify a case; other_task for qualifier/unrelated work; no_content for template/near-empty.
Return exactly ${n} decisions via the structured output tool.`
}

phase('Judge')
const out = await pipeline(
  COUNTS.map((n, i) => ({ i, n, path: `${DIR}/adj_${String(i).padStart(3, '0')}.md` })),
  b => parallel(LENSES.map(l => () => agent(judgePrompt(b.path, b.n, l), { label: `adj ${b.i} · ${l.k}`, phase: 'Judge', schema: DEC })))
    .then(rs => ({ b, rs })),
  async ({ b, rs }) => {
    const [A, B] = rs.map(r => new Map(((r && r.decisions) || []).map(d => [d.name, d])))
    const names = [...new Set([...A.keys(), ...B.keys()])]
    const agreed = [], split = []
    for (const nm of names) {
      const a = A.get(nm), c = B.get(nm)
      if (a && c && a.status === c.status && a.track === c.track) agreed.push({ ...a, confidence: a.confidence === 'low' || c.confidence === 'low' ? 'medium' : a.confidence, votes: 2 })
      else split.push({ nm, a, c })
    }
    if (!split.length) return agreed
    const brief = split.map(s => `- ${s.nm}: README-lens → ${s.a ? `${s.a.status}/${s.a.track} (${s.a.reason})` : 'no answer'}; ARTIFACTS-lens → ${s.c ? `${s.c.status}/${s.c.track} (${s.c.reason})` : 'no answer'}`).join('\n')
    const tb = await agent(`${TRACKS}

Two independent reviewers disagreed on these repos in ${b.path}:
${brief}

Read the cards for ONLY these repos in that file (use Grep to find "REPO: <name>" then Read around it; read the whole card). Weigh both arguments against the evidence and decide.
Return one decision per listed repo via the structured output tool.`, { label: `tiebreak ${b.i} (${split.length})`, phase: 'Tiebreak', schema: DEC })
    const T = new Map(((tb && tb.decisions) || []).map(d => [d.name, d]))
    return agreed.concat(split.map(s => T.get(s.nm) ? { ...T.get(s.nm), votes: 3 } : (s.a || s.c)).filter(Boolean))
  },
)
const decisions = out.filter(Boolean).flat()
log(`decisions: ${decisions.length}`)
return { decisions }

export const meta = {
  name: 'hackalem-synthesize',
  description: 'Per-track synthesis of how HackAlem teams solved each case (approach clusters, standouts, tips, gaps), adversarial fact-check of each synthesis, then a cross-track overview',
  phases: [
    { title: 'Synthesize', detail: 'one analyst per track reads the dossier of every solution + README bundle' },
    { title: 'Fact-check', detail: 'a skeptic per track verifies clusters, counts, standouts and claims against the dossier and READMEs' },
    { title: 'Overview', detail: 'cross-track findings for participants and organizers' },
  ],
}

const DIR = args.dir // absolute path to work/syn
const TRACKS = args.tracks // [{id, n, title}]

const SYN = {
  type: 'object',
  properties: {
    headline: { type: 'string', description: 'RU, 1-2 sentences: the story of this track — what most teams did and what separated the best' },
    approaches: {
      type: 'array', minItems: 2, maxItems: 7,
      items: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'RU, short name of the approach family' },
          count: { type: 'integer', description: 'approximate number of solutions in this family (families may overlap)' },
          description: { type: 'string', description: 'RU, 2-3 sentences: how these solutions work (data → logic/model → output), typical stack, strengths/limits' },
          examples: { type: 'array', items: { type: 'string' }, description: '3-6 exact repo names (hack-xxxxxxxx-...) that best exemplify it' },
        },
        required: ['name', 'count', 'description', 'examples'],
      },
    },
    standouts: {
      type: 'array', minItems: 3, maxItems: 8,
      items: {
        type: 'object',
        properties: {
          repo: { type: 'string', description: 'exact repo name' },
          why: { type: 'string', description: 'RU, 2-3 sentences: what concretely is strong or instructive (specific technique, evaluation, UX, rigor) — only claims supported by its README/dossier' },
        },
        required: ['repo', 'why'],
      },
    },
    tips: { type: 'array', items: { type: 'string' }, description: 'RU, 3-6 bullet points: what worked well in this track — practical lessons for participants of future hackathons' },
    pitfalls: { type: 'array', items: { type: 'string' }, description: 'RU, 3-6 bullet points: typical gaps/mistakes seen across solutions' },
    organizers: { type: 'array', items: { type: 'string' }, description: 'RU, 2-5 bullet points for organizers and the case partner (case clarity, data, what teams struggled with, evaluation hints)' },
  },
  required: ['headline', 'approaches', 'standouts', 'tips', 'pitfalls', 'organizers'],
}
const CHECK = {
  type: 'object',
  properties: {
    revised: SYN,
    changes: { type: 'array', items: { type: 'string' }, description: 'what you corrected and why (short)' },
  },
  required: ['revised', 'changes'],
}
const OVERVIEW = {
  type: 'object',
  properties: {
    key_findings: { type: 'array', items: { type: 'string' }, description: 'RU, 5-8 cross-track observations backed by numbers' },
    for_participants: { type: 'array', items: { type: 'string' }, description: 'RU, 5-8 concrete lessons for participants' },
    for_organizers: { type: 'array', items: { type: 'string' }, description: 'RU, 5-8 concrete observations/recommendations for organizers' },
  },
  required: ['key_findings', 'for_participants', 'for_organizers'],
}

const STYLE = `Write in Russian, plainly and concretely: name real techniques, models, data flows, numbers. No marketing words, no filler, no emoji.
You may use **bold** for 1-3 key words per bullet and backticks for code identifiers. When you refer to a specific solution, write its exact repo name (hack-xxxxxxxx-...) so it can be linked.
These are 5-hour hackathon prototypes judged only from README, file tree and commit metadata (code was NOT executed) — do not claim something works, say what the README claims.`

function synPrompt(t) {
  const d = `${DIR}/dossier_t${String(t.id).padStart(2, '0')}.md`, rd = `${DIR}/readmes_t${String(t.id).padStart(2, '0')}.md`
  return `You are writing the analysis of one case track of the HackAlem.ai hackathon final for a report read by participants (to learn how others solved it) and organizers.
Track ${t.title}. ${t.n} team solutions.

1. Read ${d} COMPLETELY (page with offset/limit). It contains track stats and, for every solution, the per-repo analysis (summary, approach, techniques, models, stack, maturity, README quality, metrics, notable).
2. Group the solutions into 3-7 approach families by HOW they solve the case (not by stack alone). Give approximate counts.
3. Pick 4-8 standouts worth learning from (rigor, evaluation with metrics, clever modelling, strong UX/explainability, honest limitations). Before finalizing each standout, verify it in ${rd} (Grep for "README <repo-name>" and read that README) so every claim is supported.
4. Write tips (what worked), pitfalls (typical gaps), and notes for organizers/partner.
${STYLE}
Return via the structured output tool.`
}
function checkPrompt(t, draft) {
  const d = `${DIR}/dossier_t${String(t.id).padStart(2, '0')}.md`, rd = `${DIR}/readmes_t${String(t.id).padStart(2, '0')}.md`
  return `You are a skeptical fact-checker for one section of a hackathon report. Track ${t.title}, ${t.n} solutions.
Draft synthesis (JSON):
${JSON.stringify(draft)}

Verify it against ${d} (read it completely) and, for standouts and any specific claim, the READMEs in ${rd} (Grep "README <repo-name>").
Check and FIX: (a) every example repo really belongs to its approach family and exists in this track; (b) counts are roughly right (recount from the dossier);
(c) every standout claim is supported by that repo's README/dossier — remove or rewrite unsupported ones; (d) a significant approach family or a clearly stronger standout is not missing;
(e) tips/pitfalls/organizer notes are grounded in what the dossier shows, not generic advice; (f) wording is plain and concrete.
${STYLE}
Return the corrected full synthesis as "revised" plus a short list of "changes".`
}

phase('Synthesize')
const results = await pipeline(
  TRACKS,
  t => agent(synPrompt(t), { label: `synth t${t.id}`, phase: 'Synthesize', schema: SYN }),
  (draft, t) => draft ? agent(checkPrompt(t, draft), { label: `check t${t.id}`, phase: 'Fact-check', schema: CHECK })
    .then(c => ({ id: t.id, syn: (c && c.revised) || draft, changes: (c && c.changes) || [] })) : null,
)
const tracks = {}
for (const r of results.filter(Boolean)) tracks[String(r.id)] = r.syn

phase('Overview')
const digest = results.filter(Boolean).map(r => `TRACK ${r.id}: ${r.syn.headline}\nApproaches: ${r.syn.approaches.map(a => `${a.name} (~${a.count})`).join('; ')}\nPitfalls: ${r.syn.pitfalls.join(' | ')}\nOrganizers: ${r.syn.organizers.join(' | ')}`).join('\n\n')
const overview = await agent(`You write the cross-track summary of a report on the HackAlem.ai hackathon final (12 industry cases, a 5-hour sprint on 2026-09-23).
Read ${DIR}/global_stats.md completely (global numbers and per-track stats). Here is the fact-checked digest of every track:

${digest}

Produce key cross-track findings (backed by numbers from global_stats.md), lessons for participants, and observations/recommendations for organizers
(e.g. case popularity imbalance, how teams used AI coding assistants, repo hygiene like committed .env or node_modules, commits after the deadline — describe neutrally, commit timestamps are self-reported).
${STYLE}`, { label: 'overview', phase: 'Overview', schema: OVERVIEW })

return { tracks, overview, changes: results.filter(Boolean).map(r => ({ id: r.id, changes: r.changes })) }

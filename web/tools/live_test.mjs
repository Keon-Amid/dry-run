// Dev check: the timeline builder must survive every partial state a live run passes through.
import fs from 'node:fs'
import { buildTimeline } from '../.tmp/timeline.mjs'
const dir = process.argv[2]
const rd = (f) => JSON.parse(fs.readFileSync(`${dir}/${f}.json`, 'utf8'))
const full = { run: rd('run'), triage: rd('triage'), results: rd('results'), swarm: rd('swarm'), archil: rd('archil') }
const states = []
states.push({ id: 'x', sigs: {}, sig: '' })
for (let k = 0; k <= full.run.steps.length; k++) states.push({ id: 'x', run: { ...full.run, steps: full.run.steps.slice(0, k) } })
for (let w = 1; w <= full.results.waves.length; w++) {
  const st = { id: 'x', run: full.run, results: { ...full.results, waves: full.results.waves.slice(0, w) }, archil: { ...full.archil, waves: full.archil.waves.slice(0, w) } }
  if (w >= 2) st.triage = { ...full.triage, checks: full.triage.checks.map((c) => { const { suspects, culprit, swarm, ...rest } = c; return rest }) }
  states.push(st)
}
states.push({ id: 'x', ...full })
let prev = 0
for (const [i, st] of states.entries()) {
  const tl = buildTimeline(st)
  const ok = isFinite(tl.duration) && tl.captions.every((c) => isFinite(c.t)) && tl.actors.every((a) => a.segs.every((s) => isFinite(s.t0) && isFinite(s.x0) && isFinite(s.x1)))
  console.log(String(i).padStart(2), 'dur', tl.duration.toFixed(1).padStart(6), 'actors', String(tl.actors.length).padStart(2), 'lanesets', tl.laneSets.length, 'markers', tl.markers.length, 'complete', tl.complete, ok ? 'ok' : 'BAD', tl.duration + 0.001 < prev ? 'SHRANK' : '')
  prev = tl.duration
}

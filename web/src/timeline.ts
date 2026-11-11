// Turns the run files into a deterministic, seekable timeline: who walks where, who dies when, what the HUD says.
// Every count, score, name and millisecond shown comes from the run files. Animation pacing is the page's own.
import type { RunData } from './data'

export const W = 640
export const H = 360
export const FY = 98 // feet line in the main corridor
export const LANES = { top: 114, bottom: 354 }
export const ENT_X = 22
export const GATE_X = 602

export type Pose = 'idle' | 'walk' | 'fall' | 'dead' | 'cheer' | 'spawn' | 'ghostwalk' | 'ghostidle' | 'invalid'
export type Seg = { t0: number; t1: number; x0: number; x1: number; y0: number; y1: number; pose: Pose }
export type Mark = { t: number; kind: 'ok' | 'dead' | 'held' | 'invalid' }
export type Actor = {
  id: string
  reportId: string
  label: string
  banner: string | null
  segs: Seg[]
  mark?: Mark
  tHide?: number
  phase: number
  wave?: string
}
export type Lane = {
  y0: number
  h: number
  feetY: number
  label: string
  text: string
  color: string | null
  score: string
  sub?: string
  scoreT: number
  tone: 'good' | 'bad' | 'mixed'
  glowT?: number
  flag?: boolean
  gate?: boolean
}
export type LaneSet = {
  t0: number
  t1: number
  wave: string
  purpose: string
  forkStep: number
  forkX: number
  lanes: Lane[]
  riftT1: number
}
export type Fire = { step: number; x: number; litT: number; goldT: number; ckptMs: number | null }
export type MarkerKind = 'fail' | 'test_wrong' | 'model_slip' | 'real_problem' | 'inconclusive' | 'culprit'
export type Marker = { step: number; check: string; t: number; slot: number; states: { t: number; kind: MarkerKind }[] }
export type Tone = 'info' | 'bad' | 'good' | 'archil' | 'gold'
export type Caption = { t: number; phase: string; text: string; tone: Tone }
export type Hud = {
  checkpoints: number
  checkpointMs: number | null
  branches: number
  live: number
  branchMs: number | null
  sandboxMs: number | null
  mountMs: number | null
  savedSteps: number | null
  savedMin: number | null
}
export type Timeline = {
  duration: number
  n: number
  built: number
  stepX: (k: number) => number
  at: (k: number) => number
  fires: Fire[]
  markers: Marker[]
  actors: Actor[]
  laneSets: LaneSet[]
  captions: Caption[]
  hud: { t: number; s: Hud }[]
  footprints: { t0: number; t1: number; tEnd: number; fromX: number; toX: number }[]
  tags: { t0: number; t1: number; step: number; kind: 'fork' | 'origin' }[]
  focus: { t0: number; t1: number; check: string }[]
  gateOpenT: number | null
  complete: boolean
  hasCards: boolean
}

// Banner colours identify a route. Green, red and gold are reserved for pass, fail and winner.
const BANNERS = ['#5FD3E8', '#F2994A', '#E8D8B0', '#F6D55C', '#F1EAD8']
const GOLD = '#E2B84B'

const num = (v: any, d: number): number => (typeof v === 'number' && isFinite(v) ? v : d)
const numOrNull = (v: any): number | null => (typeof v === 'number' && isFinite(v) ? v : null)
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

export function actorAt(a: Actor, t: number): { x: number; y: number; pose: Pose; u: number } | null {
  if (!a.segs.length || t < a.segs[0].t0) return null
  if (a.tHide != null && t >= a.tHide) return null
  let s = a.segs[0]
  for (const g of a.segs) {
    if (g.t0 <= t) s = g
    else break
  }
  const u = s.t1 > s.t0 ? clamp((t - s.t0) / (s.t1 - s.t0), 0, 1) : 1
  return { x: s.x0 + (s.x1 - s.x0) * u, y: s.y0 + (s.y1 - s.y0) * u, pose: s.pose, u }
}

export function captionAt(tl: Timeline, t: number): Caption | null {
  let c: Caption | null = null
  for (const k of tl.captions) {
    if (k.t <= t) c = k
    else break
  }
  return c
}

export function hudAt(tl: Timeline, t: number): Hud {
  let h = tl.hud[0].s
  for (const k of tl.hud) {
    if (k.t <= t) h = k.s
    else break
  }
  return h
}

export function buildTimeline(d: RunData): Timeline {
  const run = d.run || {}
  const steps: any[] = Array.isArray(run.steps) ? run.steps : []
  const n = Math.max(1, Math.round(num(run.n_steps, steps.length || 7)))
  const X0 = 84
  const X1 = 548
  const stepX = (k: number) => (k <= 0 ? ENT_X + 14 : n === 1 ? (X0 + X1) / 2 : X0 + ((Math.min(k, n) - 1) * (X1 - X0)) / (n - 1))
  const at = (k: number) => (k <= 0 ? ENT_X + 14 : stepX(k) - 13)

  const fires: Fire[] = []
  for (let k = 1; k <= n; k++) fires.push({ step: k, x: stepX(k), litT: Infinity, goldT: Infinity, ckptMs: null })
  const markers: Marker[] = []
  const actors: Actor[] = []
  const laneSets: LaneSet[] = []
  const captions: Caption[] = []
  const footprints: Timeline['footprints'] = []
  const tags: Timeline['tags'] = []
  const focus: Timeline['focus'] = []
  const hudEv: { t: number; f: (h: Hud) => void }[] = []
  let gateOpenT: number | null = null
  let seq = 0

  const mk = (id: string, reportId: string, label: string, banner: string | null): Actor => {
    const a: Actor = { id, reportId, label, banner, segs: [], phase: (seq++ * 0.37) % 1 }
    actors.push(a)
    return a
  }
  const seg = (a: Actor, t0: number, t1: number, x0: number, x1: number, y0: number, y1: number, pose: Pose) =>
    a.segs.push({ t0, t1, x0, x1, y0, y1, pose })
  const cap = (t: number, phase: string, text: string, tone: Tone = 'info') => captions.push({ t, phase, text, tone })
  const markerOf = (check: string) => markers.find((m) => m.check === check)
  const addMarker = (step: number, check: string, t: number): Marker => {
    const slot = markers.filter((m) => m.step === step).length
    const m: Marker = { step, check, t, slot, states: [{ t, kind: 'fail' }] }
    markers.push(m)
    return m
  }
  const closeTags = (t: number) => {
    for (const g of tags) if (g.t1 === Infinity) g.t1 = t
    for (const f of footprints) if (f.tEnd === Infinity) f.tEnd = t
  }
  const endWave = (t: number) => {
    const s = laneSets[laneSets.length - 1]
    if (s && s.t1 === Infinity) {
      s.t1 = t
      for (const a of actors) if (a.wave === s.wave && a.tHide == null) a.tHide = t
    }
  }

  // ---------- BUILD: one campfire per spec step, one checkpoint per campfire ----------
  const triChecks: any[] = Array.isArray(d.triage?.checks) ? d.triage.checks : []
  const triNames = new Set<string>(triChecks.map((c) => c.check))
  const heldout = new Set<string>()
  for (const s of d.swarm?.swarms ?? []) for (const h of s.heldout_checks ?? []) heldout.add(h)
  // Before triage.json exists we can't know which failing checks will be triaged; skip the ones named as held-out.
  const showCheck = (c: string) => (triNames.size ? triNames.has(c) : !heldout.has(c) && !/^held[-_]?out/i.test(c))
  const surfaced = new Map<string, number>()
  const failSeen = new Set<string>()

  const hero = mk('build', 'build', 'the builder agent (main run)', null)
  let who = hero
  let dead = false
  let T = 0.5
  seg(hero, 0, T, at(0), at(0), FY, FY, 'idle')
  cap(
    0,
    'BUILD',
    steps.length
      ? `The agent builds the spec one step at a time. Each campfire is a checkpoint of its whole disk: files and conversation.`
      : `Waiting for the build to start.`,
  )
  let ghost: Actor | null = null
  for (const s of steps) {
    const k = Math.round(num(s.step, 0))
    if (k < 1 || k > n) continue
    const dur = clamp(num(s.wall_s, 1.2), 0.9, 2.2)
    seg(who, T, T + dur, at(k - 1), at(k), FY, FY, dead ? 'ghostwalk' : 'walk')
    T += dur
    fires[k - 1].litT = T
    fires[k - 1].ckptMs = numOrNull(s.checkpoint_ms)
    const ck = numOrNull(s.checkpoint_ms)
    hudEv.push({ t: T, f: (h) => ((h.checkpoints = k), (h.checkpointMs = ck)) })
    const fails = Object.entries(s.checks || {})
      .filter(([c, ok]) => ok === false && !failSeen.has(c))
      .map(([c]) => c)
    for (const c of fails) {
      failSeen.add(c)
      if (!surfaced.has(c)) surfaced.set(c, k)
    }
    const shown = fails.filter(showCheck)
    for (const c of shown) addMarker(k, c, T)
    if (shown.length && !dead) {
      dead = true
      seg(hero, T, T + 0.7, at(k), at(k) + 6, FY, FY, 'fall')
      seg(hero, T + 0.7, T + 0.7, at(k) + 6, at(k) + 6, FY, FY, 'dead')
      hero.mark = { t: T + 0.7, kind: 'dead' }
      cap(T, 'BUILD', `A check fails at step ${k}: ${shown.join(', ')}. The builder can't see the checks, so it keeps building.`, 'bad')
      ghost = mk('build-ghost', 'build', 'the builder, still building (checks are hidden from it)', null)
      seg(ghost, T + 0.7, T + 1.4, at(k), at(k), FY, FY, 'ghostidle')
      who = ghost
      T += 1.4
    } else if (shown.length) {
      cap(T, 'BUILD', `Another check fails at step ${k}: ${shown.join(', ')}.`, 'bad')
      seg(who, T, T + 0.6, at(k), at(k), FY, FY, 'ghostidle')
      T += 0.6
    } else {
      seg(who, T, T + 0.2, at(k), at(k), FY, FY, dead ? 'ghostidle' : 'idle')
      T += 0.2
    }
  }
  const built = steps.length
  const buildDone = built >= n
  if (buildDone) {
    // checks that only fail in the final grade
    for (const [c, ok] of Object.entries(run.final_checks || {})) {
      if (ok === false && !failSeen.has(c)) {
        failSeen.add(c)
        surfaced.set(c, n)
        if (showCheck(c)) addMarker(n, c, T)
      }
    }
    for (const c of triChecks)
      if (!markerOf(c.check)) addMarker(clamp(Math.round(num(c.surfaced_step, n)), 1, n), c.check, T)
    if (!markers.length) {
      seg(hero, T, T + 0.8, at(n), GATE_X - 16, FY, FY, 'walk')
      T += 0.8
      seg(hero, T, T, GATE_X - 16, GATE_X - 16, FY, FY, 'cheer')
      hero.mark = { t: T, kind: 'ok' }
      gateOpenT = T
      cap(T, 'GRADE', `All ${n} steps built and every check passes.`, 'good')
      T += 2
    } else {
      if (ghost) ghost.tHide = T + 1.2
      cap(
        T,
        'GRADE',
        `Build finished: ${markers.length} check${markers.length === 1 ? '' : 's'} failed. Each one is triaged before anything else is spent on it.`,
        'bad',
      )
      T += 2
    }
  }

  // ---------- waves ----------
  const waves: any[] = Array.isArray(d.results?.waves) ? d.results.waves : []
  const waveBy = new Map<string, any>(waves.map((w) => [w.wave, w]))
  const played = new Set<string>()
  const swarms: any[] = Array.isArray(d.swarm?.swarms) ? d.swarm.swarms : []
  const archWaves: any[] = Array.isArray(d.archil?.waves) ? d.archil.waves : []

  const deathStep = (c: any, w: any, fork: number, to: number): number => {
    const own = numOrNull(c.first_fail_step)
    if (own != null) return clamp(Math.round(own), fork + 1, to)
    // Not recorded per copy: place the body at the step where its failing check surfaced in the main run.
    const failing = Object.entries(c.checks || {})
      .filter(([, ok]) => ok === false)
      .map(([name]) => name)
    const target = w.check && failing.includes(w.check) ? [w.check] : failing
    let best = Infinity
    for (const name of target) {
      const s = markerOf(name)?.step ?? surfaced.get(name)
      if (s != null && s > fork) best = Math.min(best, s)
    }
    return clamp(best === Infinity ? to : best, fork + 1, to)
  }

  function playWave(w: any, T0: number, opt: { tri?: any; swarm?: any }): number {
    const purpose = String(w.purpose || 'wave')
    const fork = Math.max(0, Math.round(num(w.fork_step, 0)))
    const to = Math.max(fork + 1, Math.round(num(w.to_step, n)))
    const copies: any[] = Array.isArray(w.copies) ? w.copies : []
    const routes: any[] =
      Array.isArray(w.routes) && w.routes.length
        ? w.routes
        : [...new Set(copies.map((c) => c.route))].map((r) => {
            const c = copies.find((x) => x.route === r) || {}
            return { route: r, kind: c.kind, edit: c.edit }
          })
    const L = Math.max(1, routes.length)
    const pitch = clamp(Math.floor((LANES.bottom - LANES.top) / L), 30, 48)
    const forkX = at(fork)
    const span = Math.max(1, to - fork)
    const perStep = clamp(2.8 / span, 0.5, 1.2)
    const maxWall = Math.max(0.001, ...copies.map((c) => num(c.wall_s, 0)))
    const rw = new Map<string, any>((opt.swarm?.rewrites ?? []).map((r: any) => [r.route, r]))
    const sus = new Map<string, any>((opt.tri?.suspects?.suspects ?? []).map((s: any) => [s.route, s]))
    const heldNames: string[] = opt.swarm?.heldout_checks ?? []
    const arch = new Map<string, any>()
    const aw = archWaves.find((x) => x.wave === w.wave)
    for (const c of aw?.copies ?? []) arch.set(c.id, c)
    const set: LaneSet = { t0: T0, t1: Infinity, wave: w.wave, purpose, forkStep: fork, forkX, lanes: [], riftT1: T0 + 1.2 }
    laneSets.push(set)
    let tEnd = T0 + 1
    let bi = 0
    routes.forEach((r, li) => {
      const y0 = LANES.top + li * pitch
      const feetY = y0 + pitch - 8
      const mine = copies.filter((c) => c.route === r.route)
      const R = rw.get(r.route)
      const Sx = sus.get(r.route)
      const isControl = r.kind === 'control' || r.route === 'control'
      const isPlain = r.kind === 'none' || r.route === 'rebuild'
      const color = isControl || isPlain ? null : BANNERS[bi++ % BANNERS.length]
      let label: string
      let text: string
      if (isControl) {
        label = 'CONTROL'
        text = 'nothing changed'
      } else if (isPlain) {
        label = 'REBUILD'
        text = `step ${to} rebuilt from checkpoint ${fork}, nothing changed`
      } else if (r.kind === 'rule_off') {
        label = 'RULE OFF'
        text = String(Sx?.rule ?? r.edit ?? r.route)
      } else if (r.kind === 'spec_line') {
        if (purpose === 'swarm') {
          label = `REWRITE ${li + 1}`
          text = `"${R?.text ?? r.edit ?? ''}"`
        } else {
          label = Sx?.step != null ? `SPEC STEP ${Sx.step}` : 'SPEC LINE'
          text = Sx?.old != null ? `"${Sx.old}" → "${Sx.new ?? r.edit ?? ''}"` : `→ "${r.edit ?? ''}"`
        }
      } else {
        label = String(r.route ?? 'route').toUpperCase()
        text = r.edit != null ? String(r.edit) : ''
      }
      const passedN = typeof r.passed === 'number' ? r.passed : mine.filter((c) => c.passed === true).length
      const gradedN = typeof r.graded === 'number' ? r.graded : typeof r.runs === 'number' ? r.runs : mine.length
      const score = typeof r.score === 'string' ? r.score : `${passedN}/${gradedN}`
      const lane: Lane = {
        y0,
        h: pitch - 3,
        feetY,
        label,
        text,
        color,
        score,
        sub: R ? `visible ${R.visible ?? score} · held-out ${R.heldout ?? 'unknown'}` : undefined,
        scoreT: Infinity,
        tone: gradedN > 0 && passedN === gradedN ? 'good' : passedN === 0 ? 'bad' : 'mixed',
        flag: !!R?.winner,
        gate: purpose === 'swarm',
      }
      if (R && !R.winner && lane.tone === 'good') lane.tone = 'mixed'
      mine.forEach((c, ci) => {
        const a = mk(String(c.id), String(c.id), `${label}${text ? ': ' + text : ''}`, color)
        a.wave = w.wave
        const off = ci - (mine.length - 1) / 2
        const ts = T0 + 0.5 + li * 0.14 + ci * 0.12
        const xs = forkX + off * 19
        seg(a, ts, ts + 0.5, forkX, xs, FY, feetY, 'spawn')
        let t = ts + 0.5
        const rel = 0.8 + 0.4 * (num(c.wall_s, maxWall) / maxWall)
        const invalid = c.invalid === true || c.ok === false
        const failedHeld = !!R && c.passed === true && heldNames.some((h) => c.checks?.[h] === false)
        if (invalid) {
          const xe = at(Math.min(to, fork + 1)) + off * 19
          const dur = perStep * rel
          seg(a, t, t + dur, xs, xe, feetY, feetY, 'walk')
          t += dur
          seg(a, t, t, xe, xe, feetY, feetY, 'invalid')
          a.mark = { t, kind: 'invalid' }
        } else if (c.passed === true && !failedHeld) {
          const xe = at(to) + off * 19
          const dur = span * perStep * rel
          seg(a, t, t + dur, xs, xe, feetY, feetY, 'walk')
          t += dur
          if (R?.winner) {
            const xf = GATE_X - 46 + off * 17
            seg(a, t, t + 0.6, xe, xf, feetY, feetY, 'walk')
            t += 0.6
            seg(a, t, t, xf, xf, feetY, feetY, 'cheer')
          } else seg(a, t, t, xe, xe, feetY, feetY, 'idle')
          a.mark = { t, kind: 'ok' }
        } else if (failedHeld) {
          // passed the visible check, then fell to a held-out check it never saw
          const xe = at(to) + off * 19
          const dur = span * perStep * rel
          seg(a, t, t + dur, xs, xe, feetY, feetY, 'walk')
          t += dur
          const xg = GATE_X - 30 + off * 22
          seg(a, t, t + 0.5, xe, xg, feetY, feetY, 'walk')
          t += 0.5
          seg(a, t, t + 0.5, xg, xg, feetY, feetY, 'fall')
          t += 0.5
          seg(a, t, t, xg, xg, feetY, feetY, 'dead')
          a.mark = { t, kind: 'held' }
        } else {
          const ds = deathStep(c, w, fork, to)
          const xe = at(ds) + off * 24
          const dur = Math.max(0.5, (ds - fork) * perStep * rel)
          seg(a, t, t + dur, xs, xe, feetY, feetY, 'walk')
          t += dur
          seg(a, t, t + 0.5, xe, xe, feetY, feetY, 'fall')
          t += 0.5
          seg(a, t, t, xe, xe, feetY, feetY, 'dead')
          a.mark = { t, kind: 'dead' }
        }
        const ac = arch.get(c.id) || {}
        const bms = numOrNull(c.timings_ms?.branch) ?? numOrNull(ac.branch_ms)
        const sms = numOrNull(c.timings_ms?.sandbox) ?? numOrNull(ac.sandbox_ms)
        const mms = numOrNull(c.timings_ms?.mount) ?? numOrNull(ac.mount_ms)
        hudEv.push({ t: ts, f: (h) => ((h.branches += 1), (h.live += 1), (h.branchMs = bms), (h.sandboxMs = sms), (h.mountMs = mms)) })
        hudEv.push({ t, f: (h) => (h.live = Math.max(0, h.live - 1)) })
        tEnd = Math.max(tEnd, t)
      })
      set.lanes.push(lane)
    })
    tEnd += 0.5
    for (const l of set.lanes) l.scoreT = tEnd
    const culprit = opt.tri?.culprit?.route
    routes.forEach((r, li) => {
      if (purpose === 'suspects' && culprit != null && r.route === culprit) set.lanes[li].glowT = tEnd + 0.7
      if (purpose === 'swarm' && rw.get(r.route)?.winner) set.lanes[li].glowT = tEnd + 0.3
    })
    const ss = numOrNull(aw?.saved?.steps)
    const sm = numOrNull(aw?.saved?.minutes)
    if (aw)
      hudEv.push({
        t: tEnd,
        f: (h) => {
          h.savedSteps = ss == null ? h.savedSteps : (h.savedSteps ?? 0) + ss
          h.savedMin = sm == null ? h.savedMin : (h.savedMin ?? 0) + sm
        },
      })
    return tEnd + 0.4
  }

  const perRoute = (w: any) => {
    const r = Array.isArray(w.routes) && w.routes.length ? w.routes.length : 1
    return Math.max(1, Math.round((Array.isArray(w.copies) ? w.copies.length : num(w.n, r)) / r))
  }
  const triageVerdict = (c: any, m: Marker | undefined, w: any, t: number): number => {
    const fork = w ? Math.round(num(w.fork_step, 0)) : null
    const where = w ? `Rebuilt step ${c.rebuild?.step ?? w.to_step} ${perRoute(w)} times from checkpoint ${fork}: fails ${c.rebuild?.fails ?? 'unknown'}.` : ''
    if (c.verdict === 'model_slip') {
      m?.states.push({ t, kind: 'model_slip' })
      cap(t, 'TRIAGE', `${where} THE MODEL SLIPPED. A retry is enough; the spec is fine.`, 'good')
    } else if (c.verdict === 'real_problem') {
      m?.states.push({ t, kind: 'real_problem' })
      cap(t, 'TRIAGE', `${where} A REAL PROBLEM in the spec or the harness.`, 'bad')
    } else if (c.verdict === 'inconclusive') {
      m?.states.push({ t, kind: 'inconclusive' })
      cap(t, 'TRIAGE', `${where} INCONCLUSIVE.`, 'info')
    } else {
      cap(t, 'TRIAGE', `${where} Verdict pending.`, 'info')
    }
    return t + 2.6
  }

  if (buildDone) {
    // TRIAGE, in the orchestrator's order
    for (const c of triChecks) {
      const m = markerOf(c.check)
      const w = c.rebuild?.wave ? waveBy.get(c.rebuild.wave) : null
      focus.push({ t0: T, t1: T + 1.8, check: c.check })
      cap(T, 'TRIAGE', `"${c.check}" failed at step ${m?.step ?? c.surfaced_step ?? '?'}. Is it the test, the model, or a real problem?`)
      T += 1.8
      if (c.verdict === 'test_wrong' || (c.fails_on_golden === true && !w)) {
        m?.states.push({ t: T, kind: 'test_wrong' })
        cap(T, 'TRIAGE', `"${c.check}" fails on the golden build too. YOUR TEST IS WRONG. The spec is not touched.`, 'good')
        T += 2.8
        continue
      }
      if (w) {
        played.add(w.wave)
        T = playWave(w, T, { tri: c })
      }
      T = triageVerdict(c, m, w, T)
      endWave(T)
    }
    for (const w of waves) {
      if (played.has(w.wave) || w.purpose !== 'triage') continue
      played.add(w.wave)
      if (w.check) focus.push({ t0: T, t1: T + 1.8, check: w.check })
      cap(T, 'TRIAGE', `"${w.check ?? w.wave}": rebuilding from checkpoint ${num(w.fork_step, 0)} to see if it fails again.`)
      T += 1.8
      T = playWave(w, T, {})
      cap(T, 'TRIAGE', `Rebuild scores are in. Verdict pending.`)
      T += 2.6
      endWave(T)
    }

    // everything after triage, in the order the orchestrator ran it
    for (const w of waves) {
      if (played.has(w.wave)) continue
      played.add(w.wave)
      const c = triChecks.find((x) => x.check === w.check)
      const fork = Math.round(num(w.fork_step, 0))
      if (w.purpose === 'suspects') {
        closeTags(T)
        const m = w.check ? markerOf(w.check) : undefined
        const origin = numOrNull(c?.origin_step)
        const surf = m?.step ?? numOrNull(c?.surfaced_step)
        if (surf != null && origin != null) {
          footprints.push({ t0: T, t1: T + 1.4, tEnd: Infinity, fromX: stepX(surf), toX: stepX(origin) })
          tags.push({ t0: T + 1.0, t1: Infinity, step: origin, kind: 'origin' })
          cap(
            T,
            'LOCATE',
            `Plain git, no LLM. git blame: it surfaced at step ${surf}. git log -L: those lines were first written at step ${origin}. Fork point: checkpoint ${fork}.`,
          )
        } else cap(T, 'LOCATE', `Fork point: checkpoint ${fork}.`)
        if (fork >= 1) tags.push({ t0: T + 1.6, t1: Infinity, step: fork, kind: 'fork' })
        T += 3
        cap(
          T,
          'SUSPECTS',
          `Branch checkpoint ${fork}: ${perRoute(w)} copies per suspect, one change each, plus a control with nothing changed. Each resumes the saved conversation and runs to the end.`,
          'archil',
        )
        T = playWave(w, T, { tri: c })
        if (c?.culprit) {
          const q = c.culprit
          const what =
            q.kind === 'rule_off' ? `harness rule "${q.rule}"` : q.kind === 'spec_line' ? `spec step ${q.step ?? '?'}, "${q.old ?? ''}"` : String(q.route)
          m?.states.push({ t: T, kind: 'culprit' })
          cap(T, 'SUSPECTS', `CULPRIT: ${what}. With that one change: ${q.score ?? 'unknown'} pass. Control, nothing changed: ${c.suspects?.control ?? 'unknown'}.`, 'gold')
          T += 3.6
        } else {
          cap(T, 'SUSPECTS', `Scores are in for ${Array.isArray(w.routes) ? w.routes.length : 0} routes.`)
          T += 2
        }
        endWave(T)
      } else if (w.purpose === 'swarm') {
        const sm = swarms.find((s) => s.wave === w.wave) || swarms.find((s) => s.check === w.check)
        cap(
          T,
          'SWARM',
          `Now the swarm: ${Array.isArray(w.routes) ? w.routes.length : '?'} rewrites of the culprit line × ${perRoute(w)} branches, all from checkpoint ${fork}. A winner must also pass held-out checks it never saw.`,
          'archil',
        )
        T = playWave(w, T, { tri: c, swarm: sm })
        if (sm) {
          const wins: any[] = (sm.rewrites ?? []).filter((r: any) => r.winner)
          cap(
            T,
            'SWARM',
            wins.length
              ? `${wins.length} of ${sm.n_rewrites ?? (sm.rewrites ?? []).length} rewrites pass the check and the held-out checks. Best: "${wins[0].text}"`
              : `No rewrite passed both the check and the held-out checks within budget.`,
            wins.length ? 'gold' : 'bad',
          )
          T += 3.8
        } else {
          cap(T, 'SWARM', `Swarm scores are in. Winners pending.`)
          T += 2
        }
        endWave(T)
      } else if (w.purpose === 'confirm') {
        closeTags(T)
        const c0 = (Array.isArray(w.copies) ? w.copies : [])[0]
        const a = mk(String(c0?.id ?? 'confirm'), String(c0?.id ?? 'confirm'), 'confirm: a fresh build from step 0 with the winning fix', GOLD)
        cap(T, 'CONFIRM', `One fresh build from step 0 with the winning fix.`, 'gold')
        seg(a, T, T + 0.4, at(0), at(0), FY, FY, 'idle')
        let t = T + 0.4
        for (let k = 1; k <= n; k++) {
          seg(a, t, t + 0.55, at(k - 1), at(k), FY, FY, 'walk')
          t += 0.55
          fires[k - 1].goldT = t
        }
        const text = triChecks.find((x) => x.confirm?.text)?.confirm?.text
        if (c0 && c0.passed === false) {
          seg(a, t, t + 0.5, at(n), at(n), FY, FY, 'fall')
          t += 0.5
          seg(a, t, t, at(n), at(n), FY, FY, 'dead')
          a.mark = { t, kind: 'dead' }
          cap(t, 'CONFIRM', text ?? `The confirm build did not pass.`, 'bad')
        } else {
          seg(a, t, t + 0.7, at(n), GATE_X - 16, FY, FY, 'walk')
          t += 0.7
          seg(a, t, t, GATE_X - 16, GATE_X - 16, FY, FY, 'cheer')
          a.mark = { t, kind: 'ok' }
          gateOpenT = t
          cap(t, 'CONFIRM', text ?? `The fixed spec builds clean from step 0.`, 'gold')
        }
        T = t + 3
      } else {
        cap(T, String(w.purpose || 'wave').toUpperCase(), `"${w.wave}": ${Array.isArray(w.copies) ? w.copies.length : num(w.n, 0)} copies branched from checkpoint ${fork}.`, 'archil')
        T = playWave(w, T, {})
        cap(T, String(w.purpose || 'wave').toUpperCase(), `"${w.wave}" finished in ${num(w.wall_s, 0) ? w.wall_s + ' s' : 'unknown time'}.`)
        T += 2.2
        endWave(T)
      }
    }
  }

  const complete = buildDone && !!d.triage && !!d.swarm
  if (complete) {
    const count = (v: string) => triChecks.filter((c) => c.verdict === v).length
    const bits: string[] = []
    if (count('real_problem')) bits.push(`${count('real_problem')} real problem${count('real_problem') === 1 ? '' : 's'} traced to its cause`)
    if (count('model_slip')) bits.push(`${count('model_slip')} model slip`)
    if (count('test_wrong')) bits.push(`${count('test_wrong')} wrong test`)
    if (count('inconclusive')) bits.push(`${count('inconclusive')} inconclusive`)
    cap(T, 'DONE', (bits.length ? `Run complete: ${bits.join(', ')}. ` : `Run complete. `) + `Click any character to open its report.`, 'gold')
    T += 0.6
  }

  // fold HUD events into states
  hudEv.sort((a, b) => a.t - b.t)
  const base: Hud = { checkpoints: 0, checkpointMs: null, branches: 0, live: 0, branchMs: null, sandboxMs: null, mountMs: null, savedSteps: null, savedMin: null }
  const hud: Timeline['hud'] = [{ t: -1, s: base }]
  let cur = base
  for (const e of hudEv) {
    cur = { ...cur }
    e.f(cur)
    hud.push({ t: e.t, s: cur })
  }
  captions.sort((a, b) => a.t - b.t)

  return {
    duration: T,
    n,
    built,
    stepX,
    at,
    fires,
    markers,
    actors,
    laneSets,
    captions,
    hud,
    footprints,
    tags,
    focus,
    gateOpenT,
    complete,
    hasCards: triChecks.length > 0,
  }
}

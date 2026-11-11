// The page reads only the orchestrator's run files (shapes: CONTRACT.md > Roles). Nothing here invents a number.
export type Json = any
export type RunInfo = { id: string; files: string[]; mtime: number; sizes?: Record<string, number>; meta?: Json; label?: string }
export type Caps = { python: string | null; pipeline: boolean; archilSdk: boolean; keys: { ARCHIL_API_KEY: boolean; ANTHROPIC_API_KEY: boolean }; fixtures: string[]; fixtureNames?: Record<string, string>; liveCmd?: boolean }
export type Job = { id: string; command: string; opts: Json; startedAt: number; endedAt: number | null; exitCode: number | null; running: boolean; runId: string | null; tail: string[] }
export type RunData = {
  id: string
  run?: Json
  triage?: Json
  results?: Json
  swarm?: Json
  archil?: Json
  baseline?: Json
  report?: Json
  before_after?: Json
  specOriginal?: string
  specFixed?: string
  sigs: Record<string, string>
  sig: string
}
// Static build (GitHub Pages, VITE_STATIC=1): run files are copied next to the page at build time
// (runs/index.json + runs/<id>/<file>); starting runs needs the local server, so it is off.
export const STATIC = import.meta.env.VITE_STATIC === '1'
const BASE = import.meta.env.BASE_URL
const runsUrl = (id?: string, file?: string): string =>
  STATIC
    ? `${BASE}runs/${id ? `${encodeURIComponent(id)}/${file}` : 'index.json'}`
    : `/api/runs${id ? `/${encodeURIComponent(id)}/${file}` : ''}`
export const asset = (p: string): string => `${BASE}${p.replace(/^\//, '')}`

const FILES = ['run', 'triage', 'results', 'swarm', 'archil', 'baseline', 'report', 'before_after'] as const

function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

export async function listRuns(): Promise<RunInfo[]> {
  const r = await fetch(runsUrl(), { cache: 'no-store' })
  if (!r.ok) throw new Error('runs api ' + r.status)
  return r.json()
}

const STATIC_CAPS: Caps = { python: null, pipeline: false, archilSdk: false,
  keys: { ARCHIL_API_KEY: false, ANTHROPIC_API_KEY: false }, fixtures: [] }
export const getCaps = (): Promise<Caps> =>
  STATIC ? Promise.resolve(STATIC_CAPS) : fetch('/api/caps', { cache: 'no-store' }).then((r) => r.json())
export const getJob = (): Promise<Job | null> =>
  STATIC ? Promise.resolve(null) : fetch('/api/job', { cache: 'no-store' })
    .then((r) => r.json())
    .then((j) => j.job ?? null)
export async function startRun(opts: Json): Promise<Job> {
  if (STATIC) throw new Error('runs can only be started from the machine that serves this page (this is the published copy)')
  const r = await fetch('/api/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.error || 'could not start the run')
  return j.job
}
export async function liveWave(runId: string, cmd: 'wave' | 'both' = 'wave'): Promise<Job> {
  if (STATIC) throw new Error('live waves can only be started from the machine that serves this page (this is the published copy)')
  const r = await fetch('/api/live', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ runId, cmd }) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.error || 'could not start the live wave')
  return j.job
}
export const stopRun = () => fetch('/api/stop', { method: 'POST' }).then((r) => r.json())

const TEXTS: [keyof RunData, string][] = [
  ['specOriginal', 'spec.original.md'],
  ['specFixed', 'spec.fixed.md'],
]

// `files` (from the run list) lets us skip files the folder doesn't have yet.
export async function loadRun(id: string, prev?: RunData | null, files?: string[]): Promise<RunData> {
  const out: RunData = { id, sigs: {}, sig: '' }
  const keep = prev && prev.id === id ? prev : null
  const want = (name: string) => !files || files.includes(name)
  await Promise.all(
    TEXTS.filter(([, name]) => want(name)).map(async ([key, name]) => {
      try {
        const r = await fetch(runsUrl(id, name), { cache: 'no-store' })
        if (!r.ok) return
        const txt = await r.text()
        ;(out as any)[key] = txt
        out.sigs[name] = txt.length + ':' + hash(txt)
      } catch {
        /* optional */
      }
    }),
  )
  await Promise.all(
    FILES.filter((f) => want(f + '.json')).map(async (f) => {
      try {
        const r = await fetch(runsUrl(id, `${f}.json`), { cache: 'no-store' })
        if (!r.ok) return
        const txt = await r.text()
        try {
          ;(out as any)[f] = JSON.parse(txt)
          out.sigs[f] = txt.length + ':' + hash(txt)
        } catch {
          // half-written file during a live run: keep the last good copy
          if (keep && (keep as any)[f]) {
            ;(out as any)[f] = (keep as any)[f]
            out.sigs[f] = keep.sigs[f]
          }
        }
      } catch {
        /* network blip: treat as missing this round */
      }
    }),
  )
  out.sig = FILES.map((f) => f + '=' + (out.sigs[f] || '-')).join('|') + '|' + TEXTS.map(([, n]) => out.sigs[n] || '-').join('|')
  return out
}

export function findCopy(d: RunData | null, copyId: string): { wave: Json; copy: Json; arch: Json | null } | null {
  for (const w of d?.results?.waves ?? [])
    for (const c of w.copies ?? [])
      if (c.id === copyId) {
        let arch: Json | null = null
        for (const aw of d?.archil?.waves ?? [])
          if (aw.wave === w.wave) for (const ac of aw.copies ?? []) if (ac.id === copyId) arch = ac
        return { wave: w, copy: c, arch }
      }
  return null
}

export const show = (v: any, unit = ''): string =>
  v === null || v === undefined || v === '' || v === 'unknown' || (typeof v === 'number' && !isFinite(v))
    ? 'unknown'
    : typeof v === 'number'
      ? (Number.isInteger(v) ? String(v) : v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2)) + unit
      : String(v) + unit

export function frac(s: any): { a: number; b: number } | null {
  const m = typeof s === 'string' ? s.match(/^(\d+)\s*\/\s*(\d+)$/) : null
  return m ? { a: Number(m[1]), b: Number(m[2]) } : null
}

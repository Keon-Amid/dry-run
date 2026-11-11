// The page reads only the orchestrator's run files (shapes: CONTRACT.md > Roles). Nothing here invents a number.
export type Json = any
export type RunInfo = { id: string; files: string[]; mtime: number; sizes?: Record<string, number> }
export type RunData = {
  id: string
  run?: Json
  triage?: Json
  results?: Json
  swarm?: Json
  archil?: Json
  sigs: Record<string, string>
  sig: string
}
const FILES = ['run', 'triage', 'results', 'swarm', 'archil'] as const

function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

export async function listRuns(): Promise<RunInfo[]> {
  const r = await fetch('/api/runs', { cache: 'no-store' })
  if (!r.ok) throw new Error('runs api ' + r.status)
  return r.json()
}

export async function loadRun(id: string, prev?: RunData | null): Promise<RunData> {
  const out: RunData = { id, sigs: {}, sig: '' }
  const keep = prev && prev.id === id ? prev : null
  await Promise.all(
    FILES.map(async (f) => {
      try {
        const r = await fetch(`/api/runs/${encodeURIComponent(id)}/${f}.json`, { cache: 'no-store' })
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
  out.sig = FILES.map((f) => f + '=' + (out.sigs[f] || '-')).join('|')
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

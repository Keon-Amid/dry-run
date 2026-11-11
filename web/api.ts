// The page's small backend, mounted on the Vite dev/preview server.
//   GET  /api/runs                 run folders, newest first, with a little metadata from run.json / triage.json
//   GET  /api/runs/<id>/<file>     one run file, read-only
//   GET  /api/caps                 what this machine can run (python, pipeline, archil SDK, which keys exist: names only)
//   GET  /api/job                  the pipeline process this server started, if any (state + last log lines)
//   POST /api/start                start `python -m orchestrator.pipeline ...` with allow-listed options (localhost only)
//   POST /api/live                 run `python -m orchestrator.live wave|both <run>` on a finished real run (localhost only)
//   POST /api/stop                 stop it (localhost only)
import fs from 'node:fs'
import path from 'node:path'
import { spawn, spawnSync, type ChildProcess } from 'node:child_process'

const NAME = /^[\w][\w.-]*$/
const FILE = /^[\w][\w.-]*\.(json|jsonl|md)$/
const FIXTURES = ['stub', 'toy', 'demo'] // fallback; the real list is read from the pipeline's own --help
const FIXTURE_NAMES: Record<string, string> = { stub: 'Stub', toy: 'Toy', demo: 'Shortlink', demo2: 'Dungeon Painter' }
const scrub = (s: string) =>
  s
    .replace(/sk-ant-[A-Za-z0-9_-]{6,}/g, 'sk-ant-…')
    .replace(/\bkey-[A-Za-z0-9]{16,}/g, 'key-…')
    .replace(/xox[abprs]-[A-Za-z0-9-]{8,}/g, 'xox…')

type Job = {
  id: string
  args: string[]
  opts: any
  startedAt: number
  endedAt: number | null
  exitCode: number | null
  runId: string | null
  log: string[]
  proc: ChildProcess | null
}

export function makeApi(repoRoot: string, RUNS: string) {
  const venvPy = path.join(repoRoot, '.venv/bin/python')
  const py = fs.existsSync(venvPy) ? venvPy : 'python3'
  let caps: any = null
  let job: Job | null = null

  const hasKey = (name: string): boolean => {
    if (process.env[name]) return true
    try {
      return new RegExp(`^\\s*${name}\\s*=\\s*\\S`, 'm').test(fs.readFileSync(path.join(repoRoot, '.env'), 'utf8'))
    } catch {
      return false
    }
  }
  const getCaps = () => {
    if (caps && Date.now() - caps.at < 20000) return caps
    const v = spawnSync(py, ['-c', 'import sys; print(sys.version.split()[0])'], { encoding: 'utf8' })
    const sdk = spawnSync(py, ['-c', 'import archil'], { cwd: repoRoot }).status === 0
    const help = spawnSync(py, ['-m', 'orchestrator.pipeline', '--help'], { cwd: repoRoot, encoding: 'utf8' })
    const fx = String(help.stdout || '').match(/--fixture \{([^}]+)\}/)
    const fixtures = fx ? fx[1].split(',').map((x) => x.trim()).filter((x) => /^[\w-]+$/.test(x)) : FIXTURES
    caps = {
      at: Date.now(),
      python: v.status === 0 ? String(v.stdout).trim() : null,
      pipeline: fs.existsSync(path.join(repoRoot, 'orchestrator/pipeline.py')),
      archilSdk: sdk,
      keys: { ARCHIL_API_KEY: hasKey('ARCHIL_API_KEY'), ANTHROPIC_API_KEY: hasKey('ANTHROPIC_API_KEY') },
      fixtures,
      fixtureNames: FIXTURE_NAMES,
      liveCmd: fs.existsSync(path.join(repoRoot, 'orchestrator/live.py')),
    }
    return caps
  }

  const jobView = () =>
    job
      ? {
          id: job.id,
          command: 'python ' + job.args.slice(1).join(' '),
          opts: job.opts,
          startedAt: job.startedAt,
          endedAt: job.endedAt,
          exitCode: job.exitCode,
          running: job.exitCode === null,
          runId: job.runId,
          tail: job.log.slice(-14),
        }
      : null

  const start = (o: any) => {
    if (job && job.exitCode === null) throw new Error('a run is already in progress')
    const c = getCaps()
    if (!c.python || !c.pipeline) throw new Error('python3 or orchestrator/pipeline.py is missing on this machine')
    const fixture = c.fixtures.includes(o?.fixture) ? o.fixture : 'stub'
    const builder = o?.builder === 'real' ? 'real' : 'stub'
    const local = o?.local !== false
    if (builder === 'real' && !c.keys.ANTHROPIC_API_KEY) throw new Error('the real builder needs ANTHROPIC_API_KEY on this machine')
    if (!local && (!c.keys.ARCHIL_API_KEY || !c.archilSdk)) throw new Error('an Archil run needs ARCHIL_API_KEY and the archil Python SDK on this machine')
    const args = ['-u', '-m', 'orchestrator.pipeline', '--fixture', fixture, '--builder', builder]
    if (local) args.push('--local')
    if (o?.smoke) args.push('--smoke')
    if (o?.noBaseline) args.push('--no-baseline')
    const copies = Number(o?.copies)
    if (Number.isInteger(copies) && copies >= 1 && copies <= 5) args.push('--copies', String(copies))
    const mb = Number(o?.maxBuilders)
    if (Number.isInteger(mb) && mb >= 1 && mb <= 64) args.push('--max-builders', String(mb))
    if (typeof o?.model === 'string' && /^[\w.-]{3,60}$/.test(o.model)) args.push('--model', o.model)
    return launch(args, { fixture, builder, local }, null)
  }

  // Edan's two extra commands on a finished real run: `wave` (a 3-copy judges' wave) and `both` (combined confirm).
  const live = (o: any) => {
    if (job && job.exitCode === null) throw new Error('a run is already in progress')
    const c = getCaps()
    const cmd = o?.cmd === 'both' ? 'both' : 'wave'
    const runId = String(o?.runId ?? '')
    if (!NAME.test(runId) || !fs.existsSync(path.join(RUNS, runId, 'run.json'))) throw new Error('unknown run')
    if (!fs.existsSync(path.join(repoRoot, 'orchestrator/live.py'))) throw new Error('orchestrator/live.py is missing')
    if (!c.keys.ANTHROPIC_API_KEY || !c.keys.ARCHIL_API_KEY || !c.archilSdk)
      throw new Error("a live wave needs ANTHROPIC_API_KEY, the run's own ARCHIL_API_KEY and the archil Python SDK on this machine")
    return launch(['-u', '-m', 'orchestrator.live', cmd, path.join(RUNS, runId)], { live: cmd }, runId)
  }

  const launch = (args: string[], opts: any, runId: string | null) => {
    const proc = spawn(py, args, { cwd: repoRoot, env: { ...process.env, PYTHONUNBUFFERED: '1' } })
    const j: Job = { id: String(Date.now()), args, opts, startedAt: Date.now(), endedAt: null, exitCode: null, runId, log: [], proc }
    const onData = (buf: any) => {
      for (const raw of String(buf).split(/\r?\n/)) {
        if (!raw.trim()) continue
        const line = scrub(raw).slice(0, 400)
        j.log.push(line)
        if (j.log.length > 300) j.log.shift()
        const m = raw.match(/^run dir:\s*(.+)$/)
        if (m) j.runId = path.basename(m[1].trim())
      }
    }
    proc.stdout?.on('data', onData)
    proc.stderr?.on('data', onData)
    proc.on('exit', (code, sig) => {
      j.exitCode = code ?? (sig ? -1 : 0)
      j.endedAt = Date.now()
      j.proc = null
    })
    proc.on('error', (e) => {
      j.log.push('could not start: ' + e.message)
      j.exitCode = -1
      j.endedAt = Date.now()
      j.proc = null
    })
    job = j
    return jobView()
  }

  const readJson = (p: string): any => {
    try {
      return JSON.parse(fs.readFileSync(p, 'utf8'))
    } catch {
      return null
    }
  }
  // Friendly names for the run picker (Edan's mapping): run.json `label` wins; otherwise fixture + who built it.
  const labelFor = (id: string, run: any, meta: any): string => {
    const m = id.match(/^\d{8}-(\d{2})(\d{2})\d{2}(?:-(.+))?$/)
    const time = m ? ` · ${m[1]}:${m[2]}` : ''
    if (typeof run?.label === 'string' && run.label.trim()) return run.label.trim() + time
    const tail = m?.[3] ?? ''
    const builder = String(meta?.builder ?? '')
    const real = /real/i.test(builder) || /-real(-|$)/.test(tail)
    const model = String(meta?.model ?? '')
    const mm = model.match(/(haiku|sonnet|opus|fable)/i)
    const who = mm ? mm[1][0].toUpperCase() + mm[1].slice(1).toLowerCase() : model || 'model unknown'
    const local = meta?.store && meta.store !== 'archil' ? ', local folders' : ''
    if (!real) return `Stub (fake agent)${local || (meta?.store === 'archil' ? ', on Archil' : '')}${time}`
    const fxName = (tail.match(/^([\w]+?)-(?:real|stub)/) || [])[1]
    if (fxName === 'toy') return `Toy: real-model smoke test (${who})${local}${time}`
    if (fxName) return `${FIXTURE_NAMES[fxName] ?? fxName}: real run (${who})${local}${time}`
    return `Real run (${who})${local}${time}`
  }
  const listRuns = () => {
    const ids = fs.existsSync(RUNS) ? fs.readdirSync(RUNS).filter((d) => NAME.test(d) && fs.statSync(path.join(RUNS, d)).isDirectory()) : []
    return ids
      .map((id) => {
        const dir = path.join(RUNS, id)
        const files = fs.readdirSync(dir).filter((f) => FILE.test(f))
        let mtime = 0
        const sizes: Record<string, number> = {}
        for (const f of files) {
          const st = fs.statSync(path.join(dir, f))
          mtime = Math.max(mtime, st.mtimeMs)
          sizes[f] = st.size
        }
        const run = files.includes('run.json') ? readJson(path.join(dir, 'run.json')) : null
        const tri = files.includes('triage.json') ? readJson(path.join(dir, 'triage.json')) : null
        const meta = run
          ? {
              builder: run.builder ?? null,
              model: run.model ?? null,
              store: run.store ?? null,
              n_steps: run.n_steps ?? null,
              built: Array.isArray(run.steps) ? run.steps.length : null,
              failing: Array.isArray(tri?.checks) ? tri.checks.length : null,
            }
          : null
        return { id, files, mtime, sizes, meta, label: labelFor(id, run, meta) }
      })
      .sort((a, b) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0))
  }

  const isLocal = (req: any) => ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket?.remoteAddress ?? '')
  const send = (res: any, code: number, body: any) => {
    res.statusCode = code
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify(body))
  }
  const body = (req: any): Promise<any> =>
    new Promise((resolve) => {
      let s = ''
      req.on('data', (c: any) => (s += c))
      req.on('end', () => {
        try {
          resolve(s ? JSON.parse(s) : {})
        } catch {
          resolve({})
        }
      })
    })

  return async (req: any, res: any, next: any) => {
    const url = String(req.url || '').split('?')[0]
    if (!url.startsWith('/api/')) return next()
    res.setHeader('Cache-Control', 'no-store')
    try {
      if (url === '/api/caps') return send(res, 200, getCaps())
      if (url === '/api/job') return send(res, 200, { job: jobView() })
      if (url === '/api/start' || url === '/api/stop' || url === '/api/live') {
        if (req.method !== 'POST') return send(res, 405, { error: 'POST only' })
        if (!isLocal(req)) return send(res, 403, { error: 'runs can only be started from the machine that serves this page' })
        if (url === '/api/stop') {
          if (job?.proc) job.proc.kill('SIGTERM')
          return send(res, 200, { job: jobView() })
        }
        try {
          if (url === '/api/live') return send(res, 200, { job: live(await body(req)) })
          return send(res, 200, { job: start(await body(req)) })
        } catch (e: any) {
          return send(res, 409, { error: String(e?.message || e) })
        }
      }
      if (url.startsWith('/api/runs')) {
        const parts = url.split('/').filter(Boolean).slice(2).map(decodeURIComponent)
        if (parts.length === 0) return send(res, 200, listRuns())
        if (parts.length === 2 && NAME.test(parts[0]) && FILE.test(parts[1])) {
          const p = path.join(RUNS, parts[0], parts[1])
          if (!fs.existsSync(p)) return send(res, 404, { error: 'not found' })
          res.setHeader('Content-Type', parts[1].endsWith('.json') ? 'application/json' : 'text/plain; charset=utf-8')
          res.end(fs.readFileSync(p))
          return
        }
      }
      send(res, 400, { error: 'bad request' })
    } catch (e: any) {
      send(res, 500, { error: String(e?.message || e) })
    }
  }
}

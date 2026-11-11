import { defineConfig, type Plugin } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Read-only API over the orchestrator's run folders. The page reads only these files.
const here = path.dirname(fileURLToPath(import.meta.url))
const RUNS = process.env.DRYRUN_RUNS_DIR || path.resolve(here, '../orchestrator/runs')
const NAME = /^[\w][\w.-]*$/
const FILE = /^[\w][\w.-]*\.(json|jsonl)$/

function runsApi(): Plugin {
  const handler = (req: any, res: any, next: any) => {
    const url = String(req.url || '').split('?')[0]
    if (!url.startsWith('/api/runs')) return next()
    res.setHeader('Cache-Control', 'no-store')
    try {
      const parts = url.split('/').filter(Boolean).slice(2).map(decodeURIComponent)
      if (parts.length === 0) {
        const ids = fs.existsSync(RUNS)
          ? fs.readdirSync(RUNS).filter((d) => NAME.test(d) && fs.statSync(path.join(RUNS, d)).isDirectory())
          : []
        const out = ids
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
            return { id, files, mtime, sizes }
          })
          .sort((a, b) => (a.id < b.id ? 1 : a.id > b.id ? -1 : 0))
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify(out))
        return
      }
      if (parts.length === 2 && NAME.test(parts[0]) && FILE.test(parts[1])) {
        const p = path.join(RUNS, parts[0], parts[1])
        if (!fs.existsSync(p)) {
          res.statusCode = 404
          res.end('not found')
          return
        }
        res.setHeader('Content-Type', parts[1].endsWith('.json') ? 'application/json' : 'text/plain; charset=utf-8')
        res.end(fs.readFileSync(p))
        return
      }
      res.statusCode = 400
      res.end('bad request')
    } catch (e: any) {
      res.statusCode = 500
      res.end(String(e?.message || e))
    }
  }
  return {
    name: 'dryrun-runs-api',
    configureServer(s) {
      s.middlewares.use(handler)
    },
    configurePreviewServer(s) {
      s.middlewares.use(handler)
    },
  }
}

export default defineConfig({
  plugins: [runsApi()],
  esbuild: { jsx: 'automatic' },
  server: { port: 5173 },
  preview: { port: 4173 },
})

import { defineConfig, type Plugin } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeApi } from './api'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..')
const RUNS = process.env.DRYRUN_RUNS_DIR || path.resolve(repoRoot, 'orchestrator/runs')

// VITE_STATIC=1 (GitHub Pages): after the build, ask the same API handler for the run list and copy every listed
// run file into dist/runs/, so the published page shows exactly what the local server would.
function staticRuns(): Plugin {
  return {
    name: 'banzai-static-runs',
    apply: 'build',
    async closeBundle() {
      if (process.env.VITE_STATIC !== '1') return
      const handler = makeApi(repoRoot, RUNS)
      const body: string = await new Promise((resolve, reject) => {
        const res: any = { statusCode: 200, setHeader() {}, end: (b: any) => resolve(String(b)) }
        handler({ url: '/api/runs', method: 'GET', headers: {} }, res, () => reject(new Error('no /api/runs')))
      })
      const runs = JSON.parse(body)
      const out = path.resolve(here, 'dist', 'runs')
      fs.mkdirSync(out, { recursive: true })
      fs.writeFileSync(path.join(out, 'index.json'), JSON.stringify(runs))
      for (const r of runs)
        for (const f of r.files ?? []) {
          fs.mkdirSync(path.join(out, r.id), { recursive: true })
          fs.copyFileSync(path.join(RUNS, r.id, f), path.join(out, r.id, f))
        }
      console.log(`static runs: ${runs.length} runs copied to dist/runs`)
    },
  }
}

function runsApi(): Plugin {
  const handler = makeApi(repoRoot, RUNS)
  return {
    name: 'banzai-api',
    configureServer(s) {
      s.middlewares.use(handler)
    },
    configurePreviewServer(s) {
      s.middlewares.use(handler)
    },
  }
}

export default defineConfig({
  base: process.env.VITE_STATIC === '1' ? './' : '/',
  plugins: [runsApi(), staticRuns()],
  esbuild: { jsx: 'automatic' },
  server: { port: 5173 },
  preview: { port: 4173 },
})

import { defineConfig, type Plugin } from 'vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeApi } from './api'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..')
const RUNS = process.env.DRYRUN_RUNS_DIR || path.resolve(repoRoot, 'orchestrator/runs')

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
  plugins: [runsApi()],
  esbuild: { jsx: 'automatic' },
  server: { port: 5173 },
  preview: { port: 4173 },
})

import { useEffect, useState } from 'react'
import { getCaps, startRun, type Caps, type Job } from './data'

type Picked = { path: string; size: number }

// NEW RUN: start the real pipeline from the page, then follow it live.
// It runs `python -m orchestrator.pipeline` on the machine that serves this page, with the options chosen here.
export function Upload({ onClose, onStarted, job }: { onClose: () => void; onStarted: (j: Job) => void; job: Job | null }) {
  const [caps, setCaps] = useState<Caps | null>(null)
  const [builder, setBuilder] = useState<'stub' | 'real'>('stub')
  const [fixture, setFixture] = useState('stub')
  const [local, setLocal] = useState(true)
  const [smoke, setSmoke] = useState(false)
  const [noBaseline, setNoBaseline] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [files, setFiles] = useState<Picked[]>([])
  const [steps, setSteps] = useState<number | null>(null)

  useEffect(() => {
    getCaps()
      .then((c) => {
        setCaps(c)
        // default to the most real thing this machine can run
        const real = c.keys.ANTHROPIC_API_KEY
        const archil = c.keys.ARCHIL_API_KEY && c.archilSdk
        setBuilder(real ? 'real' : 'stub')
        setFixture(real && c.fixtures.includes('demo') ? 'demo' : 'stub')
        setLocal(!archil)
      })
      .catch(() => setErr('Cannot reach the page server.'))
  }, [])

  const canReal = !!caps?.keys.ANTHROPIC_API_KEY
  const canArchil = !!caps?.keys.ARCHIL_API_KEY && !!caps?.archilSdk
  const fixtureOk = (f: string) => (builder === 'stub' ? f === 'stub' : true)
  const skipBaseline = builder === 'stub' ? true : noBaseline
  const args = ['--fixture', fixture, '--builder', builder]
  if (local) args.push('--local')
  if (smoke) args.push('--smoke')
  if (skipBaseline) args.push('--no-baseline')
  const running = !!job?.running
  const ready = !!caps?.python && !!caps?.pipeline && !running && !busy

  const go = async () => {
    setErr('')
    setBusy(true)
    try {
      onStarted(await startRun({ fixture, builder, local, smoke, noBaseline: skipBaseline }))
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  const pick = async (list: FileList | null) => {
    if (!list) return
    const arr = Array.from(list)
    setFiles(arr.map((f) => ({ path: (f as any).webkitRelativePath || f.name, size: f.size })))
    const spec = arr.find((f) => /(^|\/)spec\.md$/i.test((f as any).webkitRelativePath || f.name))
    setSteps(spec ? ((await spec.text()).match(/^##\s*Step\s+\d+/gim) || []).length : null)
  }
  const has = (re: RegExp) => files.some((f) => re.test(f.path))
  const parts: [string, boolean][] = [
    ['spec.md', has(/(^|\/)spec\.md$/i)],
    ['rules/', has(/(^|\/)rules\//i)],
    ['checks/', has(/(^|\/)checks\//i)],
    ['checks_heldout/', has(/(^|\/)checks_heldout\//i)],
    ['golden/', has(/(^|\/)golden\//i)],
  ]

  const Opt = ({ on, set, ok = true, children, why }: { on: boolean; set: () => void; ok?: boolean; children: any; why?: string }) => (
    <button className={'opt' + (on ? ' on' : '')} disabled={!ok} onClick={set} title={ok ? '' : why}>
      {children}
      {!ok && why ? <small>{why}</small> : null}
    </button>
  )

  return (
    <div className="cards" onClick={onClose}>
      <div className="scroll upload" onClick={(e) => e.stopPropagation()}>
        <h2>NEW RUN</h2>
        <p className="cardtext">Starts the real pipeline on this machine and follows it live: build step by step, checkpoint every step, triage, suspects, swarm, confirm.</p>
        <div className="optrow">
          <b>WHO BUILDS</b>
          <Opt
            on={builder === 'stub'}
            set={() => {
              setBuilder('stub')
              setFixture('stub')
            }}
          >
            Stub agent<small>scripted, no model calls</small>
          </Opt>
          <Opt
            on={builder === 'real'}
            ok={canReal}
            why="needs ANTHROPIC_API_KEY on this machine"
            set={() => {
              setBuilder('real')
              setFixture(caps?.fixtures.includes('demo') ? 'demo' : (caps?.fixtures.find((f) => f !== 'stub') ?? 'stub'))
            }}
          >
            Real builder (Claude)
          </Opt>
        </div>
        <div className="optrow">
          <b>WHAT SPEC</b>
          {(caps?.fixtures ?? ['stub']).map((f) => (
            <Opt key={f} on={fixture === f} ok={fixtureOk(f)} why="needs the real builder" set={() => setFixture(f)}>
              {f === 'stub' ? 'Stub spec' : `${caps?.fixtureNames?.[f] ?? f}${f.startsWith('demo') ? ' demo' : ''}`}
              <small>{f === 'stub' ? 'scripted checks' : f === 'toy' ? '3 steps' : 'real checks'}</small>
            </Opt>
          ))}
        </div>
        <div className="optrow">
          <b>WHERE</b>
          <Opt on={local} set={() => setLocal(true)}>
            Local folders<small>no Archil</small>
          </Opt>
          <Opt on={!local} ok={canArchil} why={!caps?.keys.ARCHIL_API_KEY ? 'needs ARCHIL_API_KEY' : 'needs the archil Python SDK (pip install archil)'} set={() => setLocal(false)}>
            Archil disk + sandboxes
          </Opt>
        </div>
        <div className="optrow">
          <b>OPTIONS</b>
          <Opt on={smoke} set={() => setSmoke((s) => !s)}>
            Build + triage only
          </Opt>
          <Opt on={skipBaseline} ok={builder === 'real'} why="the baseline needs a model call" set={() => setNoBaseline((s) => !s)}>
            Skip the plain-Claude baseline
          </Opt>
        </div>
        <div className="stubnote">
          <code>python -m orchestrator.pipeline {args.join(' ')}</code>
        </div>
        {caps && (!caps.python || !caps.pipeline) && <div className="stubnote">python3 or orchestrator/pipeline.py is missing on this machine, so runs can't start here.</div>}
        {running && <div className="stubnote">A run is already in progress: {job?.runId ?? 'starting'}.</div>}
        {err && <div className="stubnote">{err}</div>}
        <div className="uploadbar">
          <button className="btn on" disabled={!ready} onClick={go}>
            {busy ? 'STARTING…' : 'START RUN'}
          </button>
          <button className="btn" onClick={onClose}>
            CLOSE
          </button>
        </div>
        <details className="own">
          <summary>Your own spec bundle (not wired yet)</summary>
          <p className="cardtext">The pipeline takes its named bundles today. This only checks that a folder has the parts a run needs.</p>
          <label className="drop">
            <input type="file" multiple {...({ webkitdirectory: '', directory: '' } as any)} onChange={(e) => pick(e.target.files)} />
            <span>{files.length ? `${files.length} files chosen` : 'Choose a bundle folder'}</span>
          </label>
          <ul className="checks">
            {parts.map(([name, ok]) => (
              <li key={name} className={files.length ? (ok ? 'ok' : 'no') : ''}>
                {files.length ? (ok ? '✓' : '✗') : '·'} <b>{name}</b>
              </li>
            ))}
          </ul>
          {steps != null && (
            <div className="row">
              <span>steps found in spec.md</span>
              <em>{steps}</em>
            </div>
          )}
        </details>
      </div>
    </div>
  )
}

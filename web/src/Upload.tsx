import { useEffect, useState } from 'react'
import { getCaps, startRun, type Caps, type Job } from './data'

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
  const [specText, setSpecText] = useState('')
  const [specName, setSpecName] = useState('')
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
      onStarted(await startRun({ fixture, builder, local, smoke, noBaseline: skipBaseline, specText: specText || undefined }))
    } catch (e: any) {
      setErr(String(e?.message || e))
    } finally {
      setBusy(false)
    }
  }

  const pick = async (list: FileList | null) => {
    const f = list?.[0]
    if (!f) return
    const txt = await f.text()
    setSpecText(txt)
    setSpecName(f.name)
    setSteps((txt.match(/^##\s*Step\s+\d+/gim) || []).length)
    if (canReal) {
      setBuilder('real')
      if (fixture === 'stub') setFixture(caps?.fixtures.includes('demo') ? 'demo' : (caps?.fixtures.find((x) => x !== 'stub') ?? 'stub'))
    }
  }
  const bundleName = fixture === 'stub' ? 'stub' : `${caps?.fixtureNames?.[fixture] ?? fixture}`

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
          <code>{specText ? `python web/tools/run_spec.py --spec ${specName || 'spec.md'} ${args.join(' ')}` : `python -m orchestrator.pipeline ${args.join(' ')}`}</code>
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
        <div className="own">
          <label className="drop">
            <input type="file" accept=".md,.txt,text/markdown,text/plain" onChange={(e) => pick(e.target.files)} />
            <span>{specName ? `YOUR SPEC: ${specName} · ${steps ?? 0} steps` : 'UPLOAD YOUR SPEC (a .md file with "## Step 1", "## Step 2", ... headings)'}</span>
          </label>
          {specText ? (
            <p className="cardtext">
              Your spec replaces the {bundleName} spec. It is built by the real builder and graded with the {bundleName} checks, so it has to be a spec for that same project.{' '}
              {builder !== 'real' ? 'Choose the real builder: the stub agent ignores the spec. ' : ''}
              <button className="mini" onClick={() => (setSpecText(''), setSpecName(''), setSteps(null))}>
                REMOVE
              </button>
            </p>
          ) : (
            <p className="cardtext">No file chosen: the run uses the bundle's own spec.</p>
          )}
        </div>
      </div>
    </div>
  )
}

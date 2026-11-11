import { useEffect, useMemo, useRef, useState } from 'react'
import { getJob, listRuns, loadRun, show, stopRun, type Job, type RunData, type RunInfo } from './data'
import { buildTimeline, captionAt, hudAt, W, H, type Caption, type Hud, type Timeline } from './timeline'
import { Scene } from './scene'
import { Cards } from './Cards'
import { Report } from './Report'
import { Upload } from './Upload'

const qs = new URLSearchParams(location.search)

function useHash() {
  const [h, setH] = useState(location.hash)
  useEffect(() => {
    const f = () => setH(location.hash)
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])
  return h
}

export default function App() {
  const hash = useHash()
  const m = hash.match(/^#\/run\/([^/]+)\/copy\/(.+)$/)
  const report = m ? { runId: decodeURIComponent(m[1]), copyId: decodeURIComponent(m[2]) } : null
  return (
    <>
      <Main reportOpen={!!report} preferRun={report?.runId ?? null} />
      {report && <Report runId={report.runId} copyId={report.copyId} onClose={() => (location.hash = '')} />}
    </>
  )
}

const Stat = ({ k, v, tone }: { k: string; v: any; tone?: string }) => (
  <div className={'stat ' + (tone ?? '')}>
    <b>{k}</b>
    <span>{v}</span>
  </div>
)

function Main({ reportOpen, preferRun }: { reportOpen: boolean; preferRun: string | null }) {
  const [runs, setRuns] = useState<RunInfo[]>([])
  const [runId, setRunId] = useState<string | null>(qs.get('run') || preferRun)
  const [data, setData] = useState<RunData | null>(null)
  const [playing, setPlaying] = useState(qs.get('paused') !== '1')
  const [speed, setSpeed] = useState(Number(qs.get('speed')) || 1)
  const [live, setLive] = useState(qs.get('live') === '1')
  const [showCards, setShowCards] = useState(qs.get('cards') === '1')
  const [showUpload, setShowUpload] = useState(qs.get('upload') === '1')
  const [ui, setUi] = useState<{ t: number; cap: Caption | null; hud: Hud | null; ended: boolean; finished: boolean }>({ t: 0, cap: null, hud: null, ended: false, finished: false })
  const [job, setJob] = useState<Job | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<Scene | null>(null)
  const tRef = useRef(Number(qs.get('t')) || 0)
  const firstLoad = useRef(true)
  const tl = useMemo<Timeline | null>(() => (data ? buildTimeline(data) : null), [data])
  const st = useRef({ playing, speed, reportOpen, live, tl, data, runId, job, runs, cardsFor: '', lastChange: Date.now(), lastSig: '' })
  Object.assign(st.current, { playing, speed, reportOpen, live, tl, data, runId, job, runs })
  if (data && st.current.lastSig !== data.id + data.sig) {
    st.current.lastSig = data.id + data.sig
    st.current.lastChange = Date.now()
  }
  if (sceneRef.current) sceneRef.current.tl = tl
  // keep the HUD and caption in step with freshly loaded data, even while paused
  useEffect(() => {
    if (!tl) return
    const t = Math.min(tRef.current, tl.duration)
    setUi((u) => ({ ...u, t, cap: captionAt(tl, t), hud: hudAt(tl, t), ended: t >= tl.duration - 0.001 }))
  }, [tl])

  // run list, the pipeline job, and live polling (every 2 s)
  useEffect(() => {
    let stop = false
    const poll = async () => {
      try {
        const [rs, jb] = await Promise.all([listRuns(), getJob().catch(() => null)])
        if (stop) return
        setRuns((prev) => (JSON.stringify(prev.map((r) => [r.id, r.label, r.files.length])) === JSON.stringify(rs.map((r) => [r.id, r.label, r.files.length])) ? prev : rs))
        setJob((prev) => (JSON.stringify(prev) === JSON.stringify(jb) ? prev : jb))
        setErr(null)
        const s = st.current
        const has = (id: string | null | undefined) => !!id && rs.some((r) => r.id === id)
        // default: the newest real run with triage results, else the newest with triage results, else the newest
        const withTriage = rs.filter((r) => (r.sizes?.['triage.json'] ?? 0) > 120)
        const preferred = withTriage.find((r) => /real/i.test(String(r.meta?.builder ?? ''))) ?? withTriage[0] ?? rs[0]
        if (!s.runId && rs.length) setRunId(preferred.id)
        else if (s.live && rs.length) {
          // LIVE follows the run the pipeline is writing, otherwise the newest folder
          const target = jb?.running && has(jb.runId) ? jb.runId! : rs[0].id
          if (target !== s.runId) {
            tRef.current = 0
            st.current.cardsFor = ''
            setRunId(target)
            return
          }
        }
        if (s.live && s.runId && s.data) {
          const d = await loadRun(s.runId, s.data, rs.find((r) => r.id === s.runId)?.files)
          if (!stop && st.current.runId === d.id && d.sig !== st.current.data?.sig) setData(d)
        }
      } catch (e) {
        setErr('Cannot reach the runs folder: ' + String(e))
      }
    }
    poll()
    const iv = setInterval(poll, 2000)
    return () => {
      stop = true
      clearInterval(iv)
    }
  }, [])

  useEffect(() => {
    if (!runId) return
    let stop = false
    setData(null)
    if (!firstLoad.current) tRef.current = 0
    firstLoad.current = false
    if (qs.get('cards') !== '1') setShowCards(false)
    loadRun(runId, null, st.current.runs.find((r) => r.id === runId)?.files)
      .then((d) => !stop && setData(d))
      .catch((e) => setErr(String(e)))
    return () => {
      stop = true
    }
  }, [runId])

  // canvas + render loop
  useEffect(() => {
    const sc = new Scene(canvasRef.current!)
    sceneRef.current = sc
    sc.tl = st.current.tl
    const fit = () => {
      const r = stageRef.current!.getBoundingClientRect()
      sc.resize(r.width - 8, r.height - 8)
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(stageRef.current!)
    const fonts = (document as any).fonts
    fonts?.load('16px VT323')
    fonts?.load('8px "Press Start 2P"')
    let raf = 0
    let last = performance.now()
    let acc = 1
    let key = ''
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const s = st.current
      const T = s.tl
      if (T) {
        if (s.playing && !s.reportOpen) tRef.current += dt * s.speed
        if (tRef.current > T.duration) tRef.current = T.duration
      }
      sc.render(tRef.current, now / 1000)
      acc += dt
      if (acc >= 0.1 && T) {
        acc = 0
        const cap = captionAt(T, tRef.current)
        const hud = hudAt(T, tRef.current)
        const ended = tRef.current >= T.duration - 0.001
        // A run is finished when its files are complete and nothing is still writing them.
        const jobHere = s.job && s.job.runId === s.data?.id ? s.job : null
        const finished = T.complete && !jobHere?.running && (!s.live || !!s.data?.report || !!jobHere || Date.now() - s.lastChange > 12000)
        const k = Math.round(tRef.current * 5) + '|' + (cap?.t ?? '') + '|' + JSON.stringify(hud) + '|' + ended + '|' + finished + '|' + T.duration
        if (k !== key) {
          key = k
          setUi({ t: tRef.current, cap, hud, ended, finished })
        }
        const sig = s.data?.id ?? ''
        if (ended && finished && T.hasCards && s.playing && s.cardsFor !== sig) {
          s.cardsFor = sig
          setShowCards(true)
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      sc.dispose()
    }
  }, [])

  const restart = () => {
    tRef.current = 0
    st.current.cardsFor = ''
    setShowCards(false)
    setPlaying(true)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (st.current.reportOpen || ['SELECT', 'INPUT'].includes((e.target as HTMLElement)?.tagName)) return
      if (e.code === 'Space') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.key === 'r' || e.key === 'R') restart()
      else if (e.key === '1') setSpeed(1)
      else if (e.key === '2') setSpeed(4)
      else if (e.key === '3') setSpeed(16)
      else if (e.key === 'l' || e.key === 'L') setLive((l) => !l)
      else if (e.key === 'c' || e.key === 'C') setShowCards((c) => !c)
      else if (e.key === 'n' || e.key === 'N') setShowUpload((u) => !u)
      else if (e.key === 'ArrowRight') tRef.current += 2
      else if (e.key === 'ArrowLeft') tRef.current = Math.max(0, tRef.current - 2)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])

  const toLogical = (e: React.MouseEvent): [number, number] => {
    const r = canvasRef.current!.getBoundingClientRect()
    return [((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H]
  }
  const onMove = (e: React.MouseEvent) => {
    const sc = sceneRef.current
    if (!sc) return
    const [x, y] = toLogical(e)
    const a = sc.hit(x, y)
    sc.hoverId = a?.id ?? null
    canvasRef.current!.style.cursor = a ? 'pointer' : 'default'
    setTip(a ? { x: e.clientX, y: e.clientY, text: a.label } : null)
  }
  const onClick = (e: React.MouseEvent) => {
    const [x, y] = toLogical(e)
    const a = sceneRef.current?.hit(x, y)
    if (a && runId) location.hash = `#/run/${encodeURIComponent(runId)}/copy/${encodeURIComponent(a.reportId)}`
  }

  // one jump button per phase of the story, for presenting
  const phases = useMemo(() => {
    const out: { phase: string; t: number }[] = []
    for (const c of tl?.captions ?? []) if (!out.some((p) => p.phase === c.phase)) out.push({ phase: c.phase, t: c.t })
    return out
  }, [tl])
  const hud = ui.hud
  const arch = data?.archil
  const run = data?.run
  const waiting = !!tl && ui.ended && !ui.finished
  const jobHere = job && (job.runId === runId || (job.running && !job.runId)) ? job : null
  const jobFailed = !!job && !job.running && job.exitCode !== 0 && job.exitCode !== null && (job.runId === runId || !job.runId)
  const localStore = !!run?.store && run.store !== 'archil'
  const usd = arch?.spent?.total?.usd
  const capText = err
    ? err
    : jobFailed
      ? `The pipeline stopped with exit code ${job!.exitCode}: ${job!.tail[job!.tail.length - 1] ?? 'no output'}`
      : !runId
      ? 'No runs found in orchestrator/runs/ yet.'
      : !tl
        ? 'Loading the run files…'
        : waiting
          ? live
            ? jobHere?.running
              ? `The pipeline is running (${Math.max(0, Math.round((Date.now() - jobHere.startedAt) / 1000))} s). ${jobHere.tail[jobHere.tail.length - 1] ?? ''}`
              : `Following this run live. Waiting for the orchestrator to write more.`
            : `This run's files end here. Turn on LIVE to follow it as the orchestrator writes more.`
          : (ui.cap?.text ?? '')
  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">BANZAI</div>
        <div className="tagline">your agent failed. whose fault was it?</div>
        <select
          className="btn"
          value={runId ?? ''}
          onChange={(e) => {
            setLive(false)
            tRef.current = 0
            setRunId(e.target.value)
          }}
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id} title={r.id}>
              {r.label ?? 'run ' + r.id}
            </option>
          ))}
        </select>
        <button className="btn" onClick={() => setPlaying((p) => !p)}>
          {playing ? 'PAUSE' : 'PLAY'}
        </button>
        <button className="btn" onClick={restart}>
          RESTART
        </button>
        {[1, 4, 16].map((s) => (
          <button key={s} className={'btn' + (speed === s ? ' on' : '')} onClick={() => setSpeed(s)}>
            {s}x
          </button>
        ))}
        <button className={'btn' + (live ? ' on' : '')} onClick={() => setLive((l) => !l)}>
          LIVE
        </button>
        <input
          className="scrub"
          type="range"
          min={0}
          max={tl?.duration ?? 1}
          step={0.05}
          value={Math.min(ui.t, tl?.duration ?? 1)}
          onChange={(e) => {
            tRef.current = Number(e.target.value)
            setUi((u) => ({ ...u, t: tRef.current }))
          }}
        />
        <button className={'btn' + (showCards ? ' on' : '')} disabled={!tl?.hasCards} onClick={() => setShowCards((s) => !s)}>
          CARDS
        </button>
        <button className="btn new" onClick={() => setShowUpload(true)} title="upload a spec bundle (N)">
          + NEW RUN
        </button>
      </header>
      <div className="hud">
        {localStore ? (
          <Stat k="STORE" tone="warn" v="local, not Archil" />
        ) : (
          <Stat k="ARCHIL DISK" v={run?.disk_id ? String(run.disk_id).replace(/^(dsk-)0+/, '$1…') : 'unknown'} />
        )}
        <Stat k="CHECKPOINTS" v={`${hud?.checkpoints ?? 0}/${tl?.n ?? '?'} · last ${show(hud?.checkpointMs, ' ms')}`} />
        <Stat k="BRANCHES" v={`${hud?.branches ?? 0} made · ${hud?.live ?? 0} running`} />
        <Stat k="BRANCH · SANDBOX · MOUNT" v={hud?.branchMs == null && hud?.sandboxMs == null ? '—' : `${show(hud?.branchMs)} · ${show(hud?.sandboxMs)} · ${show(hud?.mountMs)} ms`} />
        <Stat k="REPLAY AVOIDED" tone="gold" v={hud?.savedSteps == null ? '—' : `${show(hud.savedSteps)} steps · ${show(hud.savedMin, ' min')}`} />
        <Stat
          k="RESTORE: BRANCH VS GIT"
          tone="gold"
          v={`${show(arch?.restore_baseline?.branch_plus_mount_s, ' s')} vs ${show(arch?.restore_baseline?.git_clone_plus_install_s, ' s')}`}
        />
        <Stat
          k="SPENT"
          v={
            arch?.spent?.total && (typeof arch.spent.total.model_calls === 'number' || typeof usd === 'number')
              ? `${show(arch.spent.total.model_calls)} calls · ${typeof usd === 'number' ? '$' + (usd < 1 ? usd.toFixed(4) : usd.toFixed(2)) : 'cost unknown'}`
              : 'unknown'
          }
        />
        {job && (
          <div className={'stat ' + (job.running ? 'run' : job.exitCode === 0 ? 'ok' : 'warn')}>
            <b>PIPELINE</b>
            <span>
              {job.running ? `running ${Math.max(0, Math.round((Date.now() - job.startedAt) / 1000))} s` : job.exitCode === 0 ? `finished in ${(((job.endedAt ?? job.startedAt) - job.startedAt) / 1000).toFixed(1)} s` : `failed (exit ${job.exitCode})`}
              {job.running && (
                <button className="mini" onClick={() => stopRun()}>
                  STOP
                </button>
              )}
            </span>
          </div>
        )}
      </div>
      <div className="stage" ref={stageRef}>
        <canvas ref={canvasRef} onMouseMove={onMove} onMouseLeave={() => setTip(null)} onClick={onClick} />
        {showCards && data && <Cards data={data} onClose={() => setShowCards(false)} />}
        {showUpload && (
          <Upload
            job={job}
            onClose={() => setShowUpload(false)}
            onStarted={(j) => {
              setJob(j)
              setShowUpload(false)
              setShowCards(false)
              st.current.cardsFor = ''
              tRef.current = 0
              setLive(true)
              setPlaying(true)
            }}
          />
        )}
      </div>
      <footer className={'caption ' + (jobFailed ? 'bad' : waiting ? 'archil' : (ui.cap?.tone ?? 'info'))}>
        <span className="phase">{jobFailed ? 'FAILED' : waiting ? (live ? 'LIVE' : 'END OF FILES') : (ui.cap?.phase ?? '…')}</span>
        <span className="captext">{capText}</span>
        <span className="jumps">
          {phases.map((p) => (
            <button
              key={p.phase}
              className={'jump' + (!waiting && ui.cap?.phase === p.phase ? ' on' : '')}
              title={`jump to ${p.phase}`}
              onClick={() => {
                tRef.current = p.t
                st.current.cardsFor = ''
                setShowCards(false)
                setUi((u) => ({ ...u, t: p.t }))
              }}
            >
              {p.phase}
            </button>
          ))}
        </span>
      </footer>
      {tip && (
        <div className="tip" style={{ left: tip.x + 14, top: tip.y + 16 }}>
          {tip.text}
          <i>click to open its report</i>
        </div>
      )}
    </div>
  )
}

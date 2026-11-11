import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { findCopy, loadRun, show, type RunData } from './data'
import { Spr } from './Spr'

const NR = <i className="nr">not recorded</i>

// The death report: one copy of the agent, everything the run files say about it, and a QR code to this page.
export function Report({ runId, copyId, onClose }: { runId: string; copyId: string; onClose: () => void }) {
  const [d, setD] = useState<RunData | null>(null)
  const [qr, setQr] = useState('')
  const [err, setErr] = useState('')
  useEffect(() => {
    setD(null)
    loadRun(runId, null)
      .then(setD)
      .catch((e) => setErr(String(e)))
  }, [runId])
  useEffect(() => {
    QRCode.toDataURL(location.href, { margin: 1, scale: 5, color: { dark: '#07060C', light: '#E8D8B0' } })
      .then(setQr)
      .catch(() => setQr(''))
  }, [runId, copyId])

  let body: any = <p>Loading…</p>
  if (err) body = <p>Could not load run {runId}.</p>
  else if (d) body = copyId === 'build' ? <BuildReport d={d} /> : <CopyReport d={d} copyId={copyId} />
  return (
    <div className="report">
      <div className="sheet">
        <div className="sheetbar">
          <button className="btn" onClick={onClose}>
            ← BACK TO THE RUN
          </button>
          <span>run {runId}</span>
        </div>
        {body}
        <div className="qr">
          {qr ? <img src={qr} alt="QR code to this report" /> : null}
          <div>
            <b>Open this report on your phone</b>
            <span>{location.href}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function Checks({ checks, target }: { checks: any; target?: string | null }) {
  const es = Object.entries(checks || {})
  if (!es.length) return <p>{NR}</p>
  return (
    <ul className="checks">
      {es.map(([k, v]) => (
        <li key={k} className={v === true ? 'ok' : v === false ? 'no' : ''}>
          {v === true ? '✓' : v === false ? '✗' : '?'} {k}
          {target && k === target ? ' (the check this wave tests)' : ''}
        </li>
      ))}
    </ul>
  )
}

function CopyReport({ d, copyId }: { d: RunData; copyId: string }) {
  const hit = findCopy(d, copyId)
  if (!hit) return <p>No copy named “{copyId}” in this run’s results.json.</p>
  const { wave: w, copy: c, arch } = hit
  const sm = (d.swarm?.swarms ?? []).find((s: any) => s.wave === w.wave)
  const held: string[] = sm?.heldout_checks ?? []
  const invalid = c.invalid === true || c.ok === false
  const heldFail = !!sm && c.passed === true && held.some((h) => c.checks?.[h] === false)
  const status = invalid ? 'LOST: RUN INVALID' : heldFail ? 'DIED AT THE HELD-OUT GATE' : c.passed === true ? 'SURVIVED' : c.passed === false ? 'DIED' : 'UNKNOWN'
  const good = status === 'SURVIVED'
  const failing = Object.entries(c.checks || {})
    .filter(([, v]) => v === false)
    .map(([k]) => k)
  const carried =
    c.kind === 'control'
      ? 'Nothing. This is a control copy.'
      : c.kind === 'none'
        ? 'Nothing. A plain rebuild from the checkpoint.'
        : c.kind === 'rule_off'
          ? `Harness rule switched off: ${c.edit ?? 'unknown'}`
          : c.kind === 'spec_line'
            ? `Spec line rewritten to: “${c.edit ?? 'unknown'}”`
            : c.edit != null
              ? String(c.edit)
              : 'unknown'
  const tm = c.timings_ms || {}
  const b = c.builder || {}
  return (
    <>
      <div className={'verdict ' + (good ? 'good' : 'bad')}>
        <Spr name={good ? 'hero_cheer' : invalid ? 'grave' : 'skull'} scale={5} />
        <div>
          <h1>{status}</h1>
          <div className="mono">{c.id}</div>
        </div>
      </div>
      <dl>
        <dt>Wave</dt>
        <dd>
          {w.wave} ({w.purpose ?? 'unknown'}), route “{c.route}”
        </dd>
        <dt>What it carried</dt>
        <dd>{carried}</dd>
        <dt>Where it came from</dt>
        <dd>
          Branched from checkpoint {show(w.fork_step)} ({w.checkpoint_id ?? 'id unknown'}), ran to step {show(w.to_step)}. Steps 1 to {show(w.fork_step)} were not rebuilt.
        </dd>
        <dt>{good ? 'Result' : 'Where it died'}</dt>
        <dd>
          {good
            ? 'Passed the check this wave tests.'
            : failing.length
              ? `Failing checks: ${failing.join(', ')}. `
              : c.error
                ? `Error: ${c.error}. `
                : ''}
          {!good && <>First failing step: {c.first_fail_step != null ? show(c.first_fail_step) : NR}</>}
        </dd>
        <dt>Checks</dt>
        <dd>
          <Checks checks={c.checks} target={w.check} />
        </dd>
        <dt>Archil</dt>
        <dd>
          branch “{c.branch ?? 'unknown'}” · branch disk {c.branch_disk_id ?? NR}
          <br />
          branch {show(tm.branch ?? arch?.branch_ms, ' ms')} · sandbox {show(tm.sandbox ?? arch?.sandbox_ms, ' ms')} · mount {show(tm.mount ?? arch?.mount_ms, ' ms')} · total {show(c.wall_s, ' s')}
        </dd>
        <dt>Builder</dt>
        <dd>
          {b.builder ?? 'unknown'} · built steps {Array.isArray(b.built) ? b.built.join(', ') || 'none' : 'unknown'} · model calls {show(b.model_calls)} · exit {show(b.exit_code)}
        </dd>
        <dt>Last words</dt>
        <dd>{c.last_words ?? b.last_words ?? b.last_message ?? NR}</dd>
        <dt>Its notes</dt>
        <dd>{c.notes ?? b.notes ?? NR}</dd>
      </dl>
    </>
  )
}

function BuildReport({ d }: { d: RunData }) {
  const run = d.run || {}
  const steps: any[] = Array.isArray(run.steps) ? run.steps : []
  const seen = new Set<string>()
  let firstFail: number | null = null
  const rows = steps.map((s) => {
    const newFails = Object.entries(s.checks || {})
      .filter(([k, v]) => v === false && !seen.has(k))
      .map(([k]) => k)
    newFails.forEach((k) => seen.add(k))
    if (newFails.length && firstFail == null) firstFail = s.step
    return { s, newFails }
  })
  const finalFails = Object.entries(run.final_checks || {})
    .filter(([, v]) => v === false)
    .map(([k]) => k)
  return (
    <>
      <div className={'verdict ' + (finalFails.length ? 'bad' : 'good')}>
        <Spr name={finalFails.length ? 'skull' : 'hero_cheer'} scale={5} />
        <div>
          <h1>{finalFails.length ? `THE BUILD: ${finalFails.length} CHECK${finalFails.length === 1 ? '' : 'S'} FAILED` : 'THE BUILD: ALL CHECKS PASS'}</h1>
          <div className="mono">
            disk {run.disk_id ?? 'unknown'} · model {run.model ?? 'unknown'} · builder {run.builder ?? 'unknown'}
          </div>
        </div>
      </div>
      <dl>
        <dt>First failure</dt>
        <dd>{firstFail != null ? `step ${firstFail}` : 'none during the build'}</dd>
        <dt>Steps</dt>
        <dd>
          <table>
            <thead>
              <tr>
                <th>step</th>
                <th>build</th>
                <th>checkpoint</th>
                <th>model calls</th>
                <th>checks that first failed here</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ s, newFails }) => (
                <tr key={s.step}>
                  <td>{s.step}</td>
                  <td>{show(s.wall_s, ' s')}</td>
                  <td>{show(s.checkpoint_ms, ' ms')}</td>
                  <td>{show(s.model_calls)}</td>
                  <td className={newFails.length ? 'no' : ''}>{newFails.join(', ') || '·'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </dd>
        <dt>Final checks</dt>
        <dd>
          <Checks checks={run.final_checks} />
        </dd>
      </dl>
    </>
  )
}

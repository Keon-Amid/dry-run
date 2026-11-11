import { useEffect, useState } from 'react'
import { frac, show, type RunData } from './data'
import { Spr } from './Spr'

export function Slots({ score, fails }: { score: any; fails?: boolean }) {
  const f = frac(score)
  if (!f) return <em>{score == null ? 'unknown' : String(score)}</em>
  return (
    <span className="slots">
      {Array.from({ length: f.b }, (_, i) => (
        <i key={i} className={'slot ' + ((i < f.a) !== !!fails ? 'g' : 'r')} />
      ))}
      <em>{String(score)}</em>
    </span>
  )
}

export function headline(c: any): string {
  const q = c.culprit
  if (c.verdict === 'real_problem')
    return q ? (q.kind === 'rule_off' ? 'KILLED BY: A HARNESS RULE' : q.kind === 'spec_line' ? `KILLED BY: SPEC STEP ${q.step ?? '?'}` : `KILLED BY: ${q.route}`) : 'A REAL PROBLEM'
  if (c.verdict === 'test_wrong') return 'FALSE ALARM: YOUR TEST WAS WRONG'
  if (c.verdict === 'model_slip') return 'THE MODEL SLIPPED'
  if (c.verdict === 'inconclusive') return 'INCONCLUSIVE'
  return 'VERDICT PENDING'
}

type DiffRow = { l: string | null; r: string | null; kind: 'same' | 'chg' | 'del' | 'add' }
function diffLines(a: string[], b: string[]): DiffRow[] {
  const n = a.length
  const m = b.length
  const L = Array.from({ length: n + 1 }, () => new Int32Array(m + 1))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const rows: DiffRow[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) rows.push({ l: a[i++], r: b[j++], kind: 'same' })
    else if (L[i + 1][j] >= L[i][j + 1]) rows.push({ l: a[i++], r: null, kind: 'del' })
    else rows.push({ l: null, r: b[j++], kind: 'add' })
  }
  while (i < n) rows.push({ l: a[i++], r: null, kind: 'del' })
  while (j < m) rows.push({ l: null, r: b[j++], kind: 'add' })
  const out: DiffRow[] = []
  for (let k = 0; k < rows.length; k++) {
    const r = rows[k]
    const nx = rows[k + 1]
    if (r.kind === 'del' && nx?.kind === 'add') {
      out.push({ l: r.l, r: nx.r, kind: 'chg' })
      k++
    } else out.push(r)
  }
  return out
}

// The spec, before and after the fix, side by side (spec.original.md / spec.fixed.md in the run folder).
function SpecDiff({ data }: { data: RunData }) {
  const rows = diffLines((data.specOriginal ?? '').split(/\r?\n/), (data.specFixed ?? '').split(/\r?\n/))
  const changed = rows.filter((r) => r.kind !== 'same').length
  const first = rows.findIndex((r) => r.kind !== 'same')
  return (
    <div className="scroll diff" onClick={(e) => e.stopPropagation()}>
      <h2>THE SPEC, BEFORE AND AFTER</h2>
      <div className="check">
        {changed === 0 ? 'The two files are identical.' : `${changed} line${changed === 1 ? '' : 's'} changed.`}
      </div>
      <div className="difftable">
        <div className="diffhead">
          <span>ORIGINAL SPEC</span>
          <span>FIXED SPEC</span>
        </div>
        {rows.map((r, i) => (
          <div key={i} className={'diffrow ' + r.kind} ref={i === first ? (el) => el?.scrollIntoView({ block: 'center' }) : undefined}>
            <span className="l">{r.l ?? ''}</span>
            <span className="r">{r.r ?? ''}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// The final screen: before / after / baseline pass rates, straight from report.json.
function ResultPanel({ data }: { data: RunData }) {
  const rep = data.report || {}
  const checks = Object.entries(rep.checks ?? {}) as [string, any][]
  const wins: any[] = rep.winning_rewrites ?? []
  const tot = rep.archil_totals
  const sp = rep.spent?.total
  return (
    <div className="scroll result" onClick={(e) => e.stopPropagation()}>
      <h2>BEFORE AND AFTER</h2>
      {checks.map(([name, v]) => {
        const win = wins.find((w) => w.check === name)
        const held: string[] = v.heldout_checks ?? []
        return (
          <div key={name} className="resblock">
            <div className="check">
              check: {name}
              {held.length ? ` · held-out: ${held.join(', ')}` : ''}
            </div>
            <table className="arms">
              <thead>
                <tr>
                  <th></th>
                  <th>what was built</th>
                  <th>visible check</th>
                  <th>held-out</th>
                  <th>cost</th>
                </tr>
              </thead>
              <tbody>
                {(v.arms ?? []).map((a: any, i: number) => {
                  const kind = String(a.arm).startsWith('before') ? 'before' : String(a.arm).startsWith('after') ? 'after' : 'baseline'
                  return (
                    <tr key={i} className={'arm-' + kind}>
                      <td>
                        <span className="chip">{kind.toUpperCase()}</span>
                      </td>
                      <td>{String(a.label ?? a.arm).replace(/^(Before|After|Baseline):\s*/i, '')}</td>
                      <td>
                        <Slots score={a.visible} />
                      </td>
                      <td>
                        <Slots score={a.heldout} />
                      </td>
                      <td className="cost">{a.cost == null || /None/.test(String(a.cost)) ? 'unknown' : String(a.cost)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {win && (
              <div className="win">
                ★ WINNING FIX: {win.text}
                <small>
                  visible {win.visible ?? 'unknown'} · held-out {win.heldout ?? 'unknown'} · confirm build{' '}
                  {win.confirm_passed === true ? 'passed' : win.confirm_passed === false ? 'failed' : 'unknown'}
                </small>
              </div>
            )}
          </div>
        )
      })}
      {Array.isArray(data.before_after?.columns) && data.before_after.columns.length > 0 && (
        <div className="resblock">
          <div className="check">the same calls on each build (before_after.json)</div>
          <table className="arms probes">
            <thead>
              <tr>
                <th>call</th>
                {data.before_after.columns.map((c: any, i: number) => (
                  <th key={i}>{String(c.name ?? '')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.keys(data.before_after.columns[0].results ?? {}).map((k) => {
                const vals = data.before_after.columns.map((c: any) => String(c.results?.[k] ?? 'unknown'))
                const differs = vals.some((v: string) => v !== vals[0])
                return (
                  <tr key={k} className={differs ? 'differs' : ''}>
                    <td>{k}</td>
                    {vals.map((v: string, i: number) => (
                      <td key={i} className={differs && i > 0 && v !== vals[0] ? 'chg' : ''}>
                        {v}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="row">
        <span>spent on the whole run</span>
        <em>{sp ? `${show(sp.model_calls)} model calls · ${typeof sp.usd === 'number' ? '$' + (sp.usd < 1 ? sp.usd.toFixed(4) : sp.usd.toFixed(2)) : 'cost unknown'}` : 'unknown'}</em>
      </div>
      <div className="row">
        <span>replay avoided by branching</span>
        <em>{tot ? `${show(tot.steps)} steps · ${show(tot.minutes, ' min')} · ${show(tot.copies)} copies` : 'unknown'}</em>
      </div>
    </div>
  )
}

// One card per failing check. Every line is read from triage.json and swarm.json.
export function Cards({ data, onClose }: { data: RunData; onClose: () => void }) {
  const checks: any[] = data.triage?.checks ?? []
  const swarms: any[] = data.swarm?.swarms ?? []
  const hasResult = Object.keys(data.report?.checks ?? {}).length > 0
  const hasDiff = typeof data.specOriginal === 'string' && typeof data.specFixed === 'string'
  const asked = new URLSearchParams(location.search).get('view')
  const [view, setView] = useState<'result' | 'cards' | 'diff'>(asked === 'diff' && hasDiff ? 'diff' : hasResult ? 'result' : 'cards')
  useEffect(() => {
    if (hasResult) setView((v) => (v === 'diff' ? v : 'result'))
  }, [hasResult])
  const ruleText = (name: string): string | null => {
    const rc = (data.report?.culprits ?? []).find((x: any) => x.check === name)
    return typeof rc?.rule_text === 'string' ? rc.rule_text : null
  }
  const why = (name: string) => {
    const m = data.run?.final_messages?.[name]
    return typeof m === 'string' && m ? (m.length > 220 ? m.slice(0, 220) + '…' : m) : null
  }
  return (
    <div className="cards" onClick={onClose}>
      {(hasResult || hasDiff) && (
        <div className="tabs" onClick={(e) => e.stopPropagation()}>
          {hasResult && (
            <button className={'btn' + (view === 'result' ? ' on' : '')} onClick={() => setView('result')}>
              BEFORE / AFTER
            </button>
          )}
          {hasDiff && (
            <button className={'btn' + (view === 'diff' ? ' on' : '')} onClick={() => setView('diff')}>
              SPEC DIFF
            </button>
          )}
          <button className={'btn' + (view === 'cards' ? ' on' : '')} onClick={() => setView('cards')}>
            DEATH CARDS
          </button>
        </div>
      )}
      {hasDiff && view === 'diff' ? (
        <SpecDiff data={data} />
      ) : hasResult && view === 'result' ? (
        <ResultPanel data={data} />
      ) : (
      <div className="cardrow" onClick={(e) => e.stopPropagation()}>
        {checks.map((c) => {
          const sm = swarms.find((s) => s.check === c.check)
          const wins: any[] = (sm?.rewrites ?? []).filter((r: any) => r.winner)
          const q = c.culprit
          const base = (data.baseline?.baselines ?? []).find((b: any) => b.check === c.check)
          return (
            <div key={c.check} className={'scroll v-' + (c.verdict ?? 'pending')}>
              <div className="emblem">
                <Spr name={c.verdict === 'test_wrong' ? 'scales' : 'skull'} scale={3} />
              </div>
              <h2>{headline(c)}</h2>
              <div className="check">check: {c.check}</div>
              {q && (
                <div className="culprit">
                  {q.kind === 'rule_off' ? (
                    <>
                      harness rule <b>{q.rule ?? 'unknown'}</b>
                      {ruleText(c.check) && (
                        <>
                          <br />
                          <s>{ruleText(c.check)}</s>
                          <br />→ <b>switch the rule off</b>
                        </>
                      )}
                    </>
                  ) : (
                    <>
                      <s>{q.old ?? ''}</s>
                      <br />→ <b>{q.new ?? ''}</b>
                    </>
                  )}
                </div>
              )}
              <p className="cardtext">{c.card ?? ''}</p>
              {why(c.check) && <p className="why">why it failed: {why(c.check)}</p>}
              {c.rebuild && (
                <div className="row">
                  <span>rebuild fails</span>
                  <Slots score={c.rebuild.fails} fails />
                </div>
              )}
              {c.suspects && (
                <>
                  <div className="row">
                    <span>with the change</span>
                    <Slots score={q?.score} />
                  </div>
                  <div className="row">
                    <span>control</span>
                    <Slots score={c.suspects.control} />
                  </div>
                </>
              )}
              {sm && (
                <div className="row">
                  <span>swarm</span>
                  <em>
                    {sm.n_branches ?? '?'} branches · {sm.n_rewrites ?? '?'} rewrites · {wins.length} pass held-out
                  </em>
                </div>
              )}
              {wins.map((w) => (
                <div key={w.route} className="win">
                  ★ {w.text}
                  <small>
                    visible {w.visible ?? 'unknown'} · held-out {w.heldout ?? 'unknown'}
                  </small>
                </div>
              ))}
              {base && (
                <div className="baseline">
                  <div className="row">
                    <span>one plain Claude call instead</span>
                    <em>{base.passes_all === true ? 'passes all' : base.passes_all === false ? 'does not pass all' : 'unknown'}</em>
                  </div>
                  <div className="row">
                    <span>· visible</span>
                    <Slots score={base.visible} />
                  </div>
                  <div className="row">
                    <span>· held-out</span>
                    <Slots score={base.heldout} />
                  </div>
                </div>
              )}
              {c.confirm && (
                <div className="row">
                  <span>confirm</span>
                  <em>{c.confirm.text ?? (c.confirm.passed === true ? 'passed' : c.confirm.passed === false ? 'failed' : 'unknown')}</em>
                </div>
              )}
            </div>
          )
        })}
      </div>
      )}
      <button className="btn closebtn" onClick={onClose}>
        CLOSE
      </button>
    </div>
  )
}

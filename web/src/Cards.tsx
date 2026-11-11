import { useState } from 'react'
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
  const [view, setView] = useState<'result' | 'cards'>(hasResult ? 'result' : 'cards')
  const why = (name: string) => {
    const m = data.run?.final_messages?.[name]
    return typeof m === 'string' && m ? (m.length > 220 ? m.slice(0, 220) + '…' : m) : null
  }
  return (
    <div className="cards" onClick={onClose}>
      {hasResult && (
        <div className="tabs" onClick={(e) => e.stopPropagation()}>
          <button className={'btn' + (view === 'result' ? ' on' : '')} onClick={() => setView('result')}>
            BEFORE / AFTER
          </button>
          <button className={'btn' + (view === 'cards' ? ' on' : '')} onClick={() => setView('cards')}>
            DEATH CARDS
          </button>
        </div>
      )}
      {hasResult && view === 'result' ? (
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
                      rule <b>{q.rule ?? 'unknown'}</b>
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

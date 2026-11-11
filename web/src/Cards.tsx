import { frac, type RunData } from './data'
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

// One card per failing check. Every line is read from triage.json and swarm.json.
export function Cards({ data, onClose }: { data: RunData; onClose: () => void }) {
  const checks: any[] = data.triage?.checks ?? []
  const swarms: any[] = data.swarm?.swarms ?? []
  return (
    <div className="cards" onClick={onClose}>
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
      <button className="btn closebtn" onClick={onClose}>
        CLOSE
      </button>
    </div>
  )
}

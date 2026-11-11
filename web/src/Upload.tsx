import { useState } from 'react'

type Picked = { path: string; size: number }

// The front door of the product: hand over a spec bundle. Starting the pipeline from here is NOT wired yet.
export function Upload({ onClose }: { onClose: () => void }) {
  const [files, setFiles] = useState<Picked[]>([])
  const [steps, setSteps] = useState<number | null>(null)
  const pick = async (list: FileList | null) => {
    if (!list) return
    const arr = Array.from(list)
    setFiles(arr.map((f) => ({ path: (f as any).webkitRelativePath || f.name, size: f.size })))
    const spec = arr.find((f) => /(^|\/)spec\.md$/i.test((f as any).webkitRelativePath || f.name))
    if (spec) {
      const txt = await spec.text()
      setSteps((txt.match(/^##\s*Step\s+\d+/gim) || []).length)
    } else setSteps(null)
  }
  const has = (re: RegExp) => files.some((f) => re.test(f.path))
  const parts: [string, string, boolean][] = [
    ['spec.md', 'the steps, one "## Step k" heading each', has(/(^|\/)spec\.md$/i)],
    ['rules/', 'the harness rules the agent rereads every turn', has(/(^|\/)rules\//i)],
    ['checks/', 'deterministic checks for "done"', has(/(^|\/)checks\//i)],
    ['checks_heldout/', 'checks the fix swarm never sees', has(/(^|\/)checks_heldout\//i)],
    ['golden/', 'a reference build, to catch wrong tests', has(/(^|\/)golden\//i)],
  ]
  return (
    <div className="cards" onClick={onClose}>
      <div className="scroll upload" onClick={(e) => e.stopPropagation()}>
        <h2>NEW RUN: UPLOAD A SPEC BUNDLE</h2>
        <p className="cardtext">Banzai builds your spec one step at a time on an Archil disk, with a checkpoint per step, and this page follows the run as it happens.</p>
        <label className="drop">
          <input type="file" multiple {...({ webkitdirectory: '', directory: '' } as any)} onChange={(e) => pick(e.target.files)} />
          <span>{files.length ? `${files.length} files chosen` : 'Choose the bundle folder'}</span>
        </label>
        <ul className="checks">
          {parts.map(([name, what, ok]) => (
            <li key={name} className={files.length ? (ok ? 'ok' : 'no') : ''}>
              {files.length ? (ok ? '✓' : '✗') : '·'} <b>{name}</b> {what}
            </li>
          ))}
        </ul>
        {steps != null && <div className="row"><span>steps found in spec.md</span><em>{steps}</em></div>}
        <div className="stubnote">
          STUB: starting a run from this page is not wired yet. Today a run is started from a terminal, then shows up in the run picker and under LIVE:
          <code>python -m orchestrator.pipeline</code>
        </div>
        <div className="uploadbar">
          <button className="btn" disabled>START (NOT WIRED)</button>
          <button className="btn" onClick={onClose}>CLOSE</button>
        </div>
      </div>
    </div>
  )
}

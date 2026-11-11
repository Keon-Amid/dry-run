# Banzai page

The pixel-roguelike view of a run. It reads only the run files in `../orchestrator/runs/<stamp>/`
(`run.json`, `triage.json`, `results.json`, `swarm.json`, `archil.json`, plus `baseline.json` and `report.json` when
present); every number on screen comes from them. `report.json` and `before_after.json` feed the final BEFORE / AFTER screen;
`spec.original.md` / `spec.fixed.md` feed the SPEC DIFF tab.

```bash
cd web
npm install
npm run dev        # http://localhost:5173 (also served on your LAN address)
```

- **Run picker:** newest first, with friendly labels (`run.json` `label`, else fixture + who built it). The page opens
  on the newest real run that has triage results.
- **NEW RUN:** starts `python -m orchestrator.pipeline` on the machine serving the page and follows it live. Options
  this machine can't run are greyed out with the reason (the real builder needs `ANTHROPIC_API_KEY`; Archil needs
  `ARCHIL_API_KEY` and `pip install archil`). Runs can only be started from localhost.
- **LIVE:** follows the newest run folder and re-reads its files every 2 s.
- **Keys:** space play/pause, R restart, 1 / 2 / 3 = 1x / 4x / 16x, L live, C cards, N new run (upload stub), arrows scrub.
- **Click a character** for its report. The QR code points at the address you opened the page from, so open the
  page on the LAN address if phones should reach it.
- `DRYRUN_RUNS_DIR=/some/folder npm run dev` reads runs from another folder.
- Sprites: `tools/cut_sprites.py` cuts `public/sprites/atlas.png` from the Gemini sheets.

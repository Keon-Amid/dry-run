# Banzai page

The pixel-roguelike view of a run. It reads only the run files in `../orchestrator/runs/<stamp>/`
(`run.json`, `triage.json`, `results.json`, `swarm.json`, `archil.json`, plus `baseline.json` and `report.json` when
present); every number on screen comes from them. `report.json` feeds the final BEFORE / AFTER screen.

```bash
cd web
npm install
npm run dev        # http://localhost:5173 (also served on your LAN address)
```

- **Run picker:** newest first. The page opens on the newest run that has triage results.
- **LIVE:** follows the newest run folder and re-reads its files every 2 s.
- **Keys:** space play/pause, R restart, 1 / 2 / 3 = 1x / 4x / 16x, L live, C cards, arrows scrub.
- **Click a character** for its report. The QR code points at the address you opened the page from, so open the
  page on the LAN address if phones should reach it.
- `DRYRUN_RUNS_DIR=/some/folder npm run dev` reads runs from another folder.
- Sprites: `tools/cut_sprites.py` cuts `public/sprites/atlas.png` from the Gemini sheets.

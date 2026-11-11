// The dungeon. One canvas, a 640x360 logical grid scaled by an integer factor, sprites cut from the Gemini art.
import { W, H, FY, GATE_X, actorAt, type Timeline, type Actor, type LaneSet } from './timeline'
import { frac } from './data'

export const PAL = {
  shadow: '#07060C',
  bg: '#12101C',
  stoneD: '#2B2738',
  stoneL: '#4A4458',
  parch: '#E8D8B0',
  bone: '#F1EAD8',
  ember: '#F2994A',
  fire: '#F6D55C',
  green: '#6FCF62',
  red: '#D6455D',
  cyan: '#5FD3E8',
  gold: '#E2B84B',
}
type Frame = { x: number; y: number; w: number; h: number }
type SpriteOpt = { alpha?: number; tint?: string; tintA?: number }
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

export class Scene {
  canvas: HTMLCanvasElement
  ctx: CanvasRenderingContext2D
  S = 2
  tl: Timeline | null = null
  atlas: HTMLImageElement | null = null
  frames: Record<string, Frame> = {}
  tintCache = new Map<string, HTMLCanvasElement>()
  fitCache = new Map<string, string>()
  wall: HTMLCanvasElement
  hoverId: string | null = null
  lastVis: [Actor, { x: number; y: number; pose: string; u: number }][] = []
  private retry: any = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    this.ctx = canvas.getContext('2d')!
    this.wall = this.makeWall()
    this.loadAtlas()
    this.retry = setInterval(() => (this.atlas ? clearInterval(this.retry) : this.loadAtlas()), 4000)
  }
  dispose() {
    clearInterval(this.retry)
  }

  async loadAtlas() {
    try {
      const j = await (await fetch('/sprites/atlas.json', { cache: 'no-store' })).json()
      const img = new Image()
      img.src = '/sprites/atlas.png'
      await img.decode()
      this.frames = j.frames || {}
      this.atlas = img
      this.tintCache.clear()
    } catch {
      /* fall back to drawn shapes until the atlas exists */
    }
  }

  resize(cssW: number, cssH: number) {
    const dpr = window.devicePixelRatio || 1
    const S = Math.max(1, Math.floor(Math.min((cssW * dpr) / W, (cssH * dpr) / H)))
    if (S === this.S && this.canvas.width === W * S) return
    this.S = S
    this.canvas.width = W * S
    this.canvas.height = H * S
    this.canvas.style.width = (W * S) / dpr + 'px'
    this.canvas.style.height = (H * S) / dpr + 'px'
    this.fitCache.clear()
  }

  private makeWall(): HTMLCanvasElement {
    const c = document.createElement('canvas')
    c.width = W
    c.height = 96
    const g = c.getContext('2d')!
    g.fillStyle = PAL.stoneD
    g.fillRect(0, 0, W, 96)
    let seed = 11
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647
    for (let row = 0; row < 12; row++) {
      const y = row * 8
      g.fillStyle = PAL.bg
      g.fillRect(0, y + 7, W, 1)
      for (let x = (row % 2) * 8; x < W; x += 16) {
        g.fillStyle = PAL.bg
        g.fillRect(x, y, 1, 7)
        const r = rnd()
        if (r < 0.1) {
          g.globalAlpha = 0.3
          g.fillStyle = PAL.stoneL
          g.fillRect(x + 1, y, 15, 1)
        } else if (r < 0.2) {
          g.globalAlpha = 0.45
          g.fillStyle = PAL.bg
          g.fillRect(x + 1, y, 15, 7)
        }
        g.globalAlpha = 1
      }
    }
    return c
  }

  // ---- drawing helpers ----
  text(str: string, x: number, y: number, size: number, color: string, align: CanvasTextAlign = 'left', maxW?: number, font = 'VT323'): number {
    const { ctx, S } = this
    ctx.save()
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.font = `${Math.round(size * S)}px "${font}", monospace`
    ctx.fillStyle = color
    ctx.textAlign = align
    ctx.textBaseline = 'top'
    let s = str
    if (maxW != null) {
      const key = size + '|' + maxW + '|' + font + '|' + str
      const hit = this.fitCache.get(key)
      if (hit != null) s = hit
      else {
        const mw = maxW * S
        if (ctx.measureText(s).width > mw) {
          while (s.length > 1 && ctx.measureText(s + '…').width > mw) s = s.slice(0, -1)
          s += '…'
        }
        this.fitCache.set(key, s)
      }
    }
    ctx.fillText(s, Math.round(x * S), Math.round(y * S))
    const w = ctx.measureText(s).width / S
    ctx.restore()
    return w
  }

  private tinted(name: string, color: string, a: number): HTMLCanvasElement | null {
    const f = this.frames[name]
    if (!f || !this.atlas) return null
    const key = name + '|' + color + '|' + a
    let c = this.tintCache.get(key)
    if (!c) {
      c = document.createElement('canvas')
      c.width = f.w
      c.height = f.h
      const g = c.getContext('2d')!
      g.imageSmoothingEnabled = false
      g.drawImage(this.atlas, f.x, f.y, f.w, f.h, 0, 0, f.w, f.h)
      g.globalCompositeOperation = 'source-atop'
      g.globalAlpha = a
      g.fillStyle = color
      g.fillRect(0, 0, f.w, f.h)
      this.tintCache.set(key, c)
    }
    return c
  }

  sprite(name: string, x: number, feetY: number, o: SpriteOpt = {}) {
    const ctx = this.ctx
    const f = this.frames[name]
    if (o.alpha != null) ctx.globalAlpha = o.alpha
    if (!f || !this.atlas) this.fallback(name, x, feetY, o)
    else {
      const dx = Math.round(x - f.w / 2)
      const dy = Math.round(feetY - f.h)
      const c = o.tint ? this.tinted(name, o.tint, o.tintA ?? 0.5) : null
      if (c) ctx.drawImage(c, dx, dy)
      else ctx.drawImage(this.atlas, f.x, f.y, f.w, f.h, dx, dy, f.w, f.h)
    }
    ctx.globalAlpha = 1
  }

  private fallback(name: string, x: number, y: number, o: SpriteOpt) {
    const ctx = this.ctx
    const r = (c: string, dx: number, dy: number, w: number, h: number) => {
      ctx.fillStyle = c
      ctx.fillRect(Math.round(x + dx), Math.round(y + dy), w, h)
    }
    if (name === 'hero_dead') {
      r(o.tint ?? PAL.stoneD, -13, -7, 22, 7)
      r(PAL.parch, 8, -6, 4, 4)
    } else if (name.startsWith('hero')) {
      r(o.tint ?? PAL.stoneD, -6, -22, 12, 20)
      r(PAL.shadow, -6, -22, 12, 2)
      r(PAL.parch, 0, -18, 5, 4)
      r(PAL.shadow, -5, -2, 4, 2)
      r(PAL.shadow, 1, -2, 4, 2)
    } else if (name === 'fire_unlit') r(PAL.stoneD, -8, -4, 16, 4)
    else if (name.startsWith('fire')) {
      r(PAL.stoneD, -8, -4, 16, 4)
      r(PAL.ember, -5, -12, 10, 9)
      r(PAL.fire, -2, -9, 5, 6)
      if (name === 'fire_aura') {
        r(PAL.cyan, -12, -16, 24, 1)
        r(PAL.cyan, -12, -1, 24, 1)
      }
    } else if (name === 'skull') {
      r(PAL.bone, -4, -9, 9, 7)
      r(PAL.bone, -2, -2, 5, 2)
      r(PAL.shadow, -2, -6, 2, 2)
      r(PAL.shadow, 2, -6, 2, 2)
    } else if (name === 'flag') {
      r(PAL.gold, -6, -22, 1, 22)
      r(PAL.gold, -5, -22, 12, 8)
    } else if (name.startsWith('chest')) {
      r(PAL.stoneD, -7, -10, 14, 10)
      r(PAL.gold, -7, -6, 14, 2)
    } else if (name === 'gate') {
      r(PAL.stoneL, -16, -40, 32, 40)
      r(PAL.shadow, -11, -32, 22, 32)
      r(PAL.gold, -11, -33, 22, 1)
    } else if (name.startsWith('portal')) {
      r(PAL.cyan, -10, -14, 20, 3)
      r(PAL.cyan, -10, -4, 20, 3)
    } else r(PAL.gold, -5, -10, 10, 10)
  }

  // ---- frame ----
  render(t: number, clock: number) {
    const { ctx, S } = this
    const tl = this.tl
    ctx.setTransform(S, 0, 0, S, 0, 0)
    ctx.imageSmoothingEnabled = false
    ctx.globalAlpha = 1
    ctx.fillStyle = PAL.shadow
    ctx.fillRect(0, 0, W, H)
    if (!tl) {
      this.text('LOADING RUN…', W / 2, H / 2 - 6, 12, PAL.parch, 'center')
      this.lastVis = []
      return
    }
    this.drawCorridor(tl, t, clock)
    const set = tl.laneSets.find((s) => t >= s.t0 && t < s.t1)
    if (set) this.drawLanes(set, t, clock)
    else this.drawEmptyLanes(tl, t)
    const vis: Scene['lastVis'] = []
    for (const a of tl.actors) {
      const p = actorAt(a, t)
      if (p) vis.push([a, p])
    }
    vis.sort((A, B) => A[1].y - B[1].y)
    for (const [a, p] of vis) this.drawActor(a, p, t, clock)
    this.lastVis = vis
  }

  private drawCorridor(tl: Timeline, t: number, clock: number) {
    const ctx = this.ctx
    ctx.fillStyle = PAL.bg
    ctx.fillRect(8, 12, 624, 96)
    ctx.drawImage(this.wall, 0, 0, 620, 58, 10, 14, 620, 58)
    ctx.fillStyle = PAL.stoneL
    ctx.fillRect(10, 72, 620, 32)
    ctx.fillStyle = PAL.stoneD
    for (let x = 22; x < 630; x += 24) ctx.fillRect(x, 72, 1, 32)
    ctx.fillRect(10, 72, 620, 1)
    ctx.fillRect(10, 88, 620, 1)
    // entrance
    ctx.fillStyle = PAL.shadow
    ctx.fillRect(12, 54, 18, 46)
    ctx.fillStyle = PAL.stoneL
    ctx.fillRect(11, 52, 20, 2)
    // gate at the far end
    this.sprite('gate', GATE_X + 8, 102)
    if (tl.gateOpenT != null && t >= tl.gateOpenT) {
      ctx.globalAlpha = 0.28 + 0.14 * Math.sin(clock * 6)
      ctx.fillStyle = PAL.gold
      ctx.fillRect(GATE_X - 4, 70, 24, 32)
      ctx.globalAlpha = 1
    }

    for (const f of tl.fires) {
      const lit = t >= f.litT
      const gold = t >= f.goldT
      const fork = tl.tags.some((g) => g.kind === 'fork' && g.step === f.step && t >= g.t0 && t < g.t1)
      const origin = tl.tags.some((g) => g.kind === 'origin' && g.step === f.step && t >= g.t0 && t < g.t1)
      const x = Math.round(f.x)
      // plaque
      const pw = 56
      ctx.fillStyle = PAL.shadow
      ctx.fillRect(x - pw / 2 - 1, 16, pw + 2, 20)
      ctx.fillStyle = fork ? PAL.cyan : origin ? PAL.ember : lit ? PAL.parch : PAL.stoneL
      ctx.fillRect(x - pw / 2, 17, pw, 18)
      const ink = lit || fork || origin ? PAL.shadow : PAL.stoneD
      this.text(`STEP ${f.step}`, x, 17, 9, ink, 'center')
      const line2 = fork ? 'FORK POINT' : origin ? 'ORIGIN' : lit ? (f.ckptMs != null ? `ckpt ${Math.round(f.ckptMs)} ms` : 'ckpt unknown') : '· · ·'
      this.text(line2, x, 25.5, 8, ink, 'center')
      if (lit) {
        ctx.globalAlpha = 0.16
        ctx.fillStyle = gold ? PAL.gold : PAL.ember
        ctx.fillRect(x - 26, 93, 52, 8)
        ctx.fillRect(x - 17, 91, 34, 12)
        ctx.globalAlpha = 1
      }
      const fr = Math.floor(clock * 7 + f.step * 1.7) % 3
      this.sprite(!lit ? 'fire_unlit' : fork ? 'fire_aura' : ['fire1', 'fire2', 'fire3'][fr], x, fork ? 100 : 97)
      if (origin && !fork) {
        // corner brackets: "it started here"
        ctx.fillStyle = PAL.ember
        ctx.globalAlpha = 0.6 + 0.4 * Math.sin(clock * 8)
        for (const [bx, by] of [[x - 15, 74], [x + 13, 74], [x - 15, 98], [x + 13, 98]] as const) ctx.fillRect(bx, by, 3, 1)
        for (const [bx, by] of [[x - 15, 74], [x + 15, 74], [x - 15, 96], [x + 15, 96]] as const) ctx.fillRect(bx, by, 1, 3)
        ctx.globalAlpha = 1
      }
    }

    // footprints: from where it surfaced back to where it started
    for (const fp of tl.footprints) {
      if (t < fp.t0 || t >= fp.tEnd) continue
      const u = clamp((t - fp.t0) / Math.max(0.01, fp.t1 - fp.t0), 0, 1)
      const dir = fp.toX < fp.fromX ? -1 : 1
      const count = Math.floor(Math.abs(fp.toX - fp.fromX) / 7)
      ctx.fillStyle = PAL.cyan
      for (let i = 0; i <= Math.floor(count * u); i++) {
        const fx = Math.round(fp.fromX + dir * i * 7) - 4
        ctx.fillRect(fx, 101 + (i % 2 ? 2 : 0), 3, 1)
        ctx.fillRect(fx + (dir < 0 ? 0 : 1), 100 + (i % 2 ? 2 : 0), 2, 1)
      }
    }

    // failed checks, dropped where they surfaced; restyled when triage rules on them
    for (const m of tl.markers) {
      if (t < m.t) continue
      let st = m.states[0]
      for (const s of m.states) if (s.t <= t) st = s
      const same = tl.markers.filter((k) => k.step === m.step && t >= k.t).length
      const x = Math.round(tl.stepX(m.step))
      const ix = x + Math.round((m.slot - (same - 1) / 2) * 18)
      const drop = t - m.t < 0.3 ? -Math.round((1 - (t - m.t) / 0.3) * 12) : 0
      if (st.kind === 'test_wrong') this.sprite('scales', ix, 55)
      else this.sprite('skull', ix, 52 + drop, st.kind === 'model_slip' || st.kind === 'inconclusive' ? { tint: PAL.stoneL, tintA: 0.75 } : {})
      const nameCol = st.kind === 'test_wrong' || st.kind === 'model_slip' ? PAL.stoneL : st.kind === 'culprit' ? PAL.gold : PAL.red
      const ny = 53 + m.slot * 15
      this.text(m.check, x, ny, 8, nameCol === PAL.stoneL ? PAL.parch : nameCol, 'center', 76)
      const verdict =
        st.kind === 'test_wrong' ? 'TEST WRONG' : st.kind === 'model_slip' ? 'MODEL SLIP' : st.kind === 'real_problem' ? 'REAL PROBLEM' : st.kind === 'culprit' ? 'CAUSE FOUND' : st.kind === 'inconclusive' ? 'INCONCLUSIVE' : ''
      if (verdict)
        this.text(verdict, x, ny + 7, 8, st.kind === 'test_wrong' ? PAL.bone : st.kind === 'model_slip' ? PAL.fire : st.kind === 'culprit' ? PAL.gold : PAL.red, 'center')
      if (tl.focus.some((f) => f.check === m.check && t >= f.t0 && t < f.t1)) {
        ctx.globalAlpha = 0.5 + 0.5 * Math.sin(clock * 12)
        ctx.fillStyle = PAL.bone
        ctx.fillRect(x - 39, 38, 78, 1)
        ctx.fillRect(x - 39, 69, 78, 1)
        ctx.fillRect(x - 39, 38, 1, 32)
        ctx.fillRect(x + 38, 38, 1, 32)
        ctx.globalAlpha = 1
      }
    }
  }

  private drawEmptyLanes(tl: Timeline, t: number) {
    // nothing branched yet: a dark floor below the corridor
    const ctx = this.ctx
    ctx.fillStyle = PAL.bg
    ctx.fillRect(8, 112, 624, 242)
    ctx.globalAlpha = 0.5
    ctx.drawImage(this.wall, 0, 0, 620, 96, 10, 114, 620, 96)
    ctx.drawImage(this.wall, 0, 0, 620, 96, 10, 210, 620, 96)
    ctx.drawImage(this.wall, 0, 0, 620, 46, 10, 306, 620, 46)
    ctx.globalAlpha = 1
    ctx.fillStyle = PAL.shadow
    ctx.globalAlpha = 0.55
    ctx.fillRect(10, 114, 620, 238)
    ctx.globalAlpha = 1
    this.text('BRANCHES APPEAR HERE WHEN A CHECKPOINT IS FORKED', W / 2, 226, 9, PAL.stoneL, 'center')
  }

  private drawLanes(set: LaneSet, t: number, clock: number) {
    const ctx = this.ctx
    for (const l of set.lanes) {
      ctx.fillStyle = PAL.bg
      ctx.fillRect(8, l.y0 - 1, 624, l.h + 2)
      const wallH = l.h - 7
      ctx.drawImage(this.wall, 0, 8, 620, wallH, 10, l.y0, 620, wallH)
      ctx.fillStyle = PAL.shadow
      ctx.globalAlpha = 0.35
      ctx.fillRect(10, l.y0, 620, wallH)
      ctx.globalAlpha = 1
      ctx.fillStyle = PAL.stoneL
      ctx.fillRect(10, l.y0 + wallH, 620, 7)
      ctx.fillStyle = PAL.stoneD
      for (let x = 22; x < 630; x += 24) ctx.fillRect(x, l.y0 + wallH, 1, 7)
      // inscription strip
      ctx.fillStyle = PAL.shadow
      ctx.globalAlpha = 0.6
      ctx.fillRect(10, l.y0, 620, 10)
      ctx.globalAlpha = 1
      if (l.color) {
        ctx.fillStyle = l.color
        ctx.fillRect(10, l.y0, 3, l.h)
      }
      const lw = this.text(l.label, 16, l.y0 + 0.5, 9, l.color ?? PAL.bone)
      const done = t >= l.scoreT
      const right = l.sub ?? l.score
      const rightW = done ? right.length * 4 + 34 : 0
      this.text(l.text, 16 + lw + 6, l.y0 + 0.5, 9, PAL.parch, 'left', 600 - lw - rightW)
      if (l.gate) {
        // the held-out line: checks the swarm never saw
        ctx.fillStyle = PAL.gold
        ctx.globalAlpha = 0.7
        for (let y = l.y0 + 11; y < l.y0 + l.h; y += 4) ctx.fillRect(GATE_X - 68, y, 1, 2)
        ctx.globalAlpha = 1
      }
      if (done) {
        const col = l.tone === 'good' ? PAL.green : l.tone === 'bad' ? PAL.red : PAL.ember
        const fr = frac(l.score)
        let sx = 626
        if (fr && fr.b <= 6) {
          sx -= fr.b * 7
          for (let i = 0; i < fr.b; i++) {
            ctx.fillStyle = PAL.shadow
            ctx.fillRect(sx + i * 7, l.y0 + 2, 6, 6)
            ctx.fillStyle = i < fr.a ? PAL.green : PAL.red
            ctx.fillRect(sx + i * 7 + 1, l.y0 + 3, 4, 4)
          }
          sx -= 4
        }
        this.text(right, sx, l.y0 + 0.5, 9, col, 'right')
        if (l.flag) {
          this.sprite('chest_open', GATE_X - 2, l.feetY + 2)
          this.sprite('flag', GATE_X + 17, l.feetY + 2)
        }
      }
      if (l.glowT != null && t >= l.glowT) {
        ctx.globalAlpha = 0.55 + 0.45 * Math.sin(clock * 7)
        ctx.fillStyle = PAL.gold
        ctx.fillRect(9, l.y0 - 1, 622, 1)
        ctx.fillRect(9, l.y0 + l.h, 622, 1)
        ctx.fillRect(9, l.y0 - 1, 1, l.h + 2)
        ctx.fillRect(630, l.y0 - 1, 1, l.h + 2)
        ctx.globalAlpha = 1
      }
    }
    // the rift: one checkpoint, many branches
    const riftEnd = set.t0 + 1.5 + set.lanes.length * 0.14
    if (t < riftEnd + 0.8 && set.lanes.length) {
      const a = t < riftEnd ? 1 : Math.max(0, 1 - (t - riftEnd) / 0.8)
      const bx = Math.round(set.forkX)
      const last = set.lanes[set.lanes.length - 1]
      ctx.fillStyle = PAL.cyan
      ctx.globalAlpha = a * (0.5 + 0.3 * Math.sin(clock * 14))
      ctx.fillRect(bx - 1, FY + 6, 2, last.feetY - FY - 6)
      for (const l of set.lanes) ctx.fillRect(bx - 5, l.feetY, 10, 1)
      ctx.globalAlpha = a
      this.sprite(['portal1', 'portal2', 'portal3'][Math.floor(clock * 8) % 3], bx, FY + 13)
    }
  }

  private drawActor(a: Actor, p: { x: number; y: number; pose: string; u: number }, t: number, clock: number) {
    const ctx = this.ctx
    const x = Math.round(p.x)
    const y = Math.round(p.y)
    // route colour tints the cloak so copies read against the dark wall
    const base: SpriteOpt = a.banner ? { tint: a.banner, tintA: 0.42 } : { tint: PAL.parch, tintA: 0.22 }
    let lying = false
    switch (p.pose) {
      case 'walk':
        this.sprite(Math.floor(t * 7 + a.phase * 2) % 2 ? 'hero_walk1' : 'hero_walk2', x, y + 1, base)
        break
      case 'idle':
        this.sprite('hero_stand', x, y, base)
        break
      case 'fall':
        if (p.u < 0.45) this.sprite('hero_fall', x, y, { tint: PAL.red, tintA: 0.6 })
        else {
          lying = true
          this.sprite('hero_dead', x, y, { tint: PAL.red, tintA: 0.35 })
        }
        break
      case 'dead':
        lying = true
        this.sprite('hero_dead', x, y, a.banner ? { tint: a.banner, tintA: 0.25 } : {})
        break
      case 'cheer':
        this.sprite('hero_cheer', x, y - Math.round(Math.abs(Math.sin(clock * 9 + a.phase * 6)) * 3), base)
        break
      case 'spawn':
        this.sprite('hero_stand', x, y, { tint: PAL.cyan, tintA: 0.85, alpha: 0.35 + 0.65 * p.u })
        break
      case 'ghostwalk':
        this.sprite(Math.floor(t * 7) % 2 ? 'hero_walk1' : 'hero_walk2', x, y - 2 + Math.round(Math.sin(clock * 5)), { tint: PAL.cyan, tintA: 0.8, alpha: 0.6 })
        break
      case 'ghostidle':
        this.sprite('hero_stand', x, y - 2 + Math.round(Math.sin(clock * 5)), { tint: PAL.cyan, tintA: 0.8, alpha: 0.6 })
        break
      case 'invalid':
        this.sprite('hero_stand', x, y, { tint: PAL.stoneL, tintA: 0.85, alpha: 0.6 })
        break
    }
    if (a.banner && !lying && p.pose !== 'spawn') {
      ctx.fillStyle = PAL.bone
      ctx.fillRect(x + 8, y - 31, 1, 26)
      ctx.fillStyle = a.banner
      const wv = Math.floor(clock * 6 + a.phase * 5) % 2
      ctx.fillRect(x + 9, y - 31, 7, 5)
      ctx.fillRect(x + 9 + (wv ? 5 : 6), y - 30 + (wv ? 1 : 0), 2, 5)
    }
    const m = a.mark
    if (m && t >= m.t) {
      const my = lying ? y - 22 : y - 33
      if (m.kind === 'ok' && p.pose === 'cheer') {
        /* winners already have the flag and the chest */
      } else if (m.kind === 'ok') {
        ctx.fillStyle = PAL.shadow
        ctx.fillRect(x - 5, my - 1, 10, 8)
        ctx.fillStyle = PAL.green
        ctx.fillRect(x - 4, my + 2, 2, 2)
        ctx.fillRect(x - 2, my + 4, 2, 2)
        ctx.fillRect(x, my + 2, 2, 2)
        ctx.fillRect(x + 2, my, 2, 2)
      } else if (m.kind === 'invalid') {
        this.text('?', x, my - 2, 10, PAL.stoneL, 'center')
      } else {
        ctx.fillStyle = m.kind === 'held' ? PAL.gold : PAL.red
        ctx.fillRect(x - 4, my, 8, 5)
        ctx.fillRect(x - 3, my + 5, 6, 2)
        ctx.fillStyle = PAL.shadow
        ctx.fillRect(x - 3, my + 2, 2, 2)
        ctx.fillRect(x + 1, my + 2, 2, 2)
        ctx.fillRect(x - 1, my + 6, 1, 1)
      }
    }
    if (this.hoverId === a.id) {
      ctx.fillStyle = PAL.bone
      const w = lying ? 15 : 10
      const top = lying ? y - 14 : y - 27
      ctx.fillRect(x - w, top, 3, 1)
      ctx.fillRect(x - w, top, 1, 3)
      ctx.fillRect(x + w - 2, top, 3, 1)
      ctx.fillRect(x + w, top, 1, 3)
      ctx.fillRect(x - w, y + 1, 3, 1)
      ctx.fillRect(x - w, y - 1, 1, 3)
      ctx.fillRect(x + w - 2, y + 1, 3, 1)
      ctx.fillRect(x + w, y - 1, 1, 3)
    }
  }

  hit(lx: number, ly: number): Actor | null {
    for (let i = this.lastVis.length - 1; i >= 0; i--) {
      const [a, p] = this.lastVis[i]
      const lying = p.pose === 'dead' || (p.pose === 'fall' && p.u >= 0.45)
      const w = lying ? 15 : 10
      const top = lying ? p.y - 14 : p.y - 27
      if (lx >= p.x - w && lx <= p.x + w && ly >= top && ly <= p.y + 2) return a
    }
    return null
  }
}

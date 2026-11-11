import { asset } from './data'
import { useEffect, useRef, useState } from 'react'

// One sprite from the atlas, drawn at an integer scale with hard pixels.
let atlasP: Promise<{ frames: Record<string, { x: number; y: number; w: number; h: number }>; img: HTMLImageElement } | null> | null = null
function atlas() {
  atlasP =
    atlasP ||
    (async () => {
      try {
        const j = await (await fetch(asset('sprites/atlas.json'))).json()
        const img = new Image()
        img.src = asset('sprites/atlas.png')
        await img.decode()
        return { frames: j.frames || {}, img }
      } catch {
        return null
      }
    })()
  return atlasP
}

export function Spr({ name, scale = 3 }: { name: string; scale?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  useEffect(() => {
    let off = false
    atlas().then((a) => {
      const f = a?.frames[name]
      if (off || !a || !f) return
      setSize({ w: f.w, h: f.h })
      requestAnimationFrame(() => {
        const c = ref.current
        if (!c) return
        c.width = f.w
        c.height = f.h
        const g = c.getContext('2d')!
        g.imageSmoothingEnabled = false
        g.clearRect(0, 0, f.w, f.h)
        g.drawImage(a.img, f.x, f.y, f.w, f.h, 0, 0, f.w, f.h)
      })
    })
    return () => {
      off = true
    }
  }, [name])
  return <canvas ref={ref} className="spr" style={{ width: (size?.w ?? 8) * scale, height: (size?.h ?? 8) * scale }} />
}

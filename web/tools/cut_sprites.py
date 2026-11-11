# Cuts sprites out of the Gemini reference sheets into one palette-snapped atlas.
# Run: uv run --with pillow --with numpy --with scipy python web/tools/cut_sprites.py
import json, sys, numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

G = '/Users/keonamid/archil-playground/ui/gemini/'
OUT = '/Users/keonamid/dry-run/web/public/sprites/'
PAL_HEX = ['07060C', '12101C', '2B2738', '4A4458', 'E8D8B0', 'F1EAD8', 'F2994A', 'F6D55C', '6FCF62', 'D6455D', '5FD3E8', 'E2B84B']
PAL = np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)] for h in PAL_HEX], dtype=np.int32)
_cache = {}

def load(fn):
    if fn in _cache:
        return _cache[fn]
    im = np.asarray(Image.open(G + fn).convert('RGB')).astype(np.int32)
    R, Gc, B = im[..., 0], im[..., 1], im[..., 2]
    mag = (R > 140) & (B > 140) & (Gc < 120)
    near = ndi.binary_dilation(mag, iterations=4)
    fringe = near & (np.minimum(R, B) > Gc + 30) & (np.maximum(R, B) > 80)   # pink/purple JPEG halo next to the key colour
    op = ~(mag | fringe)
    op = ndi.binary_erosion(op, iterations=2)
    _cache[fn] = (im, op)
    return im, op

def snap(rgb, pal=None):
    P = PAL if pal is None else PAL[pal]
    d = ((rgb[..., None, :] - P[None, None, :, :]) ** 2).sum(-1)
    return P[d.argmin(-1)].astype(np.uint8)

def despeckle(a):
    lab, n = ndi.label(a, structure=np.ones((3, 3)))
    if n <= 1:
        return a
    sizes = ndi.sum(a, lab, range(1, n + 1))
    keep = np.zeros_like(a)
    for i, s in enumerate(sizes, 1):
        if s >= max(3, 0.02 * sizes.max()):
            keep |= lab == i
    return keep

def trim(rgb, a):
    ys, xs = np.nonzero(a)
    return rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1], a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

def cut(fn, rect, scale=None, height=None, mode='magenta', pal=None, thr=0.5):
    im, op = load(fn)
    x0, y0, x1, y1 = rect
    rgb = im[y0:y1, x0:x1].astype(np.uint8)
    a = op[y0:y1, x0:x1].copy()
    if mode == 'tile':
        a = ndi.binary_dilation(a, iterations=2) & ~((im[y0:y1, x0:x1, 0] > 140) & (im[y0:y1, x0:x1, 2] > 140) & (im[y0:y1, x0:x1, 1] < 120))
    rgb, a = trim(rgb, a)
    h, w = a.shape
    if scale is None:
        scale = h / height
    tw, th = max(1, round(w / scale)), max(1, round(h / scale))
    rgba = Image.fromarray(np.dstack([rgb, (a * 255).astype(np.uint8)]), 'RGBA').resize((tw, th), Image.BOX)
    arr = np.asarray(rgba).astype(np.int32)
    alpha = arr[..., 3] >= 255 * thr
    out = snap(arr[..., :3], pal)
    if mode == 'tile':   # make the dark surround transparent: flood the dark colours in from the border
        dark = (out == PAL[0].astype(np.uint8)).all(-1) | (out == PAL[1].astype(np.uint8)).all(-1)
        lab, n = ndi.label(dark)
        edge = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
        edge.discard(0)
        alpha &= ~np.isin(lab, list(edge))
    alpha = despeckle(alpha)
    out, alpha = trim(out, alpha)
    return np.dstack([out, (alpha * 255).astype(np.uint8)]), scale

C = '2-character-sprites.jpeg'; I = '4-map-icons.jpeg'; T = '5-tileset.jpeg'
HERO = 208 / 24
FIRE = 226 / 18
SPEC = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else None
HEROP = [0, 1, 2, 3, 4]
FIREP = [0, 1, 2, 3, 4, 5, 6, 7, 9, 11]
FRAMES = [
    ('hero_stand', C, (55, 32, 215, 260), dict(scale=HERO, pal=HEROP)),
    ('hero_idle2', C, (323, 49, 490, 260), dict(scale=HERO, pal=HEROP)),
    ('hero_walk1', C, (33, 278, 214, 519), dict(scale=HERO, pal=HEROP)),
    ('hero_walk2', C, (594, 278, 765, 519), dict(scale=HERO, pal=HEROP)),
    ('hero_fall', C, (291, 565, 537, 777), dict(scale=HERO, pal=HEROP)),
    ('hero_dead', C, (836, 651, 1098, 777), dict(scale=HERO, pal=HEROP)),
    ('hero_cheer', C, (2244, 1305, 2410, 1536), dict(scale=HERO, pal=HEROP)),
    ('fire_unlit', I, (61, 169, 329, 358), dict(scale=FIRE, pal=[0, 1, 2, 3])),
    ('fire1', I, (428, 146, 650, 369), dict(scale=FIRE, pal=FIREP)),
    ('fire2', I, (738, 123, 983, 369), dict(scale=FIRE, pal=FIREP)),
    ('fire3', I, (1070, 100, 1316, 369), dict(scale=FIRE, pal=FIREP)),
    ('fire_aura', I, (1390, 179, 1935, 736), dict(height=31, pal=[0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11])),
    ('skull', I, (84, 525, 329, 724), dict(height=12, pal=[0, 1, 2, 3, 4, 5, 9])),
    ('grave', I, (405, 433, 684, 724), dict(height=16, pal=[0, 1, 2, 3])),
    ('flag', I, (2434, 422, 2691, 724), dict(height=22, pal=[0, 1, 2, 3, 6, 7, 11], thr=0.3)),
    ('chest_closed', I, (61, 846, 364, 1103), dict(height=14, pal=[0, 2, 3, 7, 11])),
    ('chest_open', I, (990, 788, 1304, 1114), dict(height=16, pal=[0, 2, 3, 5, 7, 11])),
    ('whistle', I, (1758, 1236, 2004, 1424), dict(height=12, pal=[0, 1, 2, 3, 4, 5])),
    ('scales', I, (2056, 1178, 2371, 1493), dict(height=18, pal=[0, 7, 11], thr=0.16)),
    ('signpost', I, (2423, 1167, 2703, 1504), dict(height=18, pal=[0, 1, 2, 3, 4], thr=0.35)),
    ('scroll', I, (1414, 1201, 1682, 1470), dict(height=14, pal=[0, 1, 2, 3, 4, 5])),
    ('portal1', I, (1449, 789, 1796, 1137), dict(height=24, pal=[0, 1, 2, 3, 5, 10])),
    ('portal2', I, (1907, 789, 2256, 1137), dict(height=24, pal=[0, 1, 2, 3, 5, 10])),
    ('portal3', I, (2355, 789, 2714, 1137), dict(height=24, pal=[0, 1, 2, 3, 5, 10])),
    ('gate', T, (2290, 518, 2744, 1018), dict(height=40, mode='tile', pal=[0, 1, 2, 3, 7, 11])),
]
if SPEC:
    FRAMES = [(n, f, tuple(r), o) for n, f, r, o in SPEC]

sprites = []
for name, fn, rect, opt in FRAMES:
    try:
        arr, sc = cut(fn, rect, **opt)
        if name == 'flag':   # the thin pole is lost in the downscale: redraw it (1 px gold) from the base up
            a = arr[..., 3] > 0
            h, w = a.shape
            cols = np.nonzero(a[h - 3:].any(0))[0]
            px = int(round(cols.mean())) if len(cols) else int(np.nonzero(a.any(0))[0].min())
            arr[0:h - 1, px] = (0xE2, 0xB8, 0x4B, 255)
            arr[h - 1, max(0, px - 1):px + 2] = (0x4A, 0x44, 0x58, 255)
        sprites.append((name, arr))
        print('%-13s %3d x %3d  (src/logical %.2f)' % (name, arr.shape[1], arr.shape[0], sc))
    except Exception as e:
        print('SKIP', name, repr(e))

# pack (shelves, 1 px padding)
W = 256
x = y = 1; rowh = 0; pos = {}
for name, arr in sprites:
    h, w = arr.shape[:2]
    if x + w + 1 > W:
        x = 1; y += rowh + 1; rowh = 0
    pos[name] = (x, y, w, h); x += w + 1; rowh = max(rowh, h)
H = y + rowh + 1
atlas = np.zeros((H, W, 4), np.uint8)
for name, arr in sprites:
    px, py, w, h = pos[name]
    atlas[py:py + h, px:px + w] = arr
Image.fromarray(atlas, 'RGBA').save(OUT + 'atlas.png')
json.dump({'frames': {n: dict(x=p[0], y=p[1], w=p[2], h=p[3]) for n, p in pos.items()}}, open(OUT + 'atlas.json', 'w'), indent=1)

# contact sheet: 8x on #2B2738 with names
S = 8; cell_w = 300; cell_h = 300; cols = 6
rows = (len(sprites) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cell_w, rows * cell_h), (0x2B, 0x27, 0x38))
d = ImageDraw.Draw(sheet)
for i, (name, arr) in enumerate(sprites):
    cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
    im = Image.fromarray(arr, 'RGBA').resize((arr.shape[1] * S, arr.shape[0] * S), Image.NEAREST)
    sheet.paste(im, (cx + (cell_w - im.width) // 2, cy + 8), im)
    d.text((cx + 8, cy + cell_h - 22), '%s %dx%d' % (name, arr.shape[1], arr.shape[0]), fill=(0xF1, 0xEA, 0xD8))
sheet.save(OUT + 'contact.png')
print('atlas', W, H, 'frames', len(sprites))

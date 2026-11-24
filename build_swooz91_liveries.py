"""
SWOOZ '91 — Smooth Heritage & Cosmic Orbital Livery Suite for Backseat Champions
Built from Dom's 'swooz · est. 1991 ·' emblem (#141414 Satin Onyx, #F2EFE9 Porcelain Cream, #FF601A Tangerine Blaze).
Generates UV-verified 2048x2048 (and 1024x1024 GT) textures across all 9 car classes,
plus 256x256 RGBA team icon and wet-gloss livery.json (smoothness 0.88), installed alongside SWOOZ Racing.
"""
from collections import deque
import json
import math
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LOGO_SRC = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\.user_uploaded\media_1795482402512_760b0a58.png"
SA_LIVERIES = r"D:\SteamLibrary\steamapps\common\Backseat Champions\BackseatChampions_Data\StreamingAssets\Liveries"
UV_DIR = os.path.join(SA_LIVERIES, "UV Templates")

USER_LIVERY_DIR = r"C:\Users\souls\AppData\LocalLow\f13rce\BackseatChampions\Liveries\user_Swooz91"
LOCAL_BACKUP_DIR = r"C:\Users\souls\.gemini\antigravity\scratch\backseat-pitwall\liveries\user_Swooz91"
VERIFY_DIR = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\scratch\uv_verify"
SHOWCASE_PATH = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\swooz91_livery_showcase.png"

# Exact SWOOZ '91 Palette sampled from uploaded artwork
ONYX = (20, 20, 20, 255)
ONYX_DEEP = (13, 13, 15, 255)
ONYX_SOFT = (28, 28, 31, 255)
CREAM = (242, 239, 233, 255)
CREAM_WARM = (232, 226, 215, 255)
TANGERINE = (255, 96, 26, 255)
TANGERINE_DEEP = (218, 68, 10, 255)
PEACH = (255, 162, 98, 255)


def load_round_font(size: int) -> ImageFont.FreeTypeFont:
    win_fonts = r"C:\Windows\Fonts"
    for f in ["arlrdbd.ttf", "cooperb.ttf", "bauhs93.ttf", "segoeuib.ttf", "arialbd.ttf"]:
        p = os.path.join(win_fonts, f)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def dilate_alpha(mask: Image.Image, radius: int) -> Image.Image:
    """Smooth circular dilation of an L-mode alpha mask using MaxFilter + Gaussian anti-alias."""
    if radius <= 0:
        return mask
    m = mask
    # Apply iterative 3x3 / 5x5 max filters + Gaussian threshold for smooth round join
    big = m.filter(ImageFilter.GaussianBlur(radius=radius * 0.58))
    px = big.load()
    w, h = big.size
    out = Image.new("L", (w, h), 0)
    opx = out.load()
    # Combine crisp box distance with smooth edge ramp
    box = m
    steps = max(1, radius // 2)
    for _ in range(steps):
        box = box.filter(ImageFilter.MaxFilter(5))
    if radius % 2 == 1:
        box = box.filter(ImageFilter.MaxFilter(3))
    box_blur = box.filter(ImageFilter.GaussianBlur(radius=1.35))
    bpx = box_blur.load()
    for y in range(h):
        for x in range(w):
            v = bpx[x, y]
            opx[x, y] = min(255, max(0, int((v - 68) * 2.45)))
    return out


def extract_swooz91_assets():
    """Extract three crisp die-cut RGBA decals directly from Dom's uploaded 'swooz · est. 1991 ·' artwork:
    1) emblem_full: Full orbital emblem with interior black outlines preserved via corner flood-fill + die-cut sticker rim.
    2) word_bubble: Pure 'swooz' bubble script with double sticker outline (works on both Cream & Onyx!).
    3) est_cream / est_dark: '· est. 1991 ·' heritage tag.
    """
    raw = Image.open(LOGO_SRC).convert("RGBA")
    # Crop inside the 1px outer screenshot border -> exact inner region (90, 165, 782, 702)
    crop = raw.crop((90, 165, 782, 702))
    w, h = crop.size
    px = crop.load()

    # 1) Corner flood-fill to mark ONLY exterior #141414 background (preserving interior black comic outlines!)
    bg = [[False] * w for _ in range(h)]
    q = deque()
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        bg[sy][sx] = True
        q.append((sx, sy))

    while q:
        cx, cy = q.popleft()
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny][nx]:
                r, g, b, _ = px[nx, ny]
                # Background is ~ (20, 20, 20); stop before touching cream/orange anti-aliased edge
                if r < 48 and g < 48 and b < 48:
                    bg[ny][nx] = True
                    q.append((nx, ny))

    fg_mask = Image.new("L", (w, h), 0)
    mpx = fg_mask.load()
    for y in range(h):
        for x in range(w):
            if not bg[y][x]:
                mpx[x, y] = 255

    # Feather alpha slightly + add a crisp 5px Onyx sticker outline around the outer cream orbits so it pops on Cream too!
    smooth_fg = fg_mask.filter(ImageFilter.GaussianBlur(radius=0.75))
    outer_rim = dilate_alpha(fg_mask, 6)

    emblem_full = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rim_layer = Image.new("RGBA", (w, h), ONYX)
    rim_layer.putalpha(outer_rim)
    emblem_full.alpha_composite(rim_layer)

    art_layer = crop.copy()
    art_layer.putalpha(smooth_fg)
    emblem_full.alpha_composite(art_layer)
    ebbox = emblem_full.getbbox()
    if ebbox:
        emblem_full = emblem_full.crop(ebbox)

    # 2) Pure 'swooz' Bubble Script cutout from orange channel (x=108..764, y=312..530 in raw)
    wcrop = raw.crop((92, 292, 780, 550))
    ww, wh = wcrop.size
    wpx = wcrop.load()
    orange_mask = Image.new("L", (ww, wh), 0)
    ompx = orange_mask.load()
    for y in range(wh):
        for x in range(ww):
            r, g, b, _ = wpx[x, y]
            # Measure pure orangeness (vivid #FF601A has r-b ~ 229, cream has r-b ~ 9, onyx has r-b ~ 0)
            chroma = r - b
            if chroma > 24:
                ompx[x, y] = min(255, int((chroma - 20) * 1.45))

    inner_black_m = dilate_alpha(orange_mask, 7)
    mid_cream_m = dilate_alpha(inner_black_m, 8)
    outer_pin_m = dilate_alpha(mid_cream_m, 4)

    word_bubble = Image.new("RGBA", (ww, wh), (0, 0, 0, 0))
    for col, msk in [(ONYX, outer_pin_m), (CREAM, mid_cream_m), (ONYX, inner_black_m), (TANGERINE, orange_mask)]:
        lyr = Image.new("RGBA", (ww, wh), col)
        lyr.putalpha(msk)
        word_bubble.alpha_composite(lyr)
    wbbox = word_bubble.getbbox()
    if wbbox:
        word_bubble = word_bubble.crop(wbbox)

    # 3) Extract '· est. 1991 ·' heritage tag from raw (300..565, 646..694)
    ecrop = raw.crop((300, 646, 565, 694))
    ew, eh = ecrop.size
    epx = ecrop.load()
    est_cream = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))
    est_dark = Image.new("RGBA", (ew, eh), (0, 0, 0, 0))
    ec_px = est_cream.load()
    ed_px = est_dark.load()
    for y in range(eh):
        for x in range(ew):
            r, g, b, _ = epx[x, y]
            a = min(255, max(0, int((max(r, g, b) - 24) * 1.22)))
            if a > 8:
                ec_px[x, y] = (CREAM[0], CREAM[1], CREAM[2], a)
                ed_px[x, y] = (ONYX[0], ONYX[1], ONYX[2], a)
    eb2 = est_cream.getbbox()
    if eb2:
        est_cream = est_cream.crop(eb2)
        est_dark = est_dark.crop(eb2)

    return emblem_full, word_bubble, est_cream, est_dark


def make_smooth_onyx_canvas(size: int = 2048) -> Image.Image:
    """Velvety satin #141414 Onyx base (smooth non-busy finish so curves & cream panels look liquid-clean)."""
    return Image.new("RGBA", (size, size), ONYX)


def paste_center(canvas: Image.Image, decal: Image.Image, cx: int, cy: int, angle: float = 0.0, scale: float = 1.0):
    im = decal
    if abs(scale - 1.0) > 1e-3:
        nw = max(1, int(im.width * scale))
        nh = max(1, int(im.height * scale))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    if abs(angle) > 1e-2:
        im = im.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def make_91_roundel(num: str = "91", size: int = 190, style: str = "pill") -> Image.Image:
    """Smooth retro-modern '91 number badge matching the bubble/sticker outline aesthetic of Dom's logo."""
    ss = 2
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = S // 2, S // 2
    fnt = load_round_font(int(S * (0.43 if len(num) > 1 else 0.54)))

    if style == "circle":
        r = int(S * 0.45)
        d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=ONYX)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=CREAM, outline=TANGERINE, width=max(8, S // 22))
        d.ellipse([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14], outline=ONYX, width=max(4, S // 48))
    elif style == "stock":
        fnt = load_round_font(int(S * 0.56))
        bb = d.textbbox((0, 0), num, font=fnt)
        tx, ty = cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2
        # Triple smooth outline matching 'swooz' sticker!
        d.text((tx, ty), num, font=fnt, fill=CREAM, stroke_width=max(20, S // 11), stroke_fill=ONYX)
        d.text((tx, ty), num, font=fnt, fill=CREAM, stroke_width=max(13, S // 16), stroke_fill=CREAM)
        d.text((tx, ty), num, font=fnt, fill=TANGERINE, stroke_width=max(6, S // 30), stroke_fill=ONYX)
        im = im.resize((size, size), Image.Resampling.LANCZOS)
        bbox = im.getbbox()
        return im.crop(bbox) if bbox else im
    else:
        # Smooth rounded vintage GT/F1 capsule
        w2, h2 = int(S * 0.45), int(S * 0.41)
        rad = int(S * 0.19)
        d.rounded_rectangle([cx - w2 - 6, cy - h2 - 6, cx + w2 + 6, cy + h2 + 6], radius=rad + 4, fill=ONYX)
        d.rounded_rectangle([cx - w2, cy - h2, cx + w2, cy + h2], radius=rad, fill=CREAM, outline=TANGERINE, width=max(8, S // 24))
        d.rounded_rectangle([cx - w2 + 12, cy - h2 + 12, cx + w2 - 12, cy + h2 - 12], radius=max(8, rad - 10), outline=ONYX, width=max(4, S // 52))

    bb = d.textbbox((0, 0), num, font=fnt)
    tx, ty = cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2
    d.text((tx, ty), num, font=fnt, fill=TANGERINE, stroke_width=max(6, S // 32), stroke_fill=ONYX)
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def draw_puffy_star(canvas: Image.Image, cx: int, cy: int, radius: int, angle_deg: float = -12.0, fill=CREAM, rim=ONYX):
    """Draws the exact soft-cornered puffy 5-point Y2K star from Dom's 'swooz · est. 1991' logo (2x anti-aliased)."""
    ss = 2
    pad = int(radius * 1.45) * ss
    S = pad * 2
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    scx, scy = S // 2, S // 2
    r_mid = radius * 0.78 * ss
    amp = radius * 0.24 * ss
    ang0 = math.radians(angle_deg)

    if rim is not None:
        rim_pts = []
        rm = r_mid + max(5, int(radius * 0.16 * ss))
        for i in range(120):
            th = (i / 120.0) * math.tau
            rr = rm + amp * math.cos(5.0 * (th - ang0))
            rim_pts.append((scx + rr * math.cos(th), scy + rr * math.sin(th)))
        d.polygon(rim_pts, fill=rim)

    pts = []
    for i in range(120):
        th = (i / 120.0) * math.tau
        rr = r_mid + amp * math.cos(5.0 * (th - ang0))
        pts.append((scx + rr * math.cos(th), scy + rr * math.sin(th)))
    d.polygon(pts, fill=fill)
    im = im.resize((S // ss, S // ss), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def draw_planet_dot(canvas: Image.Image, cx: int, cy: int, radius: int, fill=CREAM, rim=ONYX):
    ss = 2
    S = (radius + 10) * 2 * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = S // 2
    r = radius * ss
    if rim is not None:
        rw = max(4, int(radius * 0.22 * ss))
        d.ellipse([c - r - rw, c - r - rw, c + r + rw, c + r + rw], fill=rim)
    d.ellipse([c - r, c - r, c + r, c + r], fill=fill)
    im = im.resize((S // ss, S // ss), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def draw_orbital_comet(
    canvas: Image.Image,
    p0: tuple,
    p1: tuple,
    p2: tuple,
    w_start: float,
    w_end: float,
    fill=CREAM,
    rim=ONYX,
):
    """Draws a silky-smooth quadratic Bezier orbital swoosh that tapers from a rounded head to a fine comet tail."""
    xs = [p0[0], p1[0], p2[0]]
    ys = [p0[1], p1[1], p2[1]]
    pad = int(max(w_start, w_end) + 18)
    bx0, by0 = max(0, int(min(xs) - pad)), max(0, int(min(ys) - pad))
    bx1, by1 = min(canvas.width, int(max(xs) + pad)), min(canvas.height, int(max(ys) + pad))
    if bx1 <= bx0 or by1 <= by0:
        return

    ss = 2
    W, H = (bx1 - bx0) * ss, (by1 - by0) * ss
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    steps = 72
    curve = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        qx = (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0] - bx0) * ss
        qy = (mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1] - by0) * ss
        rad = (w_start * (1.0 - t ** 1.25) + w_end * (t ** 1.25)) * 0.5 * ss
        curve.append((qx, qy, rad))

    if rim is not None:
        rim_pad = max(3.5, max(w_start, w_end) * 0.14) * ss
        for qx, qy, rad in curve:
            rr = rad + rim_pad
            d.ellipse([qx - rr, qy - rr, qx + rr, qy + rr], fill=rim)

    for qx, qy, rad in curve:
        d.ellipse([qx - rad, qy - rad, qx + rad, qy + rad], fill=fill)

    im = im.resize((bx1 - bx0, by1 - by0), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (bx0, by0))


def draw_smooth_wave_box(
    canvas: Image.Image,
    box: tuple,
    axis: str = "h",
    cream_side: str = "top",
    amp_frac: float = 0.12,
    freq: float = 1.0,
    phase: float = 0.0,
    ribbon_px: int = 24,
):
    """Fills a rectangular UV island with a 2x-supersampled liquid S-curve split:
    Porcelain Cream on one side, Satin Onyx on the other, separated by a triple-band Tangerine + Onyx + Cream wave!
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return
    ss = 2
    W, H = w * ss, h * ss
    im = Image.new("RGBA", (W, H), ONYX)
    d = ImageDraw.Draw(im)

    if axis == "h":
        mid = H * (0.54 if cream_side == "top" else 0.46)
        amp = H * amp_frac
        pts_wave = []
        for ix in range(0, W + 4, 4):
            u = ix / max(1, W)
            wy = mid + amp * math.sin(u * math.pi * freq + phase)
            pts_wave.append((ix, wy))
        if cream_side == "top":
            poly = [(0, 0), (W, 0)] + list(reversed(pts_wave))
        else:
            poly = pts_wave + [(W, H), (0, H)]
        d.polygon(poly, fill=CREAM)

        # Flowing Tangerine ribbon with crisp Onyx pin-borders
        rw = ribbon_px * ss
        pin = max(4, int(rw * 0.22))
        outer_pts = [(x, y - rw * 0.5 - pin) for x, y in pts_wave] + [(x, y + rw * 0.5 + pin) for x, y in reversed(pts_wave)]
        inner_pts = [(x, y - rw * 0.5) for x, y in pts_wave] + [(x, y + rw * 0.5) for x, y in reversed(pts_wave)]
        hi_pts = [(x, y - rw * 0.18) for x, y in pts_wave] + [(x, y + rw * 0.06) for x, y in reversed(pts_wave)]
        d.polygon(outer_pts, fill=ONYX)
        d.polygon(inner_pts, fill=TANGERINE)
        d.polygon(hi_pts, fill=PEACH)
    else:
        mid = W * (0.54 if cream_side == "left" else 0.46)
        amp = W * amp_frac
        pts_wave = []
        for iy in range(0, H + 4, 4):
            u = iy / max(1, H)
            wx = mid + amp * math.sin(u * math.pi * freq + phase)
            pts_wave.append((wx, iy))
        if cream_side == "left":
            poly = [(0, 0)] + pts_wave + [(0, H)]
        else:
            poly = [(W, 0), (W, H)] + list(reversed(pts_wave))
        d.polygon(poly, fill=CREAM)

        rw = ribbon_px * ss
        pin = max(4, int(rw * 0.22))
        outer_pts = [(x - rw * 0.5 - pin, y) for x, y in pts_wave] + [(x + rw * 0.5 + pin, y) for x, y in reversed(pts_wave)]
        inner_pts = [(x - rw * 0.5, y) for x, y in pts_wave] + [(x + rw * 0.5, y) for x, y in reversed(pts_wave)]
        hi_pts = [(x - rw * 0.18, y) for x, y in pts_wave] + [(x + rw * 0.06, y) for x, y in reversed(pts_wave)]
        d.polygon(outer_pts, fill=ONYX)
        d.polygon(inner_pts, fill=TANGERINE)
        d.polygon(hi_pts, fill=PEACH)

    im = im.resize((w, h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(im, (x0, y0))


def draw_tangerine_wing_panel(canvas: Image.Image, box: tuple, axis: str = "h", cream_edge: str = "bottom"):
    """Clean aerodynamic wing plane in Onyx or Cream with smooth Tangerine + Cream tip band."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(canvas)
    d.rectangle([x0, y0, x1, y1], fill=ONYX)
    w, h = x1 - x0, y1 - y0
    if axis == "h":
        th = max(8, int(h * 0.18))
        ch = max(5, int(h * 0.09))
        if cream_edge == "bottom":
            d.rectangle([x0, y1 - th, x1, y1], fill=TANGERINE)
            d.rectangle([x0, y1 - th - ch - 3, x1, y1 - th - 3], fill=CREAM)
        else:
            d.rectangle([x0, y0, x1, y0 + th], fill=TANGERINE)
            d.rectangle([x0, y0 + th + 3, x1, y0 + th + 3 + ch], fill=CREAM)
    else:
        tw = max(8, int(w * 0.18))
        cw = max(5, int(w * 0.09))
        if cream_edge == "left":
            d.rectangle([x0, y0, x0 + tw, y1], fill=TANGERINE)
            d.rectangle([x0 + tw + 3, y0, x0 + tw + 3 + cw, y1], fill=CREAM)
        else:
            d.rectangle([x1 - tw, y0, x1, y1], fill=TANGERINE)
            d.rectangle([x1 - tw - 3 - cw, y0, x1 - tw - 3, y1], fill=CREAM)


def draw_center_heritage_ribbon(d: ImageDraw.ImageDraw, cx: int, y0: int, y1: int, half_tang: int = 18, cream_gap: int = 6):
    """Smooth triple centerline stripe: Cream outer pins + Onyx pin gap + Tangerine core!"""
    d.rectangle([cx - half_tang - cream_gap - 8, y0, cx + half_tang + cream_gap + 8, y1], fill=ONYX)
    d.rectangle([cx - half_tang - cream_gap - 5, y0, cx - half_tang - 3, y1], fill=CREAM)
    d.rectangle([cx + half_tang + 3, y0, cx + half_tang + cream_gap + 5, y1], fill=CREAM)
    d.rectangle([cx - half_tang, y0, cx + half_tang, y1], fill=TANGERINE)
    d.rectangle([cx - max(3, half_tang // 4), y0, cx + max(3, half_tang // 4), y1], fill=PEACH)


# ==============================================================================
# 1. FORMULA MODERN (2022-2026 Ground-Effect F1) — 2048x2048
# ==============================================================================
def build_formula_modern(emblem, word, est_c, est_d, num_pill) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top Sharkfin / Engine Cover Upper Flanks (x=40..585 & 1320..1865, y=12..218)
    draw_smooth_wave_box(im, (40, 12, 585, 218), axis="h", cream_side="bottom", amp_frac=0.14, phase=0.4, ribbon_px=16)
    draw_smooth_wave_box(im, (1320, 12, 1865, 218), axis="h", cream_side="bottom", amp_frac=0.14, phase=2.7, ribbon_px=16)
    draw_puffy_star(im, 145, 75, 24, fill=CREAM)
    draw_puffy_star(im, 1760, 75, 24, angle_deg=18, fill=CREAM)
    paste_center(im, word, 355, 112, scale=0.34)
    paste_center(im, word, 1545, 112, scale=0.34)

    # Cockpit Collar / Headrest (x=850..1055, y=185..395, cx=952) — Porcelain Cream with Tangerine spine
    d.rectangle([850, 185, 1055, 395], fill=CREAM)
    draw_center_heritage_ribbon(d, 952, 185, 395, half_tang=14, cream_gap=5)
    paste_center(im, word, 952, 312, scale=0.22)

    # Left & Right Flowing Sidepods + Engine Cover (x=25..935 & 970..1885, y=222..560)
    # Silky S-wave split: Porcelain Cream upper deck flowing into Satin Onyx undercut with Tangerine ribbon!
    draw_smooth_wave_box(im, (25, 222, 935, 555), axis="h", cream_side="top", amp_frac=0.16, freq=1.25, phase=0.2, ribbon_px=26)
    draw_smooth_wave_box(im, (970, 222, 1885, 555), axis="h", cream_side="top", amp_frac=0.16, freq=1.25, phase=2.9, ribbon_px=26)

    # Cosmic orbital arcs & stars sweeping across sidepods
    draw_orbital_comet(im, (90, 485), (430, 245), (860, 355), w_start=26, w_end=5, fill=TANGERINE, rim=ONYX)
    draw_orbital_comet(im, (1820, 485), (1480, 245), (1045, 355), w_start=26, w_end=5, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 150, 300, 26, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 1760, 300, 26, angle_deg=15, fill=TANGERINE, rim=ONYX)
    draw_planet_dot(im, 765, 290, 13, fill=TANGERINE, rim=ONYX)
    draw_planet_dot(im, 1140, 290, 13, fill=TANGERINE, rim=ONYX)

    paste_center(im, emblem, 445, 368, scale=0.44)
    paste_center(im, emblem, 1465, 368, scale=0.44)
    paste_center(im, est_c, 715, 508, scale=0.82)
    paste_center(im, est_c, 1200, 508, scale=0.82)

    # Halo (x=15..555, y=555..1060) — Porcelain Cream halo with Tangerine apex swoop & bubble 'swooz'
    d.polygon([(15, 735), (555, 555), (555, 675), (260, 810), (555, 945), (555, 1060), (15, 880)], fill=CREAM)
    d.polygon([(15, 782), (245, 782), (282, 810), (245, 838), (15, 838)], fill=TANGERINE)
    paste_center(im, word, 142, 810, scale=0.25)

    # Front Nosecone (x=10..230, y=885..1335, cx=118, 180-deg front-facing!)
    ncx = 118
    d.polygon([(12, 885), (224, 885), (196, 1335), (40, 1335)], fill=CREAM)
    draw_center_heritage_ribbon(d, ncx, 885, 1335, half_tang=15, cream_gap=5)
    paste_center(im, word, ncx, 962, angle=180, scale=0.22)
    paste_center(im, num_pill, ncx, 1095, angle=180, scale=0.66)
    paste_center(im, emblem, ncx, 1240, angle=180, scale=0.21)

    # Rear Wing Main Plane & DRS Flap (x=512..872, y=605..740 [180 deg] & y=748..905 [0 deg])
    draw_tangerine_wing_panel(im, (512, 605, 872, 740), "h", "top")
    d.rectangle([512, 748, 872, 905], fill=CREAM)
    d.rectangle([512, 876, 872, 905], fill=TANGERINE)
    paste_center(im, word, 692, 675, angle=180, scale=0.45)
    paste_center(im, word, 692, 815, angle=0, scale=0.47)

    # Sidepod Upper Shoulders (x=250..650, y=1090..1345 & x=670..1075, y=1005..1260)
    draw_smooth_wave_box(im, (250, 1090, 650, 1345), axis="h", cream_side="top", amp_frac=0.14, ribbon_px=18)
    draw_smooth_wave_box(im, (670, 1005, 1075, 1260), axis="h", cream_side="top", amp_frac=0.14, phase=3.1, ribbon_px=18)

    # Engine Cover Cowl Shield (x=1375..1718, y=785..1115, cx=1546)
    scx = 1546
    d.polygon([(scx, 780), (1720, 1045), (1546, 1120), (1372, 1045)], fill=CREAM)
    draw_center_heritage_ribbon(d, scx, 785, 1115, half_tang=14, cream_gap=5)
    paste_center(im, emblem, scx, 965, angle=180, scale=0.28)

    # Front Wing Stacked Elements (x=955..1535, y=1325..1695)
    d.rectangle([955, 1325, 1535, 1695], fill=ONYX)
    d.rectangle([955, 1465, 1535, 1560], fill=CREAM)
    d.rectangle([955, 1564, 1535, 1602], fill=TANGERINE)
    d.rectangle([955, 1325, 1038, 1695], fill=TANGERINE)
    d.rectangle([1452, 1325, 1535, 1695], fill=TANGERINE)
    paste_center(im, word, 1245, 1512, scale=0.44)

    # Wing Endplates at bottom-left (x=80..410 & 490..815, y=1850..1945)
    draw_tangerine_wing_panel(im, (80, 1850, 410, 1945), "h", "bottom")
    draw_tangerine_wing_panel(im, (490, 1850, 815, 1945), "h", "bottom")
    paste_center(im, word, 245, 1892, angle=-12, scale=0.29)
    paste_center(im, word, 650, 1892, angle=12, scale=0.29)

    # Right-column vertical wing plates
    draw_tangerine_wing_panel(im, (1758, 720, 1932, 1340), "v", "left")

    return im


# ==============================================================================
# 2. FORMULA (2018-2021 Hybrid Wide-Track F1) — 2048x2048
# ==============================================================================
def build_formula(emblem, word, est_c, est_d, num_pill) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top Wing Planes (x=5..720 & 735..1445, y=5..200)
    draw_tangerine_wing_panel(im, (5, 5, 720, 200), "h", "bottom")
    draw_tangerine_wing_panel(im, (735, 5, 1445, 200), "h", "bottom")
    paste_center(im, word, 360, 92, scale=0.46)
    paste_center(im, word, 1090, 92, scale=0.46)

    # Engine Cover / Sharkfin Triangles (x=5..455 & 475..930, y=200..510)
    draw_smooth_wave_box(im, (5, 200, 455, 510), axis="h", cream_side="top", amp_frac=0.15, ribbon_px=20)
    draw_smooth_wave_box(im, (475, 200, 930, 510), axis="h", cream_side="top", amp_frac=0.15, phase=3.14, ribbon_px=20)
    paste_center(im, emblem, 295, 385, scale=0.33)
    paste_center(im, emblem, 635, 385, scale=0.33)

    # Rear Wing Main Planes (x=8..425, y=532..855)
    draw_tangerine_wing_panel(im, (8, 532, 425, 608), "h", "bottom")
    d.rectangle([8, 612, 425, 688], fill=CREAM)
    d.rectangle([8, 612, 425, 628], fill=TANGERINE)
    draw_tangerine_wing_panel(im, (8, 694, 425, 855), "h", "bottom")
    paste_center(im, word, 216, 568, angle=0, scale=0.36)
    paste_center(im, word, 216, 652, angle=180, scale=0.36)
    paste_center(im, word, 216, 755, angle=0, scale=0.46)
    paste_center(im, est_c, 216, 816, angle=0, scale=0.72)

    # Nosecone & Front Bulkhead (x=35..398, y=990..1775, cx=216) — Smooth Cream nose with Tangerine spine!
    d.polygon([(35, 990), (398, 990), (355, 1775), (78, 1775)], fill=CREAM)
    draw_center_heritage_ribbon(d, 216, 990, 1775, half_tang=18, cream_gap=6)
    draw_puffy_star(im, 125, 1115, 22, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 307, 1115, 22, angle_deg=18, fill=TANGERINE, rim=ONYX)
    paste_center(im, emblem, 216, 1225, scale=0.32)
    paste_center(im, num_pill, 216, 1465, scale=0.70)
    paste_center(im, word, 216, 1630, scale=0.18)

    # Central Sidepod / Monocoque Top Deck (x=405..968, y=1020..1330)
    draw_smooth_wave_box(im, (405, 1020, 968, 1330), axis="h", cream_side="top", amp_frac=0.15, ribbon_px=22)
    paste_center(im, emblem, 686, 1172, scale=0.44)

    # Lower Sidepod Flanks (x=275..1115, y=1285..1935)
    draw_smooth_wave_box(im, (295, 1335, 1105, 1615), axis="h", cream_side="top", amp_frac=0.16, ribbon_px=20)
    draw_smooth_wave_box(im, (275, 1660, 1100, 1935), axis="h", cream_side="bottom", amp_frac=0.16, ribbon_px=20)
    paste_center(im, word, 695, 1465, scale=0.46)
    paste_center(im, word, 695, 1815, scale=0.46)

    # Vertical Side / Floor Edge Strips
    draw_tangerine_wing_panel(im, (1455, 275, 1705, 945), "v", "left")
    draw_tangerine_wing_panel(im, (1370, 785, 1585, 1480), "v", "right")
    paste_center(im, word, 1575, 560, angle=-80, scale=0.38)
    paste_center(im, word, 1475, 1135, angle=80, scale=0.38)

    # Right-edge fin/endplate & top-right endplates
    draw_tangerine_wing_panel(im, (1825, 5, 2040, 1875), "v", "left")
    draw_tangerine_wing_panel(im, (1460, 5, 1628, 265), "h", "bottom")
    draw_tangerine_wing_panel(im, (1636, 5, 1805, 265), "h", "bottom")
    draw_puffy_star(im, 1544, 118, 26, fill=CREAM)
    draw_puffy_star(im, 1720, 118, 26, angle_deg=15, fill=CREAM)

    return im


# ==============================================================================
# 3. FORMULA CLASSIC (1990s V10 Era F1 — THE '1991' FLAGSHIP!) — 2048x2048
# ==============================================================================
def build_formula_classic(emblem, word, est_c, est_d, num_circle) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Rear Wing Endplates (x=25..342, y=10..430)
    draw_tangerine_wing_panel(im, (25, 10, 180, 430), "h", "bottom")
    draw_tangerine_wing_panel(im, (188, 10, 342, 430), "h", "bottom")
    paste_center(im, emblem, 102, 205, scale=0.22)
    paste_center(im, emblem, 265, 205, scale=0.22)

    # Top horizontal wing strip (x=675..1245, y=8..82)
    draw_tangerine_wing_panel(im, (675, 8, 1245, 82), "h", "top")
    paste_center(im, word, 960, 46, angle=180, scale=0.33)

    # Upper Monocoque / Sidepod Flanks (x=30..1400, y=450..895, centerline y=672)
    d.rectangle([30, 450, 1400, 895], fill=CREAM)
    d.rectangle([30, 450, 1400, 520], fill=ONYX)
    d.rectangle([30, 825, 1400, 895], fill=ONYX)
    d.rectangle([30, 646, 1400, 698], fill=TANGERINE)
    d.rectangle([30, 638, 1400, 644], fill=ONYX)
    d.rectangle([30, 700, 1400, 706], fill=ONYX)

    # Vertical Front & Rear Wing Blades (x=1630..2035, y=10..1165)
    d.rectangle([1565, 20, 1645, 1180], fill=TANGERINE)
    d.rectangle([1658, 10, 1818, 585], fill=CREAM)
    d.rectangle([1788, 10, 1818, 585], fill=TANGERINE)
    draw_tangerine_wing_panel(im, (1828, 10, 2035, 585), "v", "left")
    draw_tangerine_wing_panel(im, (1630, 600, 1755, 1165), "v", "right")
    paste_center(im, word, 1732, 295, angle=90, scale=0.58)
    paste_center(im, word, 1692, 880, angle=-90, scale=0.52)
    paste_center(im, est_c, 1925, 295, angle=85, scale=0.88)

    # Main 1991 V10 Chassis / Sidepods / Nosecone (x=10..2038, y=915..2035, centerline y=1488, nose at x=2030!)
    cy = 1488
    # Porcelain Cream body shell with smooth sweeping Onyx lower sidepod scallops!
    d.polygon(
        [(10, 915), (860, 915), (1755, 1285), (2038, 1410), (2038, 1566), (1755, 1690), (860, 2035), (10, 2035)],
        fill=CREAM,
    )
    # Smooth curved Onyx + Tangerine sidepod undercuts along outer edges
    draw_orbital_comet(im, (20, 1020), (620, 1040), (1460, 1330), w_start=170, w_end=22, fill=ONYX, rim=TANGERINE)
    draw_orbital_comet(im, (20, 1955), (620, 1935), (1460, 1645), w_start=170, w_end=22, fill=ONYX, rim=TANGERINE)

    # Tapered 1991 Tangerine + Onyx centerline arrow converging to the nose tip!
    d.polygon([(310, cy - 64), (2038, cy - 32), (2038, cy + 32), (310, cy + 64)], fill=ONYX)
    d.polygon([(315, cy - 52), (2038, cy - 24), (2038, cy + 24), (315, cy + 52)], fill=TANGERINE)
    d.polygon([(320, cy - 12), (2038, cy - 6), (2038, cy + 6), (320, cy + 12)], fill=PEACH)

    # Sidepod full 'swooz · est. 1991 ·' emblems & puffy cosmic stars!
    paste_center(im, emblem, 745, 1205, angle=-8, scale=0.46)
    paste_center(im, emblem, 745, 1770, angle=188, scale=0.46)
    draw_puffy_star(im, 430, 1290, 26, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 430, 1685, 26, angle_deg=18, fill=TANGERINE, rim=ONYX)

    # Nosecone #91 vintage circle roundel + bubble 'swooz'
    paste_center(im, num_circle, 1835, cy, angle=-90, scale=0.66)
    paste_center(im, word, 1590, cy, angle=-90, scale=0.34)

    return im


# ==============================================================================
# 4. FORMULA OLDSKOOL (Late-1980s / 1991 MP4 Turbo Era F1) — 2048x2048
# ==============================================================================
def build_formula_oldskool(emblem, word, est_c, est_d, num_circle) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Rear Wing Main Plane (x=10..395, y=30..315)
    d.rectangle([10, 30, 395, 168], fill=CREAM)
    d.rectangle([10, 144, 395, 168], fill=TANGERINE)
    draw_tangerine_wing_panel(im, (10, 174, 395, 315), "h", "top")
    paste_center(im, word, 202, 92, angle=0, scale=0.45)
    paste_center(im, word, 202, 248, angle=180, scale=0.45)

    # Upper Cockpit Surround / Monocoque Shoulders (x=1005..1670 -> 1130..1555, y=5..880, cx=1342)
    # Iconic Senna-era Cream + Tangerine + Onyx smooth heritage collar!
    d.polygon([(1005, 5), (1670, 5), (1555, 280), (1555, 880), (1130, 880), (1130, 280)], fill=CREAM)
    d.polygon([(1215, 195), (1342, 325), (1469, 195), (1469, 880), (1215, 880)], fill=ONYX)
    d.polygon([(1235, 225), (1342, 335), (1449, 225), (1449, 880), (1235, 880)], fill=TANGERINE)
    d.rectangle([1316, 330, 1368, 880], fill=CREAM)

    # Upper Wing / Flap Boxes (x=485..1098, y=375..495)
    draw_tangerine_wing_panel(im, (485, 375, 785, 495), "h", "bottom")
    draw_tangerine_wing_panel(im, (798, 375, 1098, 495), "h", "bottom")
    paste_center(im, word, 635, 428, scale=0.35)
    paste_center(im, word, 948, 428, scale=0.35)

    # Mid-left Twin Horizontal Wing Plates (x=18..525 & 540..1045, y=625..798)
    d.rectangle([18, 625, 525, 798], fill=CREAM)
    d.rectangle([18, 768, 525, 798], fill=TANGERINE)
    d.rectangle([540, 625, 1045, 798], fill=CREAM)
    d.rectangle([540, 768, 1045, 798], fill=TANGERINE)
    paste_center(im, word, 272, 698, scale=0.52)
    paste_center(im, word, 792, 698, scale=0.52)

    # Left & Right Sidepods / Engine Cover (y=815..1142 & y=1148..1475, x=10..1045)
    for idx, (y_top, y_bot) in enumerate([(815, 1142), (1148, 1475)]):
        draw_smooth_wave_box(im, (10, y_top, 1045, y_bot), axis="h", cream_side="top", amp_frac=0.16, phase=idx * 2.4, ribbon_px=22)
        wx = 420 if idx == 0 else 615
        paste_center(im, emblem, wx, y_top + 132, scale=0.42)
        paste_center(im, est_c, wx + (295 if idx == 0 else -295), y_bot - 52, scale=0.82)
        draw_puffy_star(im, wx + (260 if idx == 0 else -260), y_top + 95, 24, fill=TANGERINE, rim=ONYX)

    # V-Shaped Nosecone (x=1035..1655, y=940..1605, tip cx=1342, y=1595)
    cx = 1342
    d.polygon([(1035, 940), (1655, 940), (1655, 1280), (cx, 1610), (1035, 1280)], fill=CREAM)
    d.polygon([(1105, 940), (cx, 1205), (1580, 940), (1618, 940), (cx, 1255), (1067, 940)], fill=ONYX)
    d.polygon([(1122, 940), (cx, 1185), (1562, 940), (1596, 940), (cx, 1230), (1088, 940)], fill=TANGERINE)
    paste_center(im, emblem, cx, 1085, scale=0.28)
    paste_center(im, num_circle, cx, 1385, scale=0.68)

    # Lower Rear Wing Endplates (x=455..732 & 740..1015, y=1810..2042)
    draw_tangerine_wing_panel(im, (455, 1810, 732, 2042), "h", "top")
    draw_tangerine_wing_panel(im, (740, 1810, 1015, 2042), "h", "top")
    paste_center(im, num_circle, 535, 1950, angle=-90, scale=0.45)
    paste_center(im, num_circle, 935, 1950, angle=90, scale=0.45)
    paste_center(im, word, 655, 1935, angle=90, scale=0.26)
    paste_center(im, word, 815, 1935, angle=-90, scale=0.26)

    return im


# ==============================================================================
# 5. FORMULA LEGACY (1960s Classic Cigar GP Car) — 2048x2048
# ==============================================================================
def build_formula_legacy(emblem, word, est_c, est_d, num_circle) -> Image.Image:
    # Smooth Porcelain Cream Grand Prix Cigar with Satin Onyx lower belly & Tangerine heritage racing spine!
    im = Image.new("RGBA", (2048, 2048), CREAM)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 1120, 2048, 2048], fill=ONYX)

    # 1. Front Nosecone & Radiator Mouth (centerline x=336, y=10..550)
    draw_center_heritage_ribbon(d, 336, 10, 550, half_tang=24, cream_gap=7)

    # 2. Lower Cigar Nose (centerline x=395, y=550..955)
    draw_center_heritage_ribbon(d, 395, 550, 955, half_tang=24, cream_gap=7)
    paste_center(im, num_circle, 395, 735, scale=0.84)
    paste_center(im, word, 395, 882, scale=0.32)

    # 3. Upper Cockpit / Fuselage (x=615..1560, y=10..435, horizontal centerline y=218)
    d.rectangle([615, 184, 1560, 252], fill=ONYX)
    d.rectangle([615, 194, 1560, 242], fill=TANGERINE)
    draw_orbital_comet(im, (660, 65), (1080, 155), (1510, 75), w_start=18, w_end=4, fill=TANGERINE, rim=ONYX)
    draw_orbital_comet(im, (660, 370), (1080, 280), (1510, 360), w_start=18, w_end=4, fill=TANGERINE, rim=ONYX)
    paste_center(im, emblem, 1065, 95, angle=0, scale=0.31)
    paste_center(im, emblem, 1065, 342, angle=180, scale=0.31)
    draw_puffy_star(im, 1385, 98, 22, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 1385, 338, 22, angle_deg=18, fill=TANGERINE, rim=ONYX)

    # 4. Rear Engine Cover (cx=780, y=605..945) & Flank Plates (x=1058..1424, y=645..900)
    draw_center_heritage_ribbon(d, 780, 605, 945, half_tang=22, cream_gap=6)
    paste_center(im, num_circle, 780, 775, scale=0.74)

    draw_smooth_wave_box(im, (1058, 645, 1238, 900), axis="h", cream_side="top", amp_frac=0.12, ribbon_px=16)
    draw_smooth_wave_box(im, (1244, 645, 1424, 900), axis="h", cream_side="top", amp_frac=0.12, phase=3.14, ribbon_px=16)
    paste_center(im, num_circle, 1148, 740, scale=0.56)
    paste_center(im, word, 1148, 842, scale=0.22)
    paste_center(im, num_circle, 1334, 740, scale=0.56)
    paste_center(im, word, 1334, 842, scale=0.22)

    # 5. Top-Right Fin Plates (x=1490..1900, y=5..278)
    draw_tangerine_wing_panel(im, (1490, 5, 1692, 278), "h", "bottom")
    draw_tangerine_wing_panel(im, (1698, 5, 1900, 278), "h", "bottom")
    paste_center(im, emblem, 1591, 128, scale=0.24)
    paste_center(im, emblem, 1799, 128, scale=0.24)

    return im


# ==============================================================================
# 6. ENDURANCE (Le Mans Hypercar / LMDh Prototype) — 2048x2048
# ==============================================================================
def build_endurance(emblem, word, est_c, est_d, num_pill) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top Rear Wing Main Plane (x=115..585, y=5..105)
    d.rectangle([115, 5, 585, 105], fill=CREAM)
    d.rectangle([115, 82, 585, 105], fill=TANGERINE)
    paste_center(im, word, 350, 46, scale=0.45)

    # Front Nose / Cowl / Fenders Stack (cx=525, y=220..1290) — Smooth Porcelain Cream hood with cosmic arcs!
    cx = 525
    d.polygon([(140, 360), (910, 360), (1015, 1290), (25, 1290)], fill=CREAM)
    draw_orbital_comet(im, (95, 1180), (285, 760), (cx - 48, 430), w_start=42, w_end=8, fill=ONYX, rim=TANGERINE)
    draw_orbital_comet(im, (955, 1180), (765, 760), (cx + 48, 430), w_start=42, w_end=8, fill=ONYX, rim=TANGERINE)
    draw_center_heritage_ribbon(d, cx, 220, 1290, half_tang=20, cream_gap=6)
    draw_puffy_star(im, 255, 620, 30, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 795, 620, 30, angle_deg=18, fill=TANGERINE, rim=ONYX)
    paste_center(im, est_d, cx, 505, scale=0.95)
    paste_center(im, emblem, cx, 735, scale=0.48)
    paste_center(im, num_pill, cx, 985, scale=0.80)
    paste_center(im, word, cx, 1165, scale=0.52)

    # Upper-right Fender Louvers (x=1085..2035, y=445..695)
    draw_smooth_wave_box(im, (1085, 530, 1560, 695), axis="h", cream_side="top", amp_frac=0.14, ribbon_px=16)
    draw_smooth_wave_box(im, (1535, 445, 2035, 610), axis="h", cream_side="top", amp_frac=0.14, phase=2.8, ribbon_px=16)

    # Rear Engine Deck / Butterfly Cowling (x=1115..1895, y=865..1425, rcx=1505)
    rcx = 1505
    draw_smooth_wave_box(im, (1115, 865, 1895, 1425), axis="h", cream_side="top", amp_frac=0.16, freq=1.4, ribbon_px=26)
    draw_center_heritage_ribbon(d, rcx, 865, 1425, half_tang=20, cream_gap=6)
    paste_center(im, emblem, rcx, 1135, scale=0.44)

    # Sharkfin (x=1895..2042, y=5..405 & x=1875..2042, y=840..1825)
    draw_tangerine_wing_panel(im, (1895, 5, 2042, 405), "v", "left")
    draw_smooth_wave_box(im, (1875, 840, 2042, 1825), axis="v", cream_side="right", amp_frac=0.15, freq=1.5, ribbon_px=16)
    paste_center(im, word, 1968, 195, angle=-90, scale=0.38)
    paste_center(im, word, 1962, 1110, angle=-90, scale=0.40)
    paste_center(im, word, 1962, 1560, angle=90, scale=0.40)

    # Left & Right Doors / Sidepods (x=5..1215, y=1320..1635)
    draw_smooth_wave_box(im, (5, 1320, 1215, 1635), axis="h", cream_side="top", amp_frac=0.15, freq=1.5, ribbon_px=22)
    paste_center(im, word, 235, 1465, scale=0.42)
    paste_center(im, num_pill, 495, 1465, scale=0.74)
    paste_center(im, emblem, 855, 1465, scale=0.38)

    # Bottom Side Skirts (x=55..615 & 645..1215, y=1895..2042)
    draw_tangerine_wing_panel(im, (55, 1895, 615, 2042), "h", "top")
    draw_tangerine_wing_panel(im, (645, 1895, 1215, 2042), "h", "top")
    paste_center(im, est_c, 335, 1978, scale=0.95)
    paste_center(im, est_c, 930, 1978, scale=0.95)

    return im


# ==============================================================================
# 7. GT2 (Modern GT3 / GTE Supercar) — 2048x2048
# ==============================================================================
def build_gt2(emblem, word, est_c, est_d, num_pill) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    # Front Bumper & Splitter (cx=585, y=205..545)
    draw_smooth_wave_box(im, (110, 205, 1085, 545), axis="h", cream_side="top", amp_frac=0.14, ribbon_px=22)
    draw_center_heritage_ribbon(d, 585, 205, 545, half_tang=18, cream_gap=5)
    paste_center(im, word, 585, 435, scale=0.48)

    # Rear Wing Main Plane (x=110..655, y=565..675 & y=740..855)
    d.rectangle([110, 565, 655, 675], fill=CREAM)
    d.rectangle([110, 650, 655, 675], fill=TANGERINE)
    draw_tangerine_wing_panel(im, (110, 740, 655, 855), "h", "top")
    paste_center(im, word, 382, 612, angle=0, scale=0.48)
    paste_center(im, word, 382, 800, angle=180, scale=0.48)

    # Roof & Windshield Banner (x=1165..1755, y=15..550, rcx=1460)
    rcx = 1460
    d.polygon([(1265, 15), (1655, 15), (1755, 550), (1165, 550)], fill=ONYX)
    draw_center_heritage_ribbon(d, rcx, 15, 455, half_tang=20, cream_gap=6)
    paste_center(im, emblem, rcx, 255, angle=180, scale=0.38)
    # Windshield sunstrip banner
    d.rectangle([1175, 462, 1745, 550], fill=CREAM)
    d.rectangle([1175, 462, 1745, 476], fill=TANGERINE)
    paste_center(im, word, rcx, 508, angle=180, scale=0.38)

    # Front Hood / Bonnet (x=1255..1785, y=558..965, hcx=1520) — Porcelain Cream hood with full Orbital Emblem!
    hcx = 1520
    d.polygon([(1255, 558), (1785, 558), (1730, 965), (1310, 965)], fill=CREAM)
    draw_center_heritage_ribbon(d, hcx, 558, 965, half_tang=16, cream_gap=5)
    paste_center(im, emblem, hcx, 710, scale=0.38)
    paste_center(im, num_pill, hcx, 885, scale=0.66)

    # Front Fenders & Rear Quarters — Smooth flowing Cream-to-Onyx S-waves!
    draw_smooth_wave_box(im, (5, 895, 705, 1215), axis="h", cream_side="top", amp_frac=0.16, ribbon_px=20)
    draw_smooth_wave_box(im, (635, 1065, 1345, 1385), axis="h", cream_side="top", amp_frac=0.16, phase=2.9, ribbon_px=20)
    draw_smooth_wave_box(im, (5, 1345, 645, 1755), axis="h", cream_side="top", amp_frac=0.16, ribbon_px=20)
    draw_smooth_wave_box(im, (740, 1375, 1395, 1775), axis="h", cream_side="top", amp_frac=0.16, phase=2.9, ribbon_px=20)

    # Door Skins (x=615..1015 & 1315..1695, y=1690..2035)
    draw_smooth_wave_box(im, (615, 1690, 1015, 2035), axis="h", cream_side="top", amp_frac=0.14, ribbon_px=18)
    draw_smooth_wave_box(im, (1315, 1690, 1695, 2035), axis="h", cream_side="top", amp_frac=0.14, phase=3.1, ribbon_px=18)
    paste_center(im, num_pill, 815, 1825, angle=8, scale=0.76)
    paste_center(im, word, 815, 1945, angle=8, scale=0.36)
    paste_center(im, num_pill, 1505, 1825, angle=-8, scale=0.76)
    paste_center(im, word, 1505, 1945, angle=-8, scale=0.36)

    return im


# ==============================================================================
# 8. STOCK (NASCAR / V8 Supercar Top-Down Wrap) — 2048x2048
# ==============================================================================
def build_stock(emblem, word, est_c, est_d, num_stock) -> Image.Image:
    im = make_smooth_onyx_canvas(2048)
    d = ImageDraw.Draw(im)

    cx = 978  # Exact symmetry axis of Stock_UV.png

    # Porcelain Cream Center Spine (Front Bumper -> Hood -> Roof -> Decklid -> Rear Bumper)
    d.rectangle([680, 20, 1276, 2035], fill=CREAM)
    # Twin Retro '91 Tangerine + Onyx Heritage Center Stripes!
    for sign in (-1, 1):
        sx = cx + sign * 42
        d.rectangle([sx - 24, 20, sx + 24, 2035], fill=ONYX)
        d.rectangle([sx - 18, 20, sx + 18, 2035], fill=TANGERINE)

    # Windshield Header Banner (y=782..838, cleanly below cowl vents!)
    d.rectangle([715, 782, 1241, 838], fill=ONYX)
    paste_center(im, word, cx, 810, angle=180, scale=0.33)

    # Front Bumper Banner (180 deg at y=152)
    paste_center(im, word, cx, 150, angle=180, scale=0.44)

    # Hood: Huge Full 'swooz · est. 1991 ·' Orbital Emblem (facing front = 180 deg)!
    paste_center(im, emblem, cx, 445, angle=180, scale=0.66)

    # Roof: Giant Stock-Car '#91'
    paste_center(im, num_stock, cx, 1025, angle=-90, scale=1.42)

    # Rear Decklid & Rear Bumper (y=1565..2020)
    paste_center(im, emblem, cx, 1715, angle=0, scale=0.48)
    paste_center(im, est_d, cx, 1960, angle=0, scale=1.08)

    # Left Body Side (x=280..655, y=105..1925) & Right Body Side (x=1300..1675, y=105..1925)
    # Smooth vertical S-wave flowing Cream upper body into Onyx lower rocker with Tangerine wave!
    draw_smooth_wave_box(im, (280, 105, 655, 1925), axis="v", cream_side="right", amp_frac=0.14, freq=2.0, ribbon_px=22)
    draw_smooth_wave_box(im, (1300, 105, 1675, 1925), axis="v", cream_side="left", amp_frac=0.14, freq=2.0, phase=3.14, ribbon_px=22)

    # Left Door '#91' + Quarter Panel 'swooz' + Front Fender Star
    paste_center(im, num_stock, 505, 905, angle=-90, scale=1.35)
    paste_center(im, emblem, 505, 1515, angle=-90, scale=0.46)
    draw_puffy_star(im, 520, 355, 34, angle_deg=-90, fill=TANGERINE, rim=ONYX)

    # Right Door '#91' + Quarter Panel 'swooz' + Front Fender Star
    paste_center(im, num_stock, 1450, 905, angle=90, scale=1.35)
    paste_center(im, emblem, 1450, 1515, angle=90, scale=0.46)
    draw_puffy_star(im, 1435, 355, 34, angle_deg=90, fill=TANGERINE, rim=ONYX)

    # Rear Spoiler Blade (x=1715..1820, y=635..1480)
    draw_tangerine_wing_panel(im, (1715, 635, 1820, 1480), "v", "left")
    paste_center(im, word, 1768, 1060, angle=-90, scale=0.45)

    return im


# ==============================================================================
# 9. GT (Classic GT Car — 1024x1024, aligned to Italia/Raven reference islands)
# ==============================================================================
def build_gt(emblem, word, est_c, num_pill) -> Image.Image:
    # Porcelain Cream upper bodywork with smooth Tangerine + Onyx center heritage stripe & Onyx aero accents!
    im = Image.new("RGBA", (2048, 2048), CREAM)
    d = ImageDraw.Draw(im)

    # Lower quarter / underbody Onyx tone with Tangerine beltline
    draw_smooth_wave_box(im, (0, 1340, 2048, 2048), axis="h", cream_side="top", amp_frac=0.10, freq=2.0, ribbon_px=24)

    # Top-center Hood/Roof Heritage Ribbon (cx=1008, y=15..780)
    draw_center_heritage_ribbon(d, 1008, 15, 780, half_tang=30, cream_gap=8)

    # Top-right Rear Wing Main Blade (x=1585..1830, y=15..680)
    draw_tangerine_wing_panel(im, (1585, 15, 1830, 680), "v", "left")
    paste_center(im, word, 1718, 345, angle=-90, scale=0.72)

    # Left Front Bumper / Splitter Strip (x=78..148, y=785..1245)
    d.rectangle([78, 785, 148, 1245], fill=ONYX)
    paste_center(im, est_c, 113, 1015, angle=90, scale=0.95)

    # Center Hood / Nose Banner (x=605..820, y=1215..1290)
    d.rectangle([605, 1215, 820, 1290], fill=ONYX)
    paste_center(im, word, 712, 1252, scale=0.28)

    # Left & Right Door Number Plates + Cosmic Stars (verified from Italia #54 at (882, 1055) & (1092, 1055))
    paste_center(im, num_pill, 882, 1055, angle=-8, scale=0.76)
    paste_center(im, num_pill, 1092, 1055, angle=8, scale=0.76)
    draw_puffy_star(im, 720, 1080, 24, fill=TANGERINE, rim=ONYX)
    draw_puffy_star(im, 1255, 1080, 24, angle_deg=18, fill=TANGERINE, rim=ONYX)

    # Lower Door Sill 'swooz' Bubble Decals
    paste_center(im, word, 405, 1555, angle=-7, scale=0.31)
    paste_center(im, word, 750, 1565, angle=7, scale=0.31)

    # Upper-left Cowl Full Orbital Emblem (verified from Italia at (368, 225))
    paste_center(im, emblem, 368, 245, scale=0.34)

    return im.resize((1024, 1024), Image.Resampling.LANCZOS)


# ==============================================================================
# 10. TEAM ICON (256x256 Transparent RGBA Rounded Badge) & LIVERY.JSON
# ==============================================================================
def build_team_icon(emblem: Image.Image) -> Image.Image:
    ss = 2
    S = 256 * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # Smooth rounded squircle badge in #141414 Onyx with #F2EFE9 Cream + #FF601A Tangerine double border!
    pad = int(S * 0.05)
    rad = int(S * 0.22)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=rad, fill=ONYX, outline=CREAM, width=14)
    d.rounded_rectangle([pad + 16, pad + 16, S - pad - 16, S - pad - 16], radius=rad - 12, outline=TANGERINE, width=8)

    scale = (S * 0.78) / max(emblem.width, emblem.height)
    paste_center(im, emblem, S // 2, S // 2, scale=scale)
    return im.resize((256, 256), Image.Resampling.LANCZOS)


def main():
    for folder in [USER_LIVERY_DIR, LOCAL_BACKUP_DIR, VERIFY_DIR]:
        os.makedirs(folder, exist_ok=True)

    emblem, word, est_c, est_d = extract_swooz91_assets()
    num_pill = make_91_roundel("91", size=190, style="pill")
    num_circle = make_91_roundel("91", size=190, style="circle")
    num_stock = make_91_roundel("91", size=220, style="stock")

    builders = {
        "FormulaModern": lambda: build_formula_modern(emblem, word, est_c, est_d, num_pill),
        "Formula": lambda: build_formula(emblem, word, est_c, est_d, num_pill),
        "FormulaClassic": lambda: build_formula_classic(emblem, word, est_c, est_d, num_circle),
        "FormulaOldskool": lambda: build_formula_oldskool(emblem, word, est_c, est_d, num_circle),
        "FormulaLegacy": lambda: build_formula_legacy(emblem, word, est_c, est_d, num_circle),
        "Endurance": lambda: build_endurance(emblem, word, est_c, est_d, num_pill),
        "GT2": lambda: build_gt2(emblem, word, est_c, est_d, num_pill),
        "Stock": lambda: build_stock(emblem, word, est_c, est_d, num_stock),
        "GT": lambda: build_gt(emblem, word, est_c, num_pill),
    }

    rendered = {}
    for car_name, fn in builders.items():
        img = fn()
        rendered[car_name] = img
        for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
            img.save(os.path.join(out_dir, f"{car_name}.png"), "PNG", optimize=True)
        print(f"Saved {car_name}.png ({img.size[0]}x{img.size[1]} {img.mode})")

    icon = build_team_icon(emblem)
    for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
        icon.save(os.path.join(out_dir, "icon.png"), "PNG", optimize=True)
    print("Saved icon.png (256x256 RGBA)")

    livery_meta = {
        "formatVersion": 1,
        "teamName": "SWOOZ '91",
        "primaryColor": "#FF601A",
        "secondaryColor": "#F2EFE9",
        "floorColor": "#141414",
        "recolorIcon": False,
        "metallic": 0.16,
        "smoothness": 0.88,
        "driverNames": ["Dom_Swooz"],
        "workshopFileId": 0,
        "workshopAppId": 0,
        "authorSteamId": 76561198164654618,
        "authorName": "Dom_Swooz",
    }
    for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
        with open(os.path.join(out_dir, "livery.json"), "w", encoding="utf-8") as f:
            json.dump(livery_meta, f, indent=4)
    print("Saved livery.json")

    # Build 1) UV-Overlay Verification Sheet AND 2) Clean Showcase Sheet
    car_order = [
        "FormulaModern", "Formula", "FormulaClassic",
        "FormulaOldskool", "FormulaLegacy", "Endurance",
        "GT2", "Stock", "GT",
    ]
    verify_grid = Image.new("RGB", (3 * 820, 3 * 864), (14, 14, 16))
    clean_grid = Image.new("RGB", (3 * 820, 3 * 864), (14, 14, 16))
    vd = ImageDraw.Draw(verify_grid)
    cd = ImageDraw.Draw(clean_grid)
    label_font = load_round_font(24)

    for idx, car_name in enumerate(car_order):
        gx, gy = (idx % 3) * 820, (idx // 3) * 864
        tile_clean = rendered[car_name].resize((790, 790), Image.Resampling.LANCZOS)
        cd.rounded_rectangle([gx + 15, gy + 12, gx + 805, gy + 52], radius=8, fill=(22, 22, 25), outline=(255, 96, 26), width=2)
        cd.text((gx + 28, gy + 17), f"SWOOZ '91  •  {car_name}  •  #91 Wet-Gloss Heritage", font=label_font, fill=(242, 239, 233))
        clean_grid.paste(tile_clean.convert("RGB"), (gx + 15, gy + 58))

        tile_uv = tile_clean.copy()
        uv_path = os.path.join(UV_DIR, f"{car_name}_UV.png")
        if os.path.exists(uv_path):
            uv_im = Image.open(uv_path).convert("RGBA").resize((790, 790), Image.Resampling.NEAREST)
            tile_uv = Image.alpha_composite(tile_uv, uv_im)
        vd.rounded_rectangle([gx + 15, gy + 12, gx + 805, gy + 52], radius=8, fill=(22, 22, 25), outline=(255, 96, 26), width=2)
        vd.text((gx + 28, gy + 17), f"UV CHECK  •  {car_name}", font=label_font, fill=(255, 190, 80))
        verify_grid.paste(tile_uv.convert("RGB"), (gx + 15, gy + 58))

    verify_grid.save(os.path.join(VERIFY_DIR, "uv_check_swooz91_all9.png"), "PNG")
    clean_grid.save(SHOWCASE_PATH, "PNG", optimize=True)
    print("Saved verification & showcase grids!")


if __name__ == "__main__":
    main()

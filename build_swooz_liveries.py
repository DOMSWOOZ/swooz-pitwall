"""
SWOOZ Racing — Complete Custom Livery Suite Generator for Backseat Champions
Generates UV-accurate 2048x2048 (and 1024x1024 GT) liveries across all 9 car classes,
plus 256x256 RGBA team icon and livery.json, and installs to User Liveries.
"""
import json
import math
import os
import shutil
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageChops

LOGO_SRC = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\swooz_pit_wall_logo_v2_1795204288393.jpg"
SA_LIVERIES = r"D:\SteamLibrary\steamapps\common\Backseat Champions\BackseatChampions_Data\StreamingAssets\Liveries"
UV_DIR = os.path.join(SA_LIVERIES, "UV Templates")

USER_LIVERY_DIR = r"C:\Users\souls\AppData\LocalLow\f13rce\BackseatChampions\Liveries\user_SwoozRacing"
LOCAL_BACKUP_DIR = r"C:\Users\souls\.gemini\antigravity\scratch\backseat-pitwall\liveries\user_SwoozRacing"
VERIFY_DIR = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\scratch\uv_verify"
SHOWCASE_PATH = r"C:\Users\souls\.gemini\antigravity\brain\a9d3f03b-c705-45fc-84a2-f2bb84ca508c\swooz_livery_showcase.png"

# SWOOZ Motorsport Palette
CARBON_DARK = (11, 13, 18, 255)
CARBON_LIGHT = (20, 24, 33, 255)
CRIMSON = (225, 6, 0, 255)
CRIMSON_DEEP = (158, 4, 0, 255)
CRIMSON_BRIGHT = (250, 28, 16, 255)
PAPAYA = (255, 128, 0, 255)
AMBER = (255, 178, 24, 255)
WHITE = (246, 248, 252, 255)
SILVER = (195, 202, 214, 255)


def load_font(size: int, heavy: bool = True) -> ImageFont.FreeTypeFont:
    win_fonts = r"C:\Windows\Fonts"
    candidates = (
        ["arialbi.ttf", "segoeuiz.ttf", "impact.ttf", "arialbd.ttf", "bahnschrift.ttf"]
        if heavy
        else ["bahnschrift.ttf", "seguisb.ttf", "arialbd.ttf"]
    )
    for f in candidates:
        p = os.path.join(win_fonts, f)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def extract_swooz_crest() -> Image.Image:
    """Extract the glowing crimson/papaya 'S' speed-wing emblem with clean alpha."""
    src = Image.open(LOGO_SRC).convert("RGBA")
    # Crop strictly to the S-wing + shift lights (above 'SWOOZ' text which starts around y=565)
    crop = src.crop((170, 145, 855, 552))
    px = crop.load()
    w, h = crop.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    opx = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            lum = max(r, g, b)
            chroma = max(r, g, b) - min(r, g, b)
            score = max(lum - 24, chroma)
            if score <= 8:
                continue
            alpha = min(255, int(score * 2.35))
            # Un-premultiply dark background slightly so edges stay vivid crimson/papaya
            boost = 255.0 / max(90.0, alpha)
            nr = min(255, int(r * min(1.35, boost)))
            ng = min(255, int(g * min(1.25, boost)))
            nb = min(255, int(b * min(1.25, boost)))
            opx[x, y] = (nr, ng, nb, alpha)
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


def make_carbon_canvas(size: int = 2048) -> Image.Image:
    """Create a realistic 2x2 diagonal twill carbon-fiber weave base."""
    tile = Image.new("RGBA", (16, 16), CARBON_DARK)
    tpx = tile.load()
    for y in range(16):
        for x in range(16):
            diag = (x + y) % 8
            diag2 = (x - y) % 8
            if diag < 3:
                v = 22 if diag == 1 else 17
                tpx[x, y] = (v, v + 3, v + 9, 255)
            elif diag2 < 2:
                tpx[x, y] = (14, 17, 24, 255)
            else:
                tpx[x, y] = (9, 11, 16, 255)
    canvas = Image.new("RGBA", (size, size), CARBON_DARK)
    for y in range(0, size, 16):
        for x in range(0, size, 16):
            canvas.paste(tile, (x, y))
    return canvas


def make_wordmark(
    text: str,
    height: int = 90,
    fill=WHITE,
    accent_bar: bool = True,
    outline=(8, 10, 14, 235),
    italic_shear: float = 0.22,
) -> Image.Image:
    """Render supersampled motorsport wordmark with optional crimson/papaya speed underline."""
    ss = 2
    fnt = load_font(int(height * 0.84 * ss), heavy=True)
    dummy = Image.new("RGBA", (10, 10))
    d0 = ImageDraw.Draw(dummy)
    bb = d0.textbbox((0, 0), text, font=fnt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad = int(height * 0.45 * ss)
    w, h = tw + pad * 2 + int(th * abs(italic_shear)), th + pad * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    tx, ty = pad - bb[0], pad - bb[1]
    if outline:
        ow = max(2, int(height * 0.055 * ss))
        d.text((tx, ty), text, font=fnt, fill=outline, stroke_width=ow, stroke_fill=outline)
    d.text((tx, ty), text, font=fnt, fill=fill)
    if accent_bar:
        by = ty + bb[3] + int(height * 0.08 * ss)
        bh = max(4, int(height * 0.11 * ss))
        split = tx + int(tw * 0.64)
        d.polygon([(tx, by), (split, by), (split - bh, by + bh), (tx - bh, by + bh)], fill=CRIMSON_BRIGHT)
        d.polygon([(split + 6, by), (tx + tw, by), (tx + tw - bh, by + bh), (split + 6 - bh, by + bh)], fill=PAPAYA)
    # Apply slight motorsport forward slant if font wasn't already italic enough
    im = im.resize((w // ss, h // ss), Image.Resampling.LANCZOS)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def make_number_badge(num: str = "1", size: int = 160, style: str = "f1") -> Image.Image:
    """Render crisp motorsport driver number (#1) in F1 shield, WEC GT box, or Classic roundel."""
    ss = 2
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = S // 2, S // 2
    if style == "roundel":
        r = int(S * 0.44)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=PAPAYA, width=max(4, S // 26))
        fnt = load_font(int(S * 0.56), heavy=True)
        bb = d.textbbox((0, 0), num, font=fnt)
        d.text((cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2), num, font=fnt, fill=(12, 14, 18, 255))
    elif style == "gt_box":
        w2, h2 = int(S * 0.42), int(S * 0.44)
        d.rounded_rectangle([cx - w2, cy - h2, cx + w2, cy + h2], radius=S // 18, fill=(10, 12, 16, 245), outline=PAPAYA, width=max(5, S // 28))
        # Top banner 'SWOOZ GT'
        d.rectangle([cx - w2 + 4, cy - h2 + 4, cx + w2 - 4, cy - h2 + int(S * 0.18)], fill=CRIMSON)
        bfnt = load_font(int(S * 0.11), heavy=False)
        bbb = d.textbbox((0, 0), "SWOOZ", font=bfnt)
        d.text((cx - (bbb[0] + bbb[2]) // 2, cy - h2 + int(S * 0.035)), "SWOOZ", font=bfnt, fill=WHITE)
        fnt = load_font(int(S * 0.50), heavy=True)
        bb = d.textbbox((0, 0), num, font=fnt)
        d.text((cx - (bb[0] + bb[2]) // 2, cy + int(S * 0.06) - (bb[1] + bb[3]) // 2), num, font=fnt, fill=WHITE)
    elif style == "stock":
        fnt = load_font(int(S * 0.72), heavy=True)
        bb = d.textbbox((0, 0), num, font=fnt)
        tx, ty = cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2
        d.text((tx + S // 28, ty + S // 28), num, font=fnt, fill=PAPAYA)
        d.text((tx, ty), num, font=fnt, fill=WHITE, stroke_width=max(6, S // 24), stroke_fill=(10, 12, 16, 255))
    else:
        # Modern F1 angular number with papaya drop-highlight
        pts = [
            (cx - int(S * 0.36), cy - int(S * 0.40)),
            (cx + int(S * 0.40), cy - int(S * 0.40)),
            (cx + int(S * 0.30), cy + int(S * 0.40)),
            (cx - int(S * 0.42), cy + int(S * 0.40)),
        ]
        d.polygon(pts, fill=(10, 12, 18, 225), outline=PAPAYA)
        d.line([pts[0], pts[1]], fill=CRIMSON_BRIGHT, width=max(5, S // 26))
        d.line([pts[2], pts[3]], fill=PAPAYA, width=max(5, S // 26))
        fnt = load_font(int(S * 0.56), heavy=True)
        bb = d.textbbox((0, 0), num, font=fnt)
        tx, ty = cx - (bb[0] + bb[2]) // 2, cy - (bb[1] + bb[3]) // 2
        d.text((tx + 5, ty + 5), num, font=fnt, fill=PAPAYA)
        d.text((tx, ty), num, font=fnt, fill=WHITE)
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def paste_center(canvas: Image.Image, decal: Image.Image, cx: int, cy: int, angle: float = 0.0, scale: float = 1.0):
    """Paste an RGBA decal centered at (cx, cy) with optional scale and CCW rotation in degrees."""
    im = decal
    if abs(scale - 1.0) > 1e-3:
        nw = max(1, int(im.width * scale))
        nh = max(1, int(im.height * scale))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    if abs(angle) > 1e-2:
        im = im.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def draw_crimson_panel(draw: ImageDraw.ImageDraw, box, stripe_axis="h", papaya_edge="bottom"):
    """Fill a rectangular UV zone with rich SWOOZ crimson + papaya/white racing edge."""
    x0, y0, x1, y1 = box
    draw.rectangle([x0, y0, x1, y1], fill=CRIMSON)
    w, h = x1 - x0, y1 - y0
    if stripe_axis == "h":
        sh = max(6, int(h * 0.14))
        wh = max(3, int(h * 0.04))
        if papaya_edge == "bottom":
            draw.rectangle([x0, y1 - sh, x1, y1], fill=PAPAYA)
            draw.rectangle([x0, y1 - sh - wh - 3, x1, y1 - sh - 3], fill=WHITE)
        elif papaya_edge == "top":
            draw.rectangle([x0, y0, x1, y0 + sh], fill=PAPAYA)
            draw.rectangle([x0, y0 + sh + 3, x1, y0 + sh + 3 + wh], fill=WHITE)
        elif papaya_edge == "center":
            cy = (y0 + y1) // 2
            draw.rectangle([x0, cy - sh // 2, x1, cy + sh // 2], fill=PAPAYA)
            draw.rectangle([x0, cy - sh // 2 - wh - 3, x1, cy - sh // 2 - 3], fill=WHITE)
            draw.rectangle([x0, cy + sh // 2 + 3, x1, cy + sh // 2 + 3 + wh], fill=WHITE)
    else:
        sw = max(6, int(w * 0.14))
        ww = max(3, int(w * 0.04))
        if papaya_edge == "center":
            cx = (x0 + x1) // 2
            draw.rectangle([cx - sw // 2, y0, cx + sw // 2, y1], fill=PAPAYA)
            draw.rectangle([cx - sw // 2 - ww - 3, y0, cx - sw // 2 - 3, y1], fill=WHITE)
            draw.rectangle([cx + sw // 2 + 3, y0, cx + sw // 2 + 3 + ww, y1], fill=WHITE)
        elif papaya_edge == "left":
            draw.rectangle([x0, y0, x0 + sw, y1], fill=PAPAYA)
            draw.rectangle([x0 + sw + 3, y0, x0 + sw + 3 + ww, y1], fill=WHITE)
        elif papaya_edge == "right":
            draw.rectangle([x1 - sw, y0, x1, y1], fill=PAPAYA)
            draw.rectangle([x1 - sw - 3 - ww, y0, x1 - sw - 3, y1], fill=WHITE)


def draw_chevrons(draw: ImageDraw.ImageDraw, cx: int, y0: int, y1: int, half_w: int, direction: int = 1, count: int = 3):
    """Draw symmetric V-shaped papaya + white aero chevrons along a vertical centerline."""
    step = (y1 - y0) // max(1, count + 1)
    for i in range(count):
        yy = y0 + (i + 1) * step
        tip_y = yy + direction * int(half_w * 0.42)
        thick = max(10, int(half_w * 0.11))
        col = PAPAYA if i % 2 == 0 else WHITE
        pts = [
            (cx - half_w, yy),
            (cx, tip_y),
            (cx + half_w, yy),
            (cx + half_w, yy + thick),
            (cx, tip_y + thick),
            (cx - half_w, yy + thick),
        ]
        draw.polygon(pts, fill=col)


# ==============================================================================
# 1. FORMULA MODERN (2022-2026 Ground-Effect F1) — 2048x2048
# ==============================================================================
def build_formula_modern(crest, wm_swooz, wm_pitwall, wm_sub, num_f1) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top engine cover / sharkfin flanks (green pair: x=40..585 & 1320..1865, y=12..218)
    d.polygon([(40, 12), (585, 12), (575, 215), (40, 218)], fill=CRIMSON_DEEP)
    d.polygon([(1320, 12), (1865, 12), (1865, 218), (1330, 215)], fill=CRIMSON_DEEP)
    paste_center(im, crest, 405, 118, scale=0.22)
    paste_center(im, crest, 1435, 118, scale=0.22)

    # Cockpit Collar / Headrest (white centerline island: x=850..1055, y=185..395, cx=952)
    d.rectangle([850, 185, 1055, 395], fill=CRIMSON)
    d.rectangle([936, 185, 968, 395], fill=PAPAYA)
    paste_center(im, crest, 952, 310, scale=0.15)

    # Left & Right Main Sidepods + Engine Cover (red mirrored pair: x=25..935 & 970..1885, y=222..565)
    d.polygon([(25, 222), (935, 222), (935, 495), (25, 455)], fill=CRIMSON)
    d.polygon([(25, 445), (935, 485), (935, 525), (25, 485)], fill=PAPAYA)
    d.polygon([(25, 488), (935, 528), (935, 540), (25, 500)], fill=WHITE)

    d.polygon([(1885, 222), (970, 222), (970, 495), (1885, 455)], fill=CRIMSON)
    d.polygon([(1885, 445), (970, 485), (970, 525), (1885, 475)], fill=PAPAYA)
    d.polygon([(1885, 488), (970, 528), (970, 540), (1885, 500)], fill=WHITE)

    paste_center(im, wm_swooz, 405, 315, scale=1.02)
    paste_center(im, wm_swooz, 1435, 315, scale=1.02)
    paste_center(im, wm_pitwall, 665, 425, scale=0.68)
    paste_center(im, wm_pitwall, 1240, 425, scale=0.68)

    # Halo (x=15..555, y=555..1060, yellow island) -> Crimson halo with papaya center apex flash
    d.polygon([(15, 735), (555, 555), (555, 675), (260, 810), (555, 945), (555, 1060), (15, 880)], fill=CRIMSON)
    d.polygon([(15, 790), (235, 790), (265, 810), (235, 830), (15, 830)], fill=PAPAYA)
    paste_center(im, wm_swooz, 145, 810, scale=0.44)

    # Actual F1 Nosecone (white centerline island on left: x=10..230, y=885..1335, cx=118, 180-deg front-facing!)
    ncx = 118
    d.polygon([(12, 885), (224, 885), (196, 1335), (40, 1335)], fill=CRIMSON)
    d.rectangle([ncx - 16, 885, ncx + 16, 1335], fill=PAPAYA)
    d.rectangle([ncx - 24, 885, ncx - 19, 1335], fill=WHITE)
    d.rectangle([ncx + 19, 885, ncx + 24, 1335], fill=WHITE)
    paste_center(im, wm_swooz, ncx, 935, angle=180, scale=0.52)
    paste_center(im, num_f1, ncx, 1065, angle=180, scale=0.66)
    paste_center(im, crest, ncx, 1215, angle=180, scale=0.17)

    # Rear Wing Main Plane & DRS Flap (x=512..872, y=605..740 [180 deg] & y=750..905 [0 deg])
    draw_crimson_panel(d, (512, 605, 872, 740), "h", "top")
    draw_crimson_panel(d, (512, 748, 872, 905), "h", "bottom")
    paste_center(im, wm_swooz, 692, 675, angle=180, scale=0.82)
    paste_center(im, wm_swooz, 692, 815, angle=0, scale=0.86)

    # Sidepod Upper Louvers / Shoulders (red mirrored pair: x=250..650, y=1090..1345 & x=670..1075, y=995..1260)
    d.polygon([(250, 1090), (650, 1090), (650, 1320), (250, 1345)], fill=CRIMSON)
    d.polygon([(250, 1275), (650, 1245), (650, 1280), (250, 1310)], fill=PAPAYA)
    d.polygon([(1075, 1005), (670, 1005), (670, 1235), (1075, 1260)], fill=CRIMSON)
    d.polygon([(1075, 1190), (670, 1160), (670, 1195), (1075, 1225)], fill=PAPAYA)

    # Engine Cover / Cowl Shield on Right (white centerline island: x=1375..1718, y=785..1115, cx=1546)
    scx = 1546
    d.polygon([(scx, 780), (1720, 1045), (1546, 1120), (1372, 1045)], fill=CRIMSON)
    d.rectangle([scx - 16, 785, scx + 16, 1115], fill=PAPAYA)
    paste_center(im, crest, scx, 925, angle=180, scale=0.19)
    paste_center(im, wm_swooz, scx, 1020, angle=180, scale=0.52)

    # Front Wing Stacked Elements (x=955..1535, y=1325..1695, centerline x=1245)
    d.rectangle([955, 1325, 1535, 1695], fill=CRIMSON_DEEP)
    d.rectangle([955, 1490, 1535, 1565], fill=PAPAYA)
    d.rectangle([955, 1572, 1535, 1586], fill=WHITE)
    d.rectangle([955, 1325, 1040, 1695], fill=PAPAYA)
    d.rectangle([1450, 1325, 1535, 1695], fill=PAPAYA)

    # Front/Rear Wing Endplates at bottom-left (x=80..410 & 490..815, y=1850..1945)
    d.rectangle([80, 1850, 410, 1945], fill=CRIMSON)
    d.rectangle([490, 1850, 815, 1945], fill=CRIMSON)
    d.rectangle([80, 1922, 410, 1945], fill=PAPAYA)
    d.rectangle([490, 1922, 815, 1945], fill=PAPAYA)
    paste_center(im, wm_swooz, 245, 1895, angle=-14, scale=0.50)
    paste_center(im, wm_swooz, 650, 1895, angle=14, scale=0.50)

    # Right-column rectangular wing flap plates (x=1758..1932, y=720..1340)
    draw_crimson_panel(d, (1758, 720, 1932, 1340), "v", "left")

    return im


# ==============================================================================
# 2. FORMULA (2018-2021 Hybrid Wide-Track F1) — 2048x2048
# ==============================================================================
def build_formula(crest, wm_swooz, wm_pitwall, wm_sub, num_f1) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top Cyan Wing Planes (x=5..720 & 735..1445, y=5..200)
    draw_crimson_panel(d, (5, 5, 720, 200), "h", "bottom")
    draw_crimson_panel(d, (735, 5, 1445, 200), "h", "bottom")

    # Engine Cover / Sharkfin Triangles (cyan pair: x=5..458 & 475..935, y=200..515, centerline x=466)
    d.polygon([(5, 430), (455, 200), (455, 510), (5, 510)], fill=CRIMSON)
    d.polygon([(5, 470), (455, 295), (455, 335), (5, 505)], fill=PAPAYA)
    d.polygon([(5, 460), (455, 285), (455, 293), (5, 468)], fill=WHITE)

    d.polygon([(930, 430), (475, 200), (475, 510), (930, 510)], fill=CRIMSON)
    d.polygon([(930, 470), (475, 295), (475, 335), (930, 505)], fill=PAPAYA)
    d.polygon([(930, 460), (475, 285), (475, 293), (930, 468)], fill=WHITE)

    # Rear Wing Main Planes (white centerline stacks: x=8..425, y=530..855)
    draw_crimson_panel(d, (8, 532, 425, 608), "h", "bottom")
    draw_crimson_panel(d, (8, 612, 425, 688), "h", "top")
    draw_crimson_panel(d, (8, 694, 425, 855), "h", "bottom")
    paste_center(im, wm_swooz, 216, 568, angle=0, scale=0.68)
    paste_center(im, wm_swooz, 216, 650, angle=180, scale=0.68)
    paste_center(im, wm_swooz, 216, 755, angle=0, scale=0.82)
    paste_center(im, wm_pitwall, 216, 815, angle=0, scale=0.58)

    # Nosecone & Front Bulkhead (white centerline island: x=30..405, y=990..1775, tip at bottom x=216, y=1765)
    d.polygon([(35, 990), (398, 990), (355, 1775), (78, 1775)], fill=CRIMSON)
    d.rectangle([196, 990, 236, 1775], fill=PAPAYA)
    d.rectangle([186, 990, 192, 1775], fill=WHITE)
    d.rectangle([240, 990, 246, 1775], fill=WHITE)
    paste_center(im, wm_pitwall, 196, 1045, scale=0.48)
    paste_center(im, crest, 196, 1205, scale=0.19)
    paste_center(im, num_f1, 196, 1455, scale=0.68)
    paste_center(im, wm_swooz, 196, 1650, scale=0.38)

    # Central Sidepod / Monocoque Top Deck (x=405..968, y=1020..1330)
    draw_crimson_panel(d, (405, 1020, 968, 1330), "h", "bottom")
    paste_center(im, wm_swooz, 686, 1135, scale=1.18)
    paste_center(im, wm_pitwall, 686, 1225, scale=0.75)

    # Lower Sidepod Flanks (magenta pair: x=275..1115, y=1285..1935)
    d.polygon([(295, 1435), (1095, 1285), (1115, 1580), (295, 1620)], fill=CRIMSON)
    d.polygon([(295, 1575), (1095, 1495), (1095, 1535), (295, 1605)], fill=PAPAYA)
    d.polygon([(275, 1615), (1100, 1745), (1100, 1935), (275, 1895)], fill=CRIMSON)
    d.polygon([(275, 1775), (1100, 1845), (1100, 1885), (275, 1815)], fill=PAPAYA)

    # Vertical Side / Floor Edge Strips (orange-red pair: x=1380..1710, y=275..1480)
    draw_crimson_panel(d, (1455, 275, 1705, 945), "v", "left")
    draw_crimson_panel(d, (1370, 785, 1585, 1480), "v", "right")
    paste_center(im, wm_swooz, 1565, 515, angle=-78, scale=0.68)
    paste_center(im, wm_swooz, 1465, 1135, angle=78, scale=0.68)

    # Right-edge fin/endplate triangles (x=1825..2040, y=5..1875)
    draw_crimson_panel(d, (1825, 5, 2040, 1875), "v", "left")

    # Engine cover / sharkfin crests + SWOOZ
    paste_center(im, crest, 315, 350, scale=0.22)
    paste_center(im, wm_swooz, 315, 445, scale=0.72)
    paste_center(im, crest, 615, 350, scale=0.22)
    paste_center(im, wm_swooz, 615, 445, scale=0.72)

    # Top-right green endplate pair (x=1460..1805, y=5..265)
    draw_crimson_panel(d, (1460, 5, 1628, 265), "h", "bottom")
    draw_crimson_panel(d, (1636, 5, 1805, 265), "h", "bottom")
    paste_center(im, crest, 1544, 115, scale=0.16)
    paste_center(im, crest, 1720, 115, scale=0.16)

    return im


# ==============================================================================
# 3. FORMULA CLASSIC (Late-1990s / V10 Era F1) — 2048x2048
# ==============================================================================
def build_formula_classic(crest, wm_swooz, wm_pitwall, wm_sub, num_f1) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top-left Rear Wing Endplates (orange pair x=25..342, blue pair x=355..662, y=10..430)
    draw_crimson_panel(d, (25, 10, 180, 430), "h", "bottom")
    draw_crimson_panel(d, (188, 10, 342, 430), "h", "bottom")
    paste_center(im, crest, 102, 175, scale=0.16)
    paste_center(im, wm_swooz, 102, 265, scale=0.45)
    paste_center(im, crest, 265, 175, scale=0.16)
    paste_center(im, wm_swooz, 265, 265, scale=0.45)

    # Top horizontal wing strip (x=675..1245, y=8..82)
    draw_crimson_panel(d, (675, 8, 1245, 82), "h", "top")
    paste_center(im, wm_swooz, 960, 46, angle=180, scale=0.62)

    # Upper Monocoque / Sidepod Flanks (blue horizontal mirrored pair: x=30..1400, y=450..895, centerline y=672)
    d.rectangle([30, 450, 1400, 895], fill=CRIMSON_DEEP)
    d.rectangle([30, 565, 1400, 780], fill=CRIMSON)
    d.rectangle([30, 648, 1400, 696], fill=PAPAYA)
    d.rectangle([30, 636, 1400, 643], fill=WHITE)
    d.rectangle([30, 701, 1400, 708], fill=WHITE)

    # Vertical sleek side/floor cowling on upper-right (lime green pair: x=1385..2035, y=15..1200)
    # Wait: x=1655..1995 has the vertical wing planes! Let's keep 1390..1645 dark carbon + crimson inner strip,
    # and paint the Front/Rear Wing Vertical Blades cleanly at x=1655..1995!
    d.polygon([(1565, 20), (1645, 20), (1645, 1180), (1565, 1180)], fill=CRIMSON)
    draw_crimson_panel(d, (1658, 10, 1818, 585), "v", "right")
    draw_crimson_panel(d, (1828, 10, 2035, 585), "v", "left")
    draw_crimson_panel(d, (1630, 600, 1755, 1165), "v", "right")
    paste_center(im, wm_swooz, 1735, 295, angle=90, scale=1.05)
    paste_center(im, wm_swooz, 1692, 880, angle=-90, scale=0.95)
    paste_center(im, wm_pitwall, 1915, 295, angle=82, scale=0.72)

    # Main V10 Chassis / Sidepods / Nosecone (magenta pair + white nosecone: x=10..2038, y=910..2035)
    # Horizontal centerline is strictly y = 1472..1500! Nose tip is at (2030, 1488) pointing RIGHT!
    cy = 1488
    d.polygon([(10, 915), (860, 915), (1755, 1285), (2038, 1410), (2038, 1566), (1755, 1690), (860, 2035), (10, 2035)], fill=CRIMSON)
    # Bold Papaya + White V10 centerline arrow stripe converging all the way to the nose tip (2035, 1488)!
    d.polygon([(380, cy - 58), (2038, cy - 28), (2038, cy + 28), (380, cy + 58)], fill=PAPAYA)
    d.polygon([(380, cy - 72), (2038, cy - 38), (2038, cy - 31), (380, cy - 63)], fill=WHITE)
    d.polygon([(380, cy + 63), (2038, cy + 31), (2038, cy + 38), (380, cy + 72)], fill=WHITE)

    # Exposed carbon aero bargeboard / sidepod undercut scallops along outer top & bottom edges
    d.polygon([(10, 915), (840, 915), (650, 1065), (10, 1190)], fill=CARBON_DARK)
    d.polygon([(10, 2035), (840, 2035), (650, 1885), (10, 1760)], fill=CARBON_DARK)

    # Sidepod 'SWOOZ' wordmarks — upright on top sidepod (y~1170), mirrored 180 deg on bottom sidepod (y~1800)
    paste_center(im, wm_swooz, 725, 1165, angle=-8, scale=0.96)
    paste_center(im, wm_swooz, 725, 1810, angle=188, scale=0.96)

    # Engine cover crests near rear (x=315, y=1260 and x=315, y=1715)
    paste_center(im, crest, 285, 1345, angle=0, scale=0.22)
    paste_center(im, crest, 285, 1630, angle=180, scale=0.22)

    # Nosecone #1 roundel & crest (nose tip is at x=2030, y=1488 -> reading from front, top of nose faces left!)
    # Check ApexRacecars FormulaClassic: 'Dense' at x=1560, y=1488 is upright horizontally, and #1 roundel rotated -90 deg faces front!
    paste_center(im, num_f1, 1845, cy, angle=-90, scale=0.64)
    paste_center(im, crest, 1655, cy, angle=-90, scale=0.19)

    return im


# ==============================================================================
# 4. FORMULA OLDSKOOL (Late-1980s MP4/4 Turbo Era F1) — 2048x2048
# ==============================================================================
def build_formula_oldskool(crest, wm_swooz, wm_pitwall, wm_sub, num_roundel) -> Image.Image:
    # Classic 80s turbo F1 iconic two-tone: crisp Titanium-White + FIA Crimson + Papaya speed-band on Carbon!
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top-left Rear Wing Main Plane (x=10..395, y=30..315, white centerline)
    draw_crimson_panel(d, (10, 30, 395, 168), "h", "bottom")
    draw_crimson_panel(d, (10, 174, 395, 315), "h", "top")
    paste_center(im, wm_swooz, 202, 96, angle=0, scale=0.82)
    paste_center(im, wm_swooz, 202, 245, angle=180, scale=0.82)

    # Upper Cockpit Surround / Monocoque Shoulders (orange vertical pair: x=1005..1670 at top, narrowing to x=1130..1555 below y=220!)
    d.polygon([(1005, 5), (1670, 5), (1555, 280), (1555, 880), (1130, 880), (1130, 280)], fill=CRIMSON)
    # Classic MP4/4 white + papaya inner chevron collar along x=1342
    d.polygon([(1219, 200), (1342, 330), (1465, 200), (1465, 880), (1219, 880)], fill=WHITE)
    d.polygon([(1249, 250), (1342, 355), (1435, 250), (1435, 880), (1249, 880)], fill=CRIMSON_BRIGHT)
    d.rectangle([1328, 340, 1356, 880], fill=PAPAYA)

    # Upper Wing / Flap Boxes (x=485..1098, y=375..495 — drawn after cockpit collar so zero overlap!)
    draw_crimson_panel(d, (485, 375, 785, 495), "h", "bottom")
    draw_crimson_panel(d, (798, 375, 1098, 495), "h", "bottom")
    paste_center(im, wm_swooz, 635, 430, scale=0.65)
    paste_center(im, wm_swooz, 948, 430, scale=0.65)

    # Mid-left Twin Horizontal Wing / Side Plates (red pair: x=18..525 & 540..1045, y=625..798)
    draw_crimson_panel(d, (18, 625, 525, 798), "h", "bottom")
    draw_crimson_panel(d, (540, 625, 1045, 798), "h", "bottom")
    paste_center(im, wm_swooz, 272, 705, scale=0.95)
    paste_center(im, wm_swooz, 792, 705, scale=0.95)

    # Left & Right Sidepods / Engine Cover (cyan stacked pair: y=815..1142 & y=1148..1475, x=10..1045)
    for y_top, y_bot, nose_right in [(815, 1142, False), (1148, 1475, True)]:
        d.rectangle([10, y_top, 1045, y_bot], fill=CRIMSON)
        d.rectangle([10, y_bot - 95, 1045, y_bot], fill=CARBON_LIGHT)
        d.rectangle([10, y_bot - 118, 1045, y_bot - 92], fill=PAPAYA)
        d.rectangle([10, y_bot - 128, 1045, y_bot - 121], fill=WHITE)
        wx = 415 if not nose_right else 475
        paste_center(im, wm_swooz, wx, y_top + 115, scale=1.02)
        paste_center(im, crest, wx + (240 if not nose_right else -240), y_top + 110, scale=0.20)
        paste_center(im, wm_pitwall, wx, y_bot - 48, scale=0.62)

    # V-Shaped Nosecone / Front Cowl (white symmetric island: x=1035..1655, y=940..1605, exact nose tip cx=1342, y=1595!)
    cx = 1342
    d.polygon([(1035, 940), (1655, 940), (1655, 1280), (cx, 1610), (1035, 1280)], fill=CRIMSON)
    d.polygon([(1120, 940), (cx, 1210), (1565, 940), (1595, 940), (cx, 1255), (1090, 940)], fill=WHITE)
    d.polygon([(1155, 940), (cx, 1175), (1530, 940), (1560, 940), (cx, 1215), (1125, 940)], fill=PAPAYA)
    paste_center(im, crest, cx, 1135, scale=0.18)
    paste_center(im, wm_swooz, cx, 1265, scale=0.62)
    paste_center(im, num_roundel, cx, 1405, scale=0.68)

    # Lower Rear Wing Endplates (red pair at bottom: x=455..735 & 740..1010, y=1810..2042)
    draw_crimson_panel(d, (455, 1810, 732, 2042), "h", "top")
    draw_crimson_panel(d, (740, 1810, 1015, 2042), "h", "top")
    paste_center(im, num_roundel, 535, 1955, angle=-90, scale=0.45)
    paste_center(im, num_roundel, 935, 1955, angle=90, scale=0.45)
    paste_center(im, wm_swooz, 655, 1935, angle=90, scale=0.46)
    paste_center(im, wm_swooz, 815, 1935, angle=-90, scale=0.46)

    return im


# ==============================================================================
# 5. FORMULA LEGACY (1960s Classic Cigar GP Car) — 2048x2048
# ==============================================================================
def build_formula_legacy(crest, wm_swooz, wm_pitwall, wm_sub, num_roundel) -> Image.Image:
    # Classic 1960s Grand Prix Works Crimson with Twin Papaya + Titanium White Heritage Stripes & Roundels!
    im = Image.new("RGBA", (2048, 2048), CRIMSON)
    d = ImageDraw.Draw(im)

    # Subtle rich crimson shading outside main hull
    d.rectangle([0, 1150, 2048, 2048], fill=CRIMSON_DEEP)

    # 1. Front Nosecone & Radiator Mouth (white centerline island: x=15..615, y=10..550, centerline x=336)
    d.rectangle([310, 10, 362, 550], fill=PAPAYA)
    d.rectangle([296, 10, 305, 550], fill=WHITE)
    d.rectangle([367, 10, 376, 550], fill=WHITE)

    # 2. Lower Cigar Nose / Underbody Hull (white centerline V-island: x=15..670, y=550..955, centerline x=395)
    d.rectangle([368, 550, 422, 955], fill=PAPAYA)
    d.rectangle([354, 550, 363, 955], fill=WHITE)
    d.rectangle([427, 550, 436, 955], fill=WHITE)
    paste_center(im, num_roundel, 395, 765, scale=0.84)
    paste_center(im, wm_swooz, 395, 890, scale=0.54)

    # 3. Upper Cockpit / Fuselage (white centerline island: x=615..1560, y=10..435, horizontal centerline y=218)
    d.rectangle([615, 192, 1560, 244], fill=PAPAYA)
    d.rectangle([615, 178, 1560, 187], fill=WHITE)
    d.rectangle([615, 249, 1560, 258], fill=WHITE)
    paste_center(im, wm_swooz, 1085, 98, angle=0, scale=0.72)
    paste_center(im, wm_swooz, 1085, 338, angle=180, scale=0.72)
    paste_center(im, crest, 1345, 218, angle=-90, scale=0.18)

    # 4. Rear Engine Cover & Flank Panels (white x=665..895, y=605..945 [cx=780] + magenta pair x=1058..1424, y=645..900)
    d.rectangle([758, 605, 802, 945], fill=PAPAYA)
    d.rectangle([746, 605, 754, 945], fill=WHITE)
    d.rectangle([806, 605, 814, 945], fill=WHITE)
    paste_center(im, num_roundel, 780, 775, scale=0.74)

    # Magenta mirrored flank plates (x=1058..1238 and x=1242..1422, y=645..900)
    draw_crimson_panel(d, (1058, 645, 1238, 900), "h", "bottom")
    draw_crimson_panel(d, (1244, 645, 1424, 900), "h", "bottom")
    paste_center(im, num_roundel, 1148, 745, scale=0.58)
    paste_center(im, wm_swooz, 1148, 835, scale=0.38)
    paste_center(im, num_roundel, 1334, 745, scale=0.58)
    paste_center(im, wm_swooz, 1334, 835, scale=0.38)

    # 5. Top-Right Fin / Wing Plates (green pair: x=1490..1692 & 1698..1900, y=5..278)
    draw_crimson_panel(d, (1490, 5, 1692, 278), "h", "bottom")
    draw_crimson_panel(d, (1698, 5, 1900, 278), "h", "bottom")
    paste_center(im, crest, 1591, 125, scale=0.18)
    paste_center(im, crest, 1799, 125, scale=0.18)

    return im


# ==============================================================================
# 6. ENDURANCE (Le Mans Hypercar / LMDh Prototype) — 2048x2048
# ==============================================================================
def build_endurance(crest, wm_swooz, wm_pitwall, wm_sub, num_gt) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Top Rear Wing Main Plane (x=115..585, y=5..105, white centerline around x=350)
    draw_crimson_panel(d, (115, 5, 585, 105), "h", "bottom")
    paste_center(im, wm_swooz, 350, 48, scale=0.82)

    # Front Nose / Cowl / Fenders Stack (white centerline islands along exact cx=525, y=215..1295!)
    cx = 525
    d.polygon([(140, 360), (910, 360), (1015, 1290), (25, 1290)], fill=CRIMSON)
    d.rectangle([cx - 22, 220, cx + 22, 1290], fill=PAPAYA)
    d.rectangle([cx - 34, 220, cx - 27, 1290], fill=WHITE)
    d.rectangle([cx + 27, 220, cx + 34, 1290], fill=WHITE)
    draw_chevrons(d, cx, 940, 1220, 240, direction=-1, count=2)
    paste_center(im, wm_pitwall, cx, 535, scale=0.58)
    paste_center(im, crest, cx, 755, scale=0.22)
    paste_center(im, num_gt, cx, 935, scale=0.78)
    paste_center(im, wm_swooz, cx, 1115, scale=0.85)

    # Upper-right Fender Louvers / Side Arches (purple/green islands: x=1040..2030, y=365..705)
    d.polygon([(1085, 530), (1595, 530), (1540, 695), (1085, 695)], fill=CRIMSON)
    d.polygon([(1535, 445), (2035, 445), (2035, 610), (1535, 610)], fill=CRIMSON)
    d.rectangle([1085, 655, 1555, 685], fill=PAPAYA)
    d.rectangle([1535, 570, 2035, 600], fill=PAPAYA)

    # Rear Engine Deck / Butterfly Cowling (lime symmetric island: x=1115..1875, y=855..1425, centerline x=1505)
    rcx = 1505
    d.polygon([(1115, 865), (1895, 865), (1795, 1425), (1215, 1425)], fill=CRIMSON)
    d.rectangle([rcx - 24, 865, rcx + 24, 1425], fill=PAPAYA)
    d.rectangle([rcx - 36, 865, rcx - 29, 1425], fill=WHITE)
    d.rectangle([rcx + 29, 865, rcx + 36, 1425], fill=WHITE)
    draw_chevrons(d, rcx, 960, 1340, 260, direction=1, count=3)

    # Sharkfin (top-right cyan x=1895..2042, y=5..405 & right-edge red pair x=1875..2042, y=840..1825)
    draw_crimson_panel(d, (1895, 5, 2042, 405), "v", "left")
    draw_crimson_panel(d, (1875, 840, 2042, 1825), "v", "left")
    paste_center(im, wm_swooz, 1968, 185, angle=-90, scale=0.65)
    paste_center(im, wm_swooz, 1962, 1110, angle=-90, scale=0.68)
    paste_center(im, wm_swooz, 1962, 1560, angle=90, scale=0.68)

    # Left & Right Sidepods / Doors (x=5..1215, y=1300..1635 & bottom rocker panels y=1895..2042)
    d.polygon([(5, 1320), (1215, 1320), (1020, 1635), (5, 1635)], fill=CRIMSON)
    d.rectangle([5, 1555, 1080, 1595], fill=PAPAYA)
    d.rectangle([5, 1542, 1080, 1549], fill=WHITE)
    paste_center(im, wm_swooz, 235, 1475, scale=0.72)
    paste_center(im, num_gt, 455, 1475, scale=0.72)
    paste_center(im, wm_swooz, 845, 1475, scale=0.72)

    # Bottom magenta side skirts / pods (x=55..615 & 645..1215, y=1895..2042)
    draw_crimson_panel(d, (55, 1895, 615, 2042), "h", "top")
    draw_crimson_panel(d, (645, 1895, 1215, 2042), "h", "top")
    paste_center(im, wm_pitwall, 335, 1975, scale=0.68)
    paste_center(im, wm_pitwall, 930, 1975, scale=0.68)

    return im


# ==============================================================================
# 7. GT2 (Modern GT3 / GTE Supercar) — 2048x2048
# ==============================================================================
def build_gt2(crest, wm_swooz, wm_pitwall, wm_sub, num_gt) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    # Front Bumper & Aero Flics (white centerline around x=585, y=205..545)
    d.rectangle([110, 205, 1085, 545], fill=CRIMSON)
    d.rectangle([563, 205, 607, 545], fill=PAPAYA)
    d.rectangle([110, 485, 1085, 525], fill=PAPAYA)
    paste_center(im, wm_swooz, 585, 435, scale=0.85)

    # Rear Wing Main Plane (white centerline x=110..655: y=565..670 [0 deg] & y=745..855 [180 deg])
    draw_crimson_panel(d, (110, 565, 655, 675), "h", "bottom")
    draw_crimson_panel(d, (110, 740, 655, 855), "h", "top")
    paste_center(im, wm_swooz, 382, 616, angle=0, scale=0.88)
    paste_center(im, wm_swooz, 382, 798, angle=180, scale=0.88)

    # Roof & Windshield Banner (x=1165..1755, y=15..555, white centerline around x=1460)
    rcx = 1460
    d.polygon([(1265, 15), (1655, 15), (1755, 550), (1165, 550)], fill=CRIMSON_DEEP)
    d.rectangle([rcx - 26, 15, rcx + 26, 550], fill=PAPAYA)
    d.rectangle([rcx - 38, 15, rcx - 31, 550], fill=WHITE)
    d.rectangle([rcx + 31, 15, rcx + 38, 550], fill=WHITE)
    paste_center(im, wm_swooz, rcx, 495, angle=180, scale=0.68)

    # Front Hood / Bonnet (x=1255..1790, y=558..965, white centerline around x=1520!)
    hcx = 1520
    d.polygon([(1255, 558), (1785, 558), (1730, 965), (1310, 965)], fill=CRIMSON)
    d.rectangle([hcx - 24, 558, hcx + 24, 965], fill=PAPAYA)
    d.rectangle([hcx - 36, 558, hcx - 29, 965], fill=WHITE)
    d.rectangle([hcx + 29, 558, hcx + 36, 965], fill=WHITE)
    paste_center(im, crest, hcx, 665, scale=0.21)
    paste_center(im, num_gt, hcx, 795, scale=0.72)
    paste_center(im, wm_swooz, hcx, 905, scale=0.62)

    # Left & Right Front Fenders / Doors (red pair: x=5..705, y=895..1225 & x=630..1345, y=1055..1390)
    d.polygon([(5, 995), (695, 895), (705, 1215), (5, 1215)], fill=CRIMSON)
    d.polygon([(5, 1140), (700, 1085), (700, 1125), (5, 1180)], fill=PAPAYA)
    d.polygon([(635, 1280), (960, 1065), (1345, 1065), (1345, 1385), (635, 1355)], fill=CRIMSON)
    d.polygon([(635, 1310), (1345, 1245), (1345, 1285), (635, 1350)], fill=PAPAYA)

    # Left & Right Rear Quarter Panels / Doors (blue pair: x=5..645, y=1345..1755 & x=735..1395, y=1375..1775)
    d.polygon([(5, 1630), (415, 1345), (645, 1585), (530, 1755), (5, 1735)], fill=CRIMSON)
    d.polygon([(5, 1675), (585, 1565), (595, 1605), (5, 1715)], fill=PAPAYA)
    d.polygon([(740, 1495), (1285, 1375), (1395, 1525), (1155, 1775), (740, 1665)], fill=CRIMSON)
    d.polygon([(740, 1565), (1345, 1465), (1355, 1505), (740, 1605)], fill=PAPAYA)

    # Bottom Deck / Door Skins (lime pair: x=615..1015 & 1315..1695, y=1690..2035)
    draw_crimson_panel(d, (615, 1690, 1015, 2035), "h", "bottom")
    draw_crimson_panel(d, (1315, 1690, 1695, 2035), "h", "bottom")
    paste_center(im, num_gt, 815, 1825, angle=8, scale=0.78)
    paste_center(im, wm_swooz, 815, 1935, angle=8, scale=0.62)
    paste_center(im, num_gt, 1505, 1825, angle=-8, scale=0.78)
    paste_center(im, wm_swooz, 1505, 1935, angle=-8, scale=0.62)

    return im


# ==============================================================================
# 8. STOCK (NASCAR / V8 Supercar Top-Down Wrap) — 2048x2048
# ==============================================================================
def build_stock(crest, wm_swooz, wm_pitwall, wm_sub, num_stock) -> Image.Image:
    im = make_carbon_canvas(2048)
    d = ImageDraw.Draw(im)

    cx = 978  # Exact 1-pixel symmetry axis of Stock_UV.png!

    # Center Body Spine: Front Bumper (y=20..210) -> Hood (210..685) -> Roof (790..1265) -> Decklid (1550..1885) -> Rear Bumper (1890..2035)
    d.rectangle([680, 20, 1276, 2035], fill=CRIMSON)
    # Bold American Stock-Car Twin Papaya + White Center Racing Stripes!
    d.rectangle([cx - 58, 20, cx - 14, 2035], fill=PAPAYA)
    d.rectangle([cx + 14, 20, cx + 58, 2035], fill=PAPAYA)
    d.rectangle([cx - 70, 20, cx - 63, 2035], fill=WHITE)
    d.rectangle([cx + 63, 20, cx + 70, 2035], fill=WHITE)

    # Windshield Header Banner (y=725..788, cleanly below hood grille teeth!)
    d.rectangle([710, 725, 1246, 788], fill=CARBON_DARK)
    paste_center(im, wm_swooz, cx, 756, angle=180, scale=0.64)

    # Front Bumper Banner (upside-down 180 deg at y=152)
    paste_center(im, wm_swooz, cx, 152, angle=180, scale=0.78)

    # Hood: Giant SWOOZ Crest + Wordmark (facing front = 180 deg)
    paste_center(im, crest, cx, 520, angle=180, scale=0.34)
    paste_center(im, wm_swooz, cx, 355, angle=180, scale=1.15)
    paste_center(im, wm_pitwall, cx, 265, angle=180, scale=0.68)

    # Roof: Giant Stock Car Roof Number '#1'
    paste_center(im, num_stock, cx, 1025, angle=-90, scale=1.55)

    # Rear Decklid & Rear Bumper (y=1565..2020, upright 0 deg)
    paste_center(im, crest, cx, 1685, angle=0, scale=0.28)
    paste_center(im, wm_swooz, cx, 1815, angle=0, scale=0.88)
    paste_center(im, wm_pitwall, cx, 1960, angle=0, scale=0.72)

    # Left Body Side (x=280..655, y=105..1925) & Right Body Side (x=1300..1675, y=105..1925)
    d.rectangle([280, 105, 655, 1925], fill=CRIMSON)
    d.rectangle([280, 105, 345, 1925], fill=CARBON_DARK)
    d.rectangle([345, 105, 385, 1925], fill=PAPAYA)
    d.rectangle([390, 105, 398, 1925], fill=WHITE)

    d.rectangle([1300, 105, 1675, 1925], fill=CRIMSON)
    d.rectangle([1610, 105, 1675, 1925], fill=CARBON_DARK)
    d.rectangle([1570, 105, 1610, 1925], fill=PAPAYA)
    d.rectangle([1557, 105, 1565, 1925], fill=WHITE)

    # Left Door Giant '#1' (x=505, y=905, angle=-90) & Quarter Panel 'SWOOZ'
    paste_center(im, num_stock, 505, 905, angle=-90, scale=1.42)
    paste_center(im, wm_swooz, 505, 1515, angle=-90, scale=0.98)
    paste_center(im, crest, 505, 355, angle=-90, scale=0.20)

    # Right Door Giant '#1' (x=1450, y=905, angle=90) & Quarter Panel 'SWOOZ'
    paste_center(im, num_stock, 1450, 905, angle=90, scale=1.42)
    paste_center(im, wm_swooz, 1450, 1515, angle=90, scale=0.98)
    paste_center(im, crest, 1450, 355, angle=90, scale=0.20)

    # Right-side Rear Spoiler Blade (x=1715..1820, y=635..1480)
    draw_crimson_panel(d, (1715, 635, 1820, 1480), "v", "left")
    paste_center(im, wm_swooz, 1768, 1060, angle=-90, scale=0.78)

    return im


# ==============================================================================
# 9. GT (Classic GT Car — 1024x1024, aligned to Italia/Raven reference islands)
# ==============================================================================
def build_gt(crest, wm_swooz, wm_pitwall, num_gt) -> Image.Image:
    # Build at 2048x2048 using exact Italia GT island coordinates (from coords_tin_tops.png), then Lanczos downsample to 1024x1024!
    im = Image.new("RGBA", (2048, 2048), CRIMSON)
    d = ImageDraw.Draw(im)

    # Top-center Hood/Roof Twin Stripes (centerline around x=1008, y=20..760)
    d.rectangle([972, 15, 1044, 780], fill=PAPAYA)
    d.rectangle([956, 15, 965, 780], fill=WHITE)
    d.rectangle([1051, 15, 1060, 780], fill=WHITE)

    # Top-right Rear Wing Main Blade (x=1585..1830, y=15..680 -> vertical wordmark like 'PEPPERMINT' in Italia!)
    d.rectangle([1585, 15, 1830, 680], fill=CARBON_DARK)
    d.rectangle([1585, 15, 1625, 680], fill=PAPAYA)
    paste_center(im, wm_swooz, 1715, 345, angle=-90, scale=1.35)

    # Left Front Bumper / Splitter Strip (x=78..148, y=785..1245 -> vertical 'SWOOZ PIT WALL' at +90 deg)
    d.rectangle([78, 785, 148, 1245], fill=CARBON_DARK)
    paste_center(im, wm_pitwall, 113, 1015, angle=90, scale=0.72)

    # Center Hood / Nose Banner (x=610..815, y=1215..1290)
    d.rectangle([605, 1215, 820, 1290], fill=CARBON_DARK)
    paste_center(im, wm_swooz, 712, 1252, scale=0.52)

    # Left & Right Door Number Plates (verified from Italia #54 at (882, 1055) tilted -8 deg and (1092, 1055) tilted +8 deg!)
    paste_center(im, num_gt, 882, 1055, angle=-8, scale=0.78)
    paste_center(im, num_gt, 1092, 1055, angle=8, scale=0.78)
    paste_center(im, crest, 715, 1080, angle=-8, scale=0.14)
    paste_center(im, crest, 1260, 1080, angle=8, scale=0.14)

    # Lower Door Sill Stripes & 'SWOOZ' Decals (verified from Italia at (405, 1555) & (750, 1565))
    paste_center(im, wm_swooz, 405, 1555, angle=-7, scale=0.56)
    paste_center(im, wm_swooz, 750, 1565, angle=7, scale=0.56)

    # Upper-left Cowl Crest (verified from Italia at (368, 225))
    paste_center(im, crest, 368, 215, scale=0.18)
    paste_center(im, wm_swooz, 368, 305, scale=0.45)

    return im.resize((1024, 1024), Image.Resampling.LANCZOS)


# ==============================================================================
# 10. TEAM ICON (256x256 Transparent RGBA) & LIVERY.JSON
# ==============================================================================
def build_team_icon(crest: Image.Image) -> Image.Image:
    ss = 2
    S = 256 * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    # Sleek carbon-shield badge with crimson + papaya border so it pops on ANY UI background
    pts = [
        (S * 0.14, S * 0.10),
        (S * 0.86, S * 0.10),
        (S * 0.94, S * 0.26),
        (S * 0.82, S * 0.84),
        (S * 0.50, S * 0.95),
        (S * 0.18, S * 0.84),
        (S * 0.06, S * 0.26),
    ]
    d.polygon(pts, fill=(10, 12, 17, 248))
    d.line(pts + [pts[0]], fill=PAPAYA, width=10)
    inner = [(S * 0.5 + (x - S * 0.5) * 0.92, S * 0.5 + (y - S * 0.5) * 0.92) for x, y in pts]
    d.line(inner + [inner[0]], fill=CRIMSON_BRIGHT, width=5)

    paste_center(im, crest, S // 2, int(S * 0.44), scale=0.58)
    wm = make_wordmark("SWOOZ", height=64, fill=WHITE, accent_bar=False)
    paste_center(im, wm, S // 2, int(S * 0.77), scale=1.0)
    return im.resize((256, 256), Image.Resampling.LANCZOS)


def main():
    for folder in [USER_LIVERY_DIR, LOCAL_BACKUP_DIR, VERIFY_DIR]:
        os.makedirs(folder, exist_ok=True)

    crest = extract_swooz_crest()
    wm_swooz = make_wordmark("SWOOZ", height=96, fill=WHITE, accent_bar=True)
    wm_pitwall = make_wordmark("PIT WALL // 50HZ", height=54, fill=SILVER, accent_bar=False)
    wm_sub = make_wordmark("DOM_SWOOZ", height=48, fill=PAPAYA, accent_bar=False)

    num_f1 = make_number_badge("1", size=190, style="f1")
    num_roundel = make_number_badge("1", size=190, style="roundel")
    num_gt = make_number_badge("1", size=190, style="gt_box")
    num_stock = make_number_badge("1", size=220, style="stock")

    builders = {
        "FormulaModern": lambda: build_formula_modern(crest, wm_swooz, wm_pitwall, wm_sub, num_f1),
        "Formula": lambda: build_formula(crest, wm_swooz, wm_pitwall, wm_sub, num_f1),
        "FormulaClassic": lambda: build_formula_classic(crest, wm_swooz, wm_pitwall, wm_sub, num_f1),
        "FormulaOldskool": lambda: build_formula_oldskool(crest, wm_swooz, wm_pitwall, wm_sub, num_roundel),
        "FormulaLegacy": lambda: build_formula_legacy(crest, wm_swooz, wm_pitwall, wm_sub, num_roundel),
        "Endurance": lambda: build_endurance(crest, wm_swooz, wm_pitwall, wm_sub, num_gt),
        "GT2": lambda: build_gt2(crest, wm_swooz, wm_pitwall, wm_sub, num_gt),
        "Stock": lambda: build_stock(crest, wm_swooz, wm_pitwall, wm_sub, num_stock),
        "GT": lambda: build_gt(crest, wm_swooz, wm_pitwall, num_gt),
    }

    rendered = {}
    for car_name, fn in builders.items():
        img = fn()
        rendered[car_name] = img
        for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
            img.save(os.path.join(out_dir, f"{car_name}.png"), "PNG", optimize=True)
        print(f"Saved {car_name}.png ({img.size[0]}x{img.size[1]} {img.mode})")

    icon = build_team_icon(crest)
    for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
        icon.save(os.path.join(out_dir, "icon.png"), "PNG", optimize=True)
    print("Saved icon.png (256x256 RGBA)")

    livery_meta = {
        "formatVersion": 1,
        "teamName": "SWOOZ Racing",
        "primaryColor": "#E10600",
        "secondaryColor": "#FF8000",
        "floorColor": "#0B0D12",
        "recolorIcon": False,
        "metallic": 0.72,
        "smoothness": 0.56,
        "driverNames": ["Dom_Swooz"],
        "workshopFileId": 0,
        "workshopAppId": 0,
        "authorSteamId": 0,
        "authorName": "Dom_Swooz",
    }
    for out_dir in (USER_LIVERY_DIR, LOCAL_BACKUP_DIR):
        with open(os.path.join(out_dir, "livery.json"), "w", encoding="utf-8") as f:
            json.dump(livery_meta, f, indent=4)
    print("Saved livery.json")

    # Build 1) UV-Overlay Verification Sheet (in scratch/uv_verify) AND 2) Clean Showcase Sheet (no UV lines!)
    car_order = ["FormulaModern", "Formula", "FormulaClassic", "FormulaOldskool", "FormulaLegacy", "Endurance", "GT2", "Stock", "GT"]
    verify_grid = Image.new("RGB", (3 * 820, 3 * 820), (10, 12, 16))
    clean_grid = Image.new("RGB", (3 * 820, 3 * 820), (10, 12, 16))
    vd = ImageDraw.Draw(verify_grid)
    cd = ImageDraw.Draw(clean_grid)
    label_font = load_font(26, heavy=True)

    for idx, car_name in enumerate(car_order):
        gx, gy = (idx % 3) * 820, (idx // 3) * 820
        tile_clean = rendered[car_name].resize((790, 790), Image.Resampling.LANCZOS)
        clean_grid.paste(tile_clean.convert("RGB"), (gx + 15, gy + 15))
        cd.rectangle([gx + 15, gy + 15, gx + 310, gy + 54], fill=(8, 10, 14))
        cd.text((gx + 26, gy + 20), f"SWOOZ • {car_name}", font=label_font, fill=(255, 255, 255))

        tile_uv = tile_clean.copy()
        uv_path = os.path.join(UV_DIR, f"{car_name}_UV.png")
        if os.path.exists(uv_path):
            uv_im = Image.open(uv_path).convert("RGBA").resize((790, 790), Image.Resampling.NEAREST)
            tile_uv = Image.alpha_composite(tile_uv, uv_im)
        verify_grid.paste(tile_uv.convert("RGB"), (gx + 15, gy + 15))
        vd.rectangle([gx + 15, gy + 15, gx + 360, gy + 54], fill=(8, 10, 14))
        vd.text((gx + 26, gy + 20), f"UV CHECK • {car_name}", font=label_font, fill=(255, 210, 60))

    verify_grid.save(os.path.join(VERIFY_DIR, "uv_check_all9.png"), "PNG")
    clean_grid.save(SHOWCASE_PATH, "PNG", optimize=True)
    print("Saved verification & showcase grids!")


if __name__ == "__main__":
    main()

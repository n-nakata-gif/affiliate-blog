#!/usr/bin/env python3
"""
generate_thumbnail.py  ―  novlify.jp サムネイル自動生成

デザイン仕様（雑誌・ブログ広告風）:
  背景写真 + 白い半透明カード + 暗い太文字
  ─────────────────────────────────────────
  ① 背景写真（Unsplash）を明るめに表示
  ② 中央に白い丸角カード（半透明）
  ③ カード内：小さいキャッチコピー → 大きいタイトル
  ④ バッジ（ジャンル名）はカード左上に埋め込み
  ⑤ サイト名は右下に小さく

参考イメージ: 「おすすめガジェットのオトクな購入方法」スタイル
"""
from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1200, 630
SITE_NAME     = "novlify.jp"
OUTPUT_DIR    = Path(__file__).parent.parent / "public" / "thumbnails"


def _resolve_font(bold: bool = True) -> str:
    """macOS / Linux 両環境でJapanese太字フォントを自動検出して返す"""
    candidates = (
        [
            # macOS ヒラギノ（太字）
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
            "/System/Library/Fonts/Supplemental/ヒラギノ角ゴシック W6.ttc",
            # Ubuntu: fonts-noto-cjk
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
            # Ubuntu: fonts-ipafont
            "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
            "/usr/share/fonts/truetype/ipafont/ipagp.ttf",
            "/usr/share/fonts/truetype/fonts-ipafont/ipagp.ttf",
        ] if bold else [
            # macOS ヒラギノ（レギュラー）
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/Supplemental/ヒラギノ角ゴシック W3.ttc",
            # Ubuntu: fonts-noto-cjk
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            # Ubuntu: fonts-ipafont
            "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
            "/usr/share/fonts/truetype/ipafont/ipag.ttf",
            "/usr/share/fonts/truetype/fonts-ipafont/ipag.ttf",
        ]
    )
    for p in candidates:
        if Path(p).exists():
            return p
    return ""  # _load_font がデフォルトフォントにフォールバック


FONT_BOLD    = _resolve_font(bold=True)
FONT_REGULAR = _resolve_font(bold=False)

# ── ジャンルテーマ ─────────────────────────────────────────────────────
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_color":     (80, 20, 10),
        "accent":       (210, 60, 15),    # バッジ・アクセントライン色
        "text_dark":    (40, 12, 5),      # タイトル文字色（濃）
        "catch_color":  (180, 50, 10),    # キャッチコピー文字色
        "badge_text":   (255, 255, 255),
        "label":        "グルメ・食",
        "catch":        "お得に美味しく！",
        "default_bg":   "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
    },
    "gadget": {
        "bg_color":     (10, 20, 60),
        "accent":       (20, 100, 200),
        "text_dark":    (5, 20, 55),
        "catch_color":  (15, 80, 170),
        "badge_text":   (255, 255, 255),
        "label":        "ガジェット・テック",
        "catch":        "仕事がサクサク捗る！",
        "default_bg":   "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&q=80",
    },
    "business": {
        "bg_color":     (5, 35, 20),
        "accent":       (10, 140, 60),
        "text_dark":    (5, 30, 15),
        "catch_color":  (8, 110, 45),
        "badge_text":   (255, 255, 255),
        "label":        "ビジネス・副業",
        "catch":        "収入アップの近道！",
        "default_bg":   "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200&q=80",
    },
    "investment": {
        "bg_color":     (45, 28, 5),
        "accent":       (170, 115, 5),
        "text_dark":    (35, 20, 3),
        "catch_color":  (140, 90, 5),
        "badge_text":   (255, 255, 255),
        "label":        "投資・資産運用",
        "catch":        "お金を賢く増やす！",
        "default_bg":   "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    },
    "travel": {
        "bg_color":     (5, 30, 50),
        "accent":       (10, 120, 180),
        "text_dark":    (3, 22, 45),
        "catch_color":  (8, 95, 150),
        "badge_text":   (255, 255, 255),
        "label":        "旅行・観光",
        "catch":        "もっと旅を楽しもう！",
        "default_bg":   "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=1200&q=80",
    },
}

# ── ユーティリティ ─────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def _fetch_image(url: str, timeout: int = 8) -> Image.Image | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None

def _cover_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = img.size
    scale  = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img    = img.resize((nw, nh), Image.LANCZOS)
    return img.crop(((nw-w)//2, (nh-h)//2, (nw-w)//2+w, (nh-h)//2+h))

def _draw_rounded_rect(draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)

def _shorten(title: str) -> str:
    for sep in ["：", "｜", " | "]:
        if sep in title:
            return title.split(sep)[0].strip()
    return title

def _wrap_text(text: str, font, max_w: int, draw) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        cand = cur + ch
        if draw.textlength(cand, font=font) > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur = cand
    if cur: lines.append(cur)
    return lines

def _fit_lines(text, draw, font_path, base_size, max_w,
               max_lines=2, min_last_ratio=0.35):
    for delta in range(0, 32, 6):
        size  = max(40, base_size - delta)
        font  = _load_font(font_path, size)
        lines = _wrap_text(text, font, max_w, draw)
        if len(lines) > max_lines + 1: continue
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]
        last_w = draw.textlength(lines[-1], font=font)
        if len(lines) <= 1 or last_w >= max_w * min_last_ratio:
            return lines, font
    font  = _load_font(font_path, max(40, base_size - 30))
    lines = _wrap_text(text, font, max_w, draw)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]
    return lines, font


# ── メイン関数 ─────────────────────────────────────────────────────────

def create_thumbnail(
    title: str,
    genre: str,
    slug: str,
    output_dir: Path | None = None,
    bg_image_url: str | None = None,
) -> Path:
    theme   = GENRE_THEMES.get(genre, GENRE_THEMES["business"])
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 背景（明るめ）────────────────────────────────────────────
    raw = _fetch_image(bg_image_url or theme["default_bg"])
    bg  = _cover_fill(raw, WIDTH, HEIGHT) if raw else Image.new("RGB", (WIDTH, HEIGHT), theme["bg_color"])
    bg  = bg.filter(ImageFilter.GaussianBlur(radius=1.5))

    # ごく薄いオーバーレイ（写真を活かす）
    result = bg.convert("RGBA")
    result = Image.alpha_composite(result, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 55)))
    img = result.convert("RGB")

    # 仮 draw（カードサイズ計算用）
    draw = ImageDraw.Draw(img)

    # ── フォント ─────────────────────────────────────────────────
    font_catch = _load_font(FONT_BOLD,    30)
    font_badge = _load_font(FONT_BOLD,    26)
    font_site  = _load_font(FONT_REGULAR, 21)

    display = _shorten(title)
    n = len(display)
    if   n <= 8:  base = 108
    elif n <= 13: base = 96
    elif n <= 18: base = 86
    elif n <= 24: base = 76
    elif n <= 30: base = 68
    else:         base = 60

    CARD_MX   = 68    # カード左右マージン
    TEXT_PX   = 46    # カード内テキスト左右パディング
    max_tw    = WIDTH - CARD_MX * 2 - TEXT_PX * 2

    lines, font_t = _fit_lines(display, draw, FONT_BOLD, base, max_tw)
    fs  = font_t.size
    gap = 18
    lh  = fs + gap
    title_h = lh * len(lines) - gap

    # ── カードサイズ計算 ──────────────────────────────────────────
    BADGE_H   = 42    # バッジ行の高さ
    CATCH_H   = font_catch.size + 10
    PAD_TOP   = 28    # バッジ上パディング
    PAD_MID   = 16    # キャッチ〜タイトル間
    PAD_BOT   = 32    # タイトル下パディング
    LINE_H    = 5     # アクセントライン

    card_inner_h = (PAD_TOP + BADGE_H + CATCH_H + PAD_MID
                    + title_h + LINE_H + PAD_BOT)
    card_h = card_inner_h
    card_x1 = CARD_MX
    card_x2 = WIDTH - CARD_MX
    # カードを縦中央（やや上）に配置
    card_y1 = max(24, (HEIGHT - card_h) // 2 - 10)
    card_y2 = card_y1 + card_h

    # ── 白い丸角カード ─────────────────────────────────────────────
    card_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_layer)
    _draw_rounded_rect(cd, (card_x1, card_y1, card_x2, card_y2),
                       radius=22, fill=(255, 255, 255, 225))
    img = Image.alpha_composite(img.convert("RGBA"), card_layer).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── カード内レイアウト ────────────────────────────────────────
    cx  = card_x1 + TEXT_PX   # テキスト左端X
    cy  = card_y1 + PAD_TOP   # 現在のY

    # ① バッジ（ジャンル名）
    ar, ag, ab = theme["accent"]
    bb   = draw.textbbox((0, 0), theme["label"], font=font_badge)
    bw   = bb[2] - bb[0] + 22
    bh   = bb[3] - bb[1] + 10
    _draw_rounded_rect(draw, (cx, cy, cx + bw, cy + bh),
                       radius=16, fill=(ar, ag, ab))
    draw.text((cx + 11, cy + 5 - bb[1]), theme["label"],
              font=font_badge, fill=theme["badge_text"])
    cy += bh + 10

    # ② キャッチコピー（小・ジャンルカラー）
    catch_text = theme["catch"]
    draw.text((cx, cy), catch_text, font=font_catch, fill=theme["catch_color"])
    cy += font_catch.size + PAD_MID

    # ③ タイトル（大・濃い色）
    tc = theme["text_dark"]
    for i, line in enumerate(lines):
        # ごく薄いシャドウ（白カード上なので控えめ）
        draw.text((cx + 1, cy + i * lh + 1), line, font=font_t,
                  fill=(0, 0, 0, 35))
        draw.text((cx, cy + i * lh), line, font=font_t, fill=tc)
    cy += title_h + 18

    # ④ アクセントライン
    draw.rectangle([(cx, cy), (cx + 120, cy + 4)], fill=(ar, ag, ab))
    draw.rectangle([(cx + 128, cy), (cx + 152, cy + 4)],
                   fill=(ar, ag, ab, 100))

    # ── サイト名（右下）─────────────────────────────────────────
    sw = draw.textlength(SITE_NAME, font=font_site)
    draw.text((WIDTH - sw - 32, HEIGHT - 38), SITE_NAME,
              font=font_site, fill=(60, 60, 60, 200))

    out = out_dir / f"{slug}.png"
    # 256色に減色して保存（平均400KB→150KB程度。テキスト主体のサムネでは画質劣化ほぼ不可視）
    img.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT).save(str(out), "PNG", optimize=True)
    return out


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--title",      required=True)
    p.add_argument("--genre",      required=True, choices=list(GENRE_THEMES))
    p.add_argument("--slug",       required=True)
    p.add_argument("--bg-url",     default=None)
    p.add_argument("--output-dir", default=None)
    a = p.parse_args()
    out = create_thumbnail(a.title, a.genre, a.slug,
                           Path(a.output_dir) if a.output_dir else None, a.bg_url)
    print(f"✅ {out}")

if __name__ == "__main__":
    main()

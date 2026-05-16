#!/usr/bin/env python3
"""
generate_thumbnail.py
ブログ記事のサムネイル画像（1200×630px）を自動生成する

デザイン仕様（プロアフィリエイターの標準構成）:
  要素3点のみ: ジャンルバッジ / タイトル（大・中央） / サイト名
  - 背景: Unsplash写真 + 適度なダークオーバーレイ
  - タイトル: 画面中央に白アウトライン文字（大・最大2行）
  - バッジ: 左上にジャンル名（小・控えめ）
  - サイト名: 右下に小さく
"""
from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── 定数 ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1200, 630
SITE_NAME     = "novlify.jp"
OUTPUT_DIR    = Path(__file__).parent.parent / "public" / "thumbnails"

FONT_BOLD    = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# ── ジャンルテーマ ─────────────────────────────────────────────────────
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_color":    (60, 15, 5),
        "text_color":  (255, 220, 0),     # 鮮やかなイエロー
        "badge_fill":  (210, 60, 10),
        "badge_text":  (255, 255, 255),
        "label":       "グルメ・食",
        "default_bg":  "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
    },
    "gadget": {
        "bg_color":    (8, 15, 45),
        "text_color":  (0, 200, 255),     # 鮮やかなシアンブルー
        "badge_fill":  (20, 100, 200),
        "badge_text":  (255, 255, 255),
        "label":       "ガジェット・テック",
        "default_bg":  "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&q=80",
    },
    "business": {
        "bg_color":    (5, 30, 20),
        "text_color":  (80, 255, 140),    # 鮮やかなグリーン
        "badge_fill":  (10, 150, 60),
        "badge_text":  (255, 255, 255),
        "label":       "ビジネス・副業",
        "default_bg":  "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200&q=80",
    },
    "investment": {
        "bg_color":    (40, 25, 5),
        "text_color":  (255, 220, 0),     # 鮮やかなゴールドイエロー
        "badge_fill":  (180, 120, 0),
        "badge_text":  (255, 255, 255),
        "label":       "投資・資産運用",
        "default_bg":  "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    },
    "travel": {
        "bg_color":    (5, 28, 45),
        "text_color":  (255, 255, 255),   # 白（写真の色と被らない）
        "badge_fill":  (10, 120, 180),
        "badge_text":  (255, 255, 255),
        "label":       "旅行・観光",
        "default_bg":  "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=1200&q=80",
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
    return img.crop(((nw - w) // 2, (nh - h) // 2, (nw - w) // 2 + w, (nh - h) // 2 + h))


def _apply_overlay(base: Image.Image, alpha: int = 110) -> Image.Image:
    """均一な暗いオーバーレイ（写真が活きる薄め設定）"""
    result = base.convert("RGBA")
    dark   = Image.new("RGBA", base.size, (0, 0, 0, alpha))
    return Image.alpha_composite(result, dark).convert("RGB")


def _draw_rounded_rect(draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _shorten(title: str) -> str:
    """「：」「｜」前の主題部分だけをサムネイルに使う"""
    for sep in ["：", "｜", " | "]:
        if sep in title:
            return title.split(sep)[0].strip()
    return title


def _wrap_text(text: str, font, max_w: int, draw) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        cand = cur + ch
        if draw.textlength(cand, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def _fit_lines(
    text: str,
    draw,
    font_path: str,
    base_size: int,
    max_w: int,
    max_lines: int = 2,
    min_last_ratio: float = 0.38,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """ウィドウ防止付き。フォントを6px刻みで下げて最適な組み合わせを選ぶ"""
    for delta in range(0, 30, 6):
        size = max(40, base_size - delta)
        font = _load_font(font_path, size)
        lines = _wrap_text(text, font, max_w, draw)
        if len(lines) > max_lines + 1:
            continue
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]
        last_w = draw.textlength(lines[-1], font=font)
        if len(lines) <= 1 or last_w >= max_w * min_last_ratio:
            return lines, font
    font = _load_font(font_path, max(40, base_size - 24))
    lines = _wrap_text(text, font, max_w, draw)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]
    return lines, font


def _draw_outlined(draw, xy, text, font, fill, stroke_w=12):
    """白アウトライン文字（黒シャドウ → 太い白縁 → カラー）"""
    x, y = xy
    # 黒シャドウ（リベ大風の強いシャドウ）
    draw.text((x + 5, y + 5), text, font=font,
              fill=(0, 0, 0, 0),
              stroke_fill=(0, 0, 0, 200),
              stroke_width=stroke_w + 5)
    # 太い白縁 + 鮮やかカラー
    draw.text((x, y), text, font=font,
              fill=fill,
              stroke_fill=(255, 255, 255),
              stroke_width=stroke_w)


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

    # 背景
    raw = _fetch_image(bg_image_url or theme["default_bg"])
    bg  = _cover_fill(raw, WIDTH, HEIGHT) if raw else Image.new("RGB", (WIDTH, HEIGHT), theme["bg_color"])
    bg  = bg.filter(ImageFilter.GaussianBlur(radius=1.2))
    img = _apply_overlay(bg, alpha=145)

    # 作業用 draw（バッジ描画後に再生成）
    draw = ImageDraw.Draw(img)

    # ── バッジ（左上）─────────────────────────────────────────────
    font_badge = _load_font(FONT_BOLD, 27)
    font_site  = _load_font(FONT_REGULAR, 22)

    BX, BY    = 46, 38
    BPH, BPV  = 20, 9
    badge_txt = theme["label"]
    bb        = draw.textbbox((0, 0), badge_txt, font=font_badge)
    bw        = bb[2] - bb[0] + BPH * 2
    bh        = bb[3] - bb[1] + BPV * 2

    badge_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    bd          = ImageDraw.Draw(badge_layer)
    br, bg_, bb_ = theme["badge_fill"]
    _draw_rounded_rect(bd, (BX, BY, BX + bw, BY + bh), 20, (br, bg_, bb_, 230))
    img = Image.alpha_composite(img.convert("RGBA"), badge_layer).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.text((BX + BPH, BY + BPV - bb[1]), badge_txt, font=font_badge, fill=theme["badge_text"])

    # ── タイトル（中央・白アウトライン）──────────────────────────
    display = _shorten(title)

    n = len(display)
    if   n <= 8:  base = 130
    elif n <= 12: base = 116
    elif n <= 17: base = 104
    elif n <= 22: base = 92
    elif n <= 28: base = 82
    else:         base = 72

    MARGIN  = 44
    STROKE  = 12           # 太い白縁で視認性アップ
    max_w   = WIDTH - MARGIN * 2 - STROKE * 2

    lines, font_t = _fit_lines(display, draw, FONT_BOLD, base, max_w)
    fs     = font_t.size
    gap    = 22
    lh     = fs + gap
    total  = lh * len(lines) - gap

    # 画像の視覚的中心（やや上寄り）に配置
    badge_bottom = BY + bh
    visual_center = int(HEIGHT * 0.50)
    title_y = max(badge_bottom + 44, visual_center - total // 2)

    tc = theme["text_color"]
    for i, line in enumerate(lines):
        _draw_outlined(draw, (MARGIN, title_y + i * lh), line, font_t, tc, STROKE)

    # ── サイト名（右下）─────────────────────────────────────────
    sw = draw.textlength(SITE_NAME, font=font_site)
    draw.text((WIDTH - sw - 36, HEIGHT - 42), SITE_NAME,
              font=font_site, fill=(210, 210, 210, 190))

    out = out_dir / f"{slug}.png"
    img.save(str(out), "PNG", optimize=True)
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

#!/usr/bin/env python3
"""
generate_thumbnail.py
ブログ記事のサムネイル画像（1200×630px）を自動生成する

デザイン仕様:
  - 背景: 記事関連のUnsplash写真（URLで指定可）
  - オーバーレイ: 暗い半透明グラデーション + ジャンルカラー
  - テキスト: ヒラギノ角ゴシック W6 の太字白文字（ドロップシャドウ付き）

単体実行:
  python3 src/generate_thumbnail.py --genre gourmet --title "タイトル" --slug gourmet_20260514
  python3 src/generate_thumbnail.py --genre gadget --title "タイトル" --slug gadget_xxx \\
      --bg-url "https://images.unsplash.com/photo-xxx"

generate.py から呼び出し:
  from generate_thumbnail import create_thumbnail
  path = create_thumbnail(title="...", genre="gourmet", slug="gourmet_20260514",
                          bg_image_url="https://images.unsplash.com/...")
"""
from __future__ import annotations

import argparse
import io
import urllib.request
import urllib.error
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── 定数 ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1200, 630
SITE_NAME     = "novlify.jp"
OUTPUT_DIR    = Path(__file__).parent.parent / "public" / "thumbnails"

FONT_BOLD    = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# ── ジャンルテーマ ─────────────────────────────────────────────────────
# bg_color: 画像が取得できない場合のソリッドカラー
# overlay:  画像の上に乗せるグラデーション色（RGBA）
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_color":   (80, 20, 10),
        "overlay":    (160, 30, 10),    # 暖色系レッド
        "badge_fill": (255, 255, 255),
        "badge_text": (160, 30, 10),
        "label":      "グルメ・食",
        "default_bg": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
    },
    "gadget": {
        "bg_color":   (10, 20, 60),
        "overlay":    (15, 40, 120),    # ディープブルー
        "badge_fill": (255, 255, 255),
        "badge_text": (15, 40, 120),
        "label":      "ガジェット・テック",
        "default_bg": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&q=80",
    },
    "business": {
        "bg_color":   (5, 40, 30),
        "overlay":    (8, 80, 60),      # エメラルドグリーン
        "badge_fill": (255, 255, 255),
        "badge_text": (8, 80, 60),
        "label":      "ビジネス・副業",
        "default_bg": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200&q=80",
    },
    "investment": {
        "bg_color":   (50, 30, 5),
        "overlay":    (110, 65, 8),     # ゴールド
        "badge_fill": (255, 255, 255),
        "badge_text": (110, 65, 8),
        "label":      "投資・資産運用",
        "default_bg": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    },
    "travel": {
        "bg_color":   (5, 35, 55),
        "overlay":    (8, 75, 120),     # スカイシアン
        "badge_fill": (255, 255, 255),
        "badge_text": (8, 75, 120),
        "label":      "旅行・観光",
        "default_bg": "https://images.unsplash.com/photo-1488085061387-422e29b40080?w=1200&q=80",
    },
}

# ── ユーティリティ ─────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _fetch_image(url: str, timeout: int = 8) -> Image.Image | None:
    """URLから画像をダウンロードして PIL Image で返す。失敗したら None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None


def _cover_fill(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """画像をアスペクト比を保ったまま target サイズに cover-fill (中央クロップ)"""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _make_solid_bg(w: int, h: int, color: tuple) -> Image.Image:
    """ソリッドカラーの背景（フォールバック用）"""
    return Image.new("RGB", (w, h), color)


def _apply_overlays(base: Image.Image, genre_color: tuple) -> Image.Image:
    """
    2層のオーバーレイを合成する:
      1. 全体: 暗い半透明（画像を沈める）
      2. 左〜中央: ジャンルカラー半透明グラデーション（テキスト読みやすさ確保）
    """
    w, h = base.size

    # --- レイヤー1: 全体を暗くする均一オーバーレイ ---
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 155))   # 60% 暗め
    result = Image.alpha_composite(base.convert("RGBA"), dark)

    # --- レイヤー2: 左側にジャンルカラーグラデーション ---
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(grad)
    r, g, b = genre_color
    # 左端: 不透明度 160 → 右端: 0 (水平グラデーション)
    for x in range(w):
        t = x / (w - 1)
        # 左2/3は濃く、右1/3は薄く
        alpha = int(max(0, 160 * (1 - t * 1.3)))
        draw.line([(x, 0), (x, h)], fill=(r, g, b, alpha))
    result = Image.alpha_composite(result, grad)

    # --- レイヤー3: 下部をより暗くしてサイト名を読みやすく ---
    bottom = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(bottom)
    for y in range(h):
        if y < h - 120:
            continue
        t = (y - (h - 120)) / 120
        alpha = int(180 * t)
        draw2.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    result = Image.alpha_composite(result, bottom)

    return result.convert("RGB")


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """テキストを max_width に収まるよう1文字ずつ折り返す"""
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if draw.textlength(candidate, font=font) > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple,
) -> None:
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


# ── メイン関数 ─────────────────────────────────────────────────────────

def create_thumbnail(
    title: str,
    genre: str,
    slug: str,
    output_dir: Path | None = None,
    bg_image_url: str | None = None,
) -> Path:
    """
    サムネイル画像を生成して保存し、ファイルパスを返す。

    Args:
        title:        記事タイトル
        genre:        ジャンル (gourmet / gadget / business / investment / travel)
        slug:         保存ファイル名のベース (例: gourmet_20260514)
        output_dir:   保存先ディレクトリ (省略時は public/thumbnails/)
        bg_image_url: 背景に使う画像の URL（省略時はジャンルデフォルト画像）

    Returns:
        生成画像の Path
    """
    theme   = GENRE_THEMES.get(genre, GENRE_THEMES["business"])
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 背景画像を取得 ────────────────────────────────────────────
    url = bg_image_url or theme["default_bg"]
    raw_img = _fetch_image(url)

    if raw_img:
        bg = _cover_fill(raw_img, WIDTH, HEIGHT)
        # 軽いブラーで写真感を抑えてテキストを際立たせる
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
    else:
        # フォールバック: ソリッドカラー
        bg = _make_solid_bg(WIDTH, HEIGHT, theme["bg_color"])

    # ── オーバーレイ合成 ─────────────────────────────────────────
    img = _apply_overlays(bg, theme["overlay"])
    draw = ImageDraw.Draw(img)

    # ── フォント ─────────────────────────────────────────────────
    font_badge = _load_font(FONT_BOLD, 28)
    font_site  = _load_font(FONT_REGULAR, 26)

    if len(title) <= 18:
        font_title = _load_font(FONT_BOLD, 70)
    elif len(title) <= 28:
        font_title = _load_font(FONT_BOLD, 60)
    elif len(title) <= 40:
        font_title = _load_font(FONT_BOLD, 52)
    else:
        font_title = _load_font(FONT_BOLD, 44)

    # ── ジャンルバッジ（左上）────────────────────────────────────
    PAD_X, PAD_Y     = 60, 48
    BADGE_PH, BADGE_PV = 20, 10

    badge_text = theme["label"]
    bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = bbox[2] - bbox[0] + BADGE_PH * 2
    bh = bbox[3] - bbox[1] + BADGE_PV * 2
    _draw_rounded_rect(
        draw,
        (PAD_X, PAD_Y, PAD_X + bw, PAD_Y + bh),
        radius=22,
        fill=theme["badge_fill"],
    )
    draw.text(
        (PAD_X + BADGE_PH, PAD_Y + BADGE_PV - bbox[1]),
        badge_text,
        font=font_badge,
        fill=theme["badge_text"],
    )

    # ── タイトルテキスト ─────────────────────────────────────────
    margin_x   = PAD_X
    max_tw     = WIDTH - margin_x * 2
    lines      = _wrap_text(title, font_title, max_tw, draw)

    if len(lines) > 3:
        lines = lines[:2] + [lines[2] + "…"]

    line_gap  = 14
    line_h    = font_title.size + line_gap
    total_h   = line_h * len(lines) - line_gap
    badge_btm = PAD_Y + bh

    title_y = max(badge_btm + 44, (HEIGHT - total_h) // 2 - 20)

    for i, line in enumerate(lines):
        y = title_y + i * line_h
        # 多層シャドウ（背景画像上でも読める）
        for dx, dy, alpha in [(3, 3, 120), (2, 2, 100), (1, 1, 80)]:
            draw.text((margin_x + dx, y + dy), line, font=font_title,
                      fill=(0, 0, 0, alpha))
        draw.text((margin_x, y), line, font=font_title, fill=(255, 255, 255))

    # ── タイトル下のアクセントライン ─────────────────────────────
    accent_y = title_y + total_h + 24
    draw.rectangle(
        [(margin_x, accent_y), (margin_x + 100, accent_y + 5)],
        fill=(255, 255, 255, 200),
    )
    draw.rectangle(
        [(margin_x + 108, accent_y), (margin_x + 130, accent_y + 5)],
        fill=(255, 255, 255, 90),
    )

    # ── サイト名（下部中央）─────────────────────────────────────
    site_w = draw.textlength(SITE_NAME, font=font_site)
    draw.text(
        ((WIDTH - site_w) // 2, HEIGHT - 62),
        SITE_NAME,
        font=font_site,
        fill=(255, 255, 255, 210),
    )

    # ── 保存 ────────────────────────────────────────────────────
    out_path = out_dir / f"{slug}.png"
    img.save(str(out_path), "PNG", optimize=True)
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ブログ記事のサムネイルを生成します")
    parser.add_argument("--title",   required=True, help="記事タイトル")
    parser.add_argument("--genre",   required=True, choices=list(GENRE_THEMES.keys()))
    parser.add_argument("--slug",    required=True, help="例: gourmet_20260514")
    parser.add_argument("--bg-url",  default=None,  help="背景画像URL（省略時はジャンルデフォルト）")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    out_dir  = Path(args.output_dir) if args.output_dir else None
    out_path = create_thumbnail(args.title, args.genre, args.slug, out_dir, args.bg_url)
    print(f"✅ サムネイル生成: {out_path}")


if __name__ == "__main__":
    main()

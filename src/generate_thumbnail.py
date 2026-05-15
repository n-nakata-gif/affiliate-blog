#!/usr/bin/env python3
"""
generate_thumbnail.py
ブログ記事のサムネイル画像（1200×630px）を自動生成する

単体実行:
  python3 src/generate_thumbnail.py --genre gourmet --title "プロテインの選び方" --slug gourmet_20260514

generate.py から呼び出し:
  from generate_thumbnail import create_thumbnail
  path = create_thumbnail(title="記事タイトル", genre="gourmet", slug="gourmet_20260514")
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── 定数 ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1200, 630
SITE_NAME     = "novlify.jp"
OUTPUT_DIR    = Path(__file__).parent.parent / "public" / "thumbnails"

FONT_BOLD    = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# ジャンル別カラーテーマ（グラデーション上→下）
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_top":    (190, 45, 20),
        "bg_bottom": (240, 110, 50),
        "badge_fill": (255, 255, 255),
        "badge_text": (190, 45, 20),
        "label":     "グルメ・食",
    },
    "gadget": {
        "bg_top":    (18, 45, 130),
        "bg_bottom": (55, 100, 210),
        "badge_fill": (255, 255, 255),
        "badge_text": (18, 45, 130),
        "label":     "ガジェット・テック",
    },
    "business": {
        "bg_top":    (8, 90, 70),
        "bg_bottom": (25, 155, 115),
        "badge_fill": (255, 255, 255),
        "badge_text": (8, 90, 70),
        "label":     "ビジネス・副業",
    },
    "investment": {
        "bg_top":    (120, 70, 8),
        "bg_bottom": (200, 145, 35),
        "badge_fill": (255, 255, 255),
        "badge_text": (120, 70, 8),
        "label":     "投資・資産運用",
    },
    "travel": {
        "bg_top":    (8, 90, 130),
        "bg_bottom": (25, 155, 195),
        "badge_fill": (255, 255, 255),
        "badge_text": (8, 90, 130),
        "label":     "旅行・観光",
    },
}

# ── ヘルパー ───────────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _gradient_bg(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    """上から下へのグラデーション背景を生成"""
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        t = y / (h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


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
        w = draw.textlength(candidate, font=font)
        if w > max_width and current:
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
    """Pillow 8.2+ の rounded_rectangle、古い場合は通常の矩形にフォールバック"""
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
) -> Path:
    """
    サムネイル画像を生成して保存し、ファイルパスを返す。

    Args:
        title:      記事タイトル
        genre:      ジャンル (gourmet / gadget / business / investment / travel)
        slug:       保存ファイル名のベース (例: gourmet_20260514)
        output_dir: 保存先ディレクトリ (省略時は public/thumbnails/)

    Returns:
        生成画像の Path
    """
    theme   = GENRE_THEMES.get(genre, GENRE_THEMES["business"])
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 背景 ──────────────────────────────────────────────────────
    img = _gradient_bg((WIDTH, HEIGHT), theme["bg_top"], theme["bg_bottom"])

    # 下部に半透明の暗いオーバーレイ（サイト名エリア）
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rectangle([(0, HEIGHT - 90), (WIDTH, HEIGHT)], fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # 右上にぼんやりした丸い光彩（装飾）
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gw_draw = ImageDraw.Draw(glow)
    for r in range(200, 0, -4):
        alpha = int(25 * (1 - r / 200))
        gw_draw.ellipse(
            [(WIDTH - 250 - r, -r), (WIDTH - 250 + r, r * 2)],
            fill=(255, 255, 255, alpha),
        )
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(img)

    # ── フォント ──────────────────────────────────────────────────
    font_badge  = _load_font(FONT_BOLD,    28)
    font_site   = _load_font(FONT_REGULAR, 26)

    # タイトル長に応じてフォントサイズを自動調整
    if len(title) <= 18:
        font_title = _load_font(FONT_BOLD, 68)
    elif len(title) <= 28:
        font_title = _load_font(FONT_BOLD, 58)
    elif len(title) <= 40:
        font_title = _load_font(FONT_BOLD, 50)
    else:
        font_title = _load_font(FONT_BOLD, 42)

    # ── ジャンルバッジ（左上） ────────────────────────────────────
    PAD_X, PAD_Y = 60, 46
    badge_pad_h, badge_pad_v = 20, 10
    badge_text = theme["label"]
    bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = bbox[2] - bbox[0] + badge_pad_h * 2
    bh = bbox[3] - bbox[1] + badge_pad_v * 2
    _draw_rounded_rect(
        draw,
        (PAD_X, PAD_Y, PAD_X + bw, PAD_Y + bh),
        radius=22,
        fill=theme["badge_fill"],
    )
    draw.text(
        (PAD_X + badge_pad_h, PAD_Y + badge_pad_v - bbox[1]),
        badge_text,
        font=font_badge,
        fill=theme["badge_text"],
    )

    # ── タイトルテキスト ──────────────────────────────────────────
    margin_x   = PAD_X
    max_tw     = WIDTH - margin_x * 2
    lines      = _wrap_text(title, font_title, max_tw, draw)

    # 最大3行。3行を超えた場合は3行目を省略
    if len(lines) > 3:
        lines = lines[:2] + [lines[2] + "…"]

    line_gap   = 14
    line_h     = font_title.size + line_gap
    total_h    = line_h * len(lines) - line_gap
    badge_bottom = PAD_Y + bh

    # タイトルブロックをページ中央～やや上に配置
    title_y = max(badge_bottom + 44, (HEIGHT - total_h) // 2 - 24)

    for i, line in enumerate(lines):
        y = title_y + i * line_h
        # ドロップシャドウ
        draw.text((margin_x + 3, y + 3), line, font=font_title, fill=(0, 0, 0, 80))
        # 本文（白）
        draw.text((margin_x, y), line, font=font_title, fill=(255, 255, 255))

    # ── タイトル下のアクセントライン ─────────────────────────────
    accent_y = title_y + total_h + 22
    draw.rectangle(
        [(margin_x, accent_y), (margin_x + 100, accent_y + 5)],
        fill=(255, 255, 255, 180),
    )
    draw.rectangle(
        [(margin_x + 108, accent_y), (margin_x + 130, accent_y + 5)],
        fill=(255, 255, 255, 80),
    )

    # ── サイト名（下部中央） ──────────────────────────────────────
    site_w = draw.textlength(SITE_NAME, font=font_site)
    draw.text(
        ((WIDTH - site_w) // 2, HEIGHT - 62),
        SITE_NAME,
        font=font_site,
        fill=(255, 255, 255, 210),
    )

    # ── 保存 ──────────────────────────────────────────────────────
    out_path = out_dir / f"{slug}.png"
    img.save(str(out_path), "PNG", optimize=True)
    return out_path


# ── CLI エントリポイント ────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ブログ記事のサムネイル画像を生成します"
    )
    parser.add_argument("--title",  required=True, help="記事タイトル")
    parser.add_argument(
        "--genre", required=True,
        choices=list(GENRE_THEMES.keys()),
        help="ジャンル",
    )
    parser.add_argument(
        "--slug", required=True,
        help="ファイル名スラッグ（例: gourmet_20260514）",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="保存先ディレクトリ（省略時は public/thumbnails/）",
    )
    args = parser.parse_args()

    out_dir  = Path(args.output_dir) if args.output_dir else None
    out_path = create_thumbnail(args.title, args.genre, args.slug, out_dir)
    print(f"✅ サムネイル生成: {out_path}")


if __name__ == "__main__":
    main()

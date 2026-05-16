#!/usr/bin/env python3
"""
generate_thumbnail.py
ブログ記事のサムネイル画像（1200×630px）を自動生成する

デザイン仕様:
  - 背景: 記事関連のUnsplash写真
  - 暗いオーバーレイ（写真を活かしつつ文字を際立てる）
  - テキスト: 大きな白抜き文字（ジャンルカラー＋太い白アウトライン）
              → YouTube人気チャンネル風の視認性の高いデザイン
  - バッジ: ジャンルカラーの丸角バッジ（左上）
  - サイト名: 下部中央（白文字）

単体実行:
  python3 src/generate_thumbnail.py --genre gourmet --title "タイトル" --slug gourmet_20260514

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
# text_color: 白抜き文字の内側色（鮮やかな色）
# badge_fill: 左上バッジの背景色
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_color":   (80, 20, 10),
        "text_color": (255, 80, 15),     # 鮮やかオレンジレッド
        "badge_fill": (220, 60, 10),
        "badge_text": (255, 255, 255),
        "label":      "グルメ・食",
        "default_bg": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
    },
    "gadget": {
        "bg_color":   (10, 20, 60),
        "text_color": (30, 170, 255),    # ブライトブルー
        "badge_fill": (20, 130, 220),
        "badge_text": (255, 255, 255),
        "label":      "ガジェット・テック",
        "default_bg": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&q=80",
    },
    "business": {
        "bg_color":   (5, 40, 30),
        "text_color": (40, 220, 120),    # ブライトグリーン
        "badge_fill": (15, 170, 85),
        "badge_text": (255, 255, 255),
        "label":      "ビジネス・副業",
        "default_bg": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200&q=80",
    },
    "investment": {
        "bg_color":   (50, 30, 5),
        "text_color": (255, 210, 0),     # ゴールドイエロー
        "badge_fill": (190, 140, 0),
        "badge_text": (255, 255, 255),
        "label":      "投資・資産運用",
        "default_bg": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    },
    "travel": {
        "bg_color":   (5, 35, 55),
        "text_color": (30, 215, 255),    # スカイシアン
        "badge_fill": (10, 140, 205),
        "badge_text": (255, 255, 255),
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
    """アスペクト比を保ちながら cover-fill（中央クロップ）"""
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _make_solid_bg(w: int, h: int, color: tuple) -> Image.Image:
    return Image.new("RGB", (w, h), color)


def _apply_overlay(base: Image.Image, dark_alpha: int = 150) -> Image.Image:
    """
    写真を活かしつつ白抜き文字が映えるよう調整するオーバーレイ:
      - 全体: 均一な暗いオーバーレイ（文字を浮き立たせる）
      - 下部: より暗くしてサイト名を読みやすく
    """
    w, h = base.size
    result = base.convert("RGBA")

    # 全体を暗く
    dark = Image.new("RGBA", (w, h), (0, 0, 0, dark_alpha))
    result = Image.alpha_composite(result, dark)

    # 下部グラデーション
    bottom = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(bottom)
    for y in range(h):
        if y < h - 120:
            continue
        t = (y - (h - 120)) / 120
        alpha = int(200 * t)
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


def _shorten_for_thumbnail(title: str) -> str:
    """
    サムネイル用に短縮したタイトルを返す。
    '：' '｜' ' | ' の前の主題部分だけを使用。
    例: "新幹線を安く乗る方法：早割…" → "新幹線を安く乗る方法"
    """
    for sep in ["：", "｜", " | "]:
        if sep in title:
            return title.split(sep)[0].strip()
    return title


def _wrap_no_widow(
    text: str,
    draw: ImageDraw.ImageDraw,
    font_path: str,
    base_size: int,
    max_width: int,
    max_lines: int = 2,
    min_last_ratio: float = 0.38,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """
    ウィドウ（末尾の極端に短い行）が出ないようフォントサイズを調整しながら折り返す。
    base_size から 6px ずつ下げながら最大 4回試みる。
    """
    for delta in [0, 6, 12, 18, 24]:
        size = max(36, base_size - delta)
        font = _load_font(font_path, size)
        lines = _wrap_text(text, font, max_width, draw)

        if len(lines) > max_lines + 1:
            continue

        if len(lines) > max_lines:
            lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]

        last_w = draw.textlength(lines[-1], font=font)
        if len(lines) <= 1 or last_w >= max_width * min_last_ratio:
            return lines, font

    font = _load_font(font_path, max(36, base_size - 24))
    lines = _wrap_text(text, font, max_width, draw)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]
    return lines, font


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    stroke_width: int = 9,
) -> None:
    """
    白抜き文字を描画する:
      1. 黒いシャドウ（+4,+4 ずらし、黒ストローク）
      2. 白いアウトライン + ジャンルカラーのテキスト
    """
    x, y = xy
    sw = stroke_width

    # シャドウパス（ずらして黒く描画）
    draw.text(
        (x + 4, y + 4),
        text,
        font=font,
        fill=(0, 0, 0, 0),           # 塗りなし
        stroke_fill=(0, 0, 0, 160),  # 黒ストロークでシャドウ
        stroke_width=sw + 3,
    )

    # 本体: 白アウトライン + ジャンルカラー
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_fill=(255, 255, 255),
        stroke_width=sw,
    )


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
        title:        記事タイトル（SEO用フルタイトルでOK。サムネイルでは自動短縮）
        genre:        ジャンル (gourmet / gadget / business / investment / travel)
        slug:         保存ファイル名のベース
        output_dir:   保存先ディレクトリ (省略時は public/thumbnails/)
        bg_image_url: 背景画像URL（省略時はジャンルデフォルト）

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
        bg = bg.filter(ImageFilter.GaussianBlur(radius=1.5))
    else:
        bg = _make_solid_bg(WIDTH, HEIGHT, theme["bg_color"])

    # ── オーバーレイ（文字が映えるよう暗め）─────────────────────
    img = _apply_overlay(bg, dark_alpha=155)

    # ── フォント ─────────────────────────────────────────────────
    font_badge = _load_font(FONT_BOLD, 30)
    font_site  = _load_font(FONT_REGULAR, 24)

    # ── サムネイル用タイトル（「：」前の主題部分だけ）───────────
    display_title = _shorten_for_thumbnail(title)

    # 文字数に応じた基準フォントサイズ（白抜き文字は大きく）
    n = len(display_title)
    if n <= 9:
        base_font_size = 110
    elif n <= 14:
        base_font_size = 96
    elif n <= 19:
        base_font_size = 86
    elif n <= 25:
        base_font_size = 76
    else:
        base_font_size = 68

    # ── ジャンルバッジ（左上）────────────────────────────────────
    PAD_X, PAD_Y     = 52, 42
    BADGE_PH, BADGE_PV = 22, 10

    badge_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    badge_draw  = ImageDraw.Draw(badge_layer)

    badge_text = theme["label"]
    bbox = badge_draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = bbox[2] - bbox[0] + BADGE_PH * 2
    bh = bbox[3] - bbox[1] + BADGE_PV * 2

    br, bg_, bb = theme["badge_fill"]
    _draw_rounded_rect(
        badge_draw,
        (PAD_X, PAD_Y, PAD_X + bw, PAD_Y + bh),
        radius=24,
        fill=(br, bg_, bb, 240),
    )
    img = Image.alpha_composite(img.convert("RGBA"), badge_layer).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.text(
        (PAD_X + BADGE_PH, PAD_Y + BADGE_PV - bbox[1]),
        badge_text,
        font=font_badge,
        fill=theme["badge_text"],
    )

    # ── タイトル折り返し（ウィドウ防止）──────────────────────────
    TEXT_X   = PAD_X          # 左端X
    STROKE_W = 9               # 白アウトライン幅
    # ストローク込みの実効幅で折り返し幅を計算
    max_tw = WIDTH - TEXT_X - PAD_X - STROKE_W * 2

    lines, font_title = _wrap_no_widow(
        display_title, draw, FONT_BOLD, base_font_size, max_tw,
        max_lines=2, min_last_ratio=0.38,
    )
    font_size = font_title.size

    line_gap = 22
    line_h   = font_size + line_gap
    total_h  = line_h * len(lines) - line_gap

    badge_btm = PAD_Y + bh
    # 縦方向: バッジ下・サイト名上の中央に配置
    usable_top    = badge_btm + 40
    usable_bottom = HEIGHT - 100   # サイト名エリアを除く
    title_y = usable_top + (usable_bottom - usable_top - total_h) // 2

    # ── 白抜き文字でタイトル描画 ──────────────────────────────────
    tc = theme["text_color"]
    for i, line in enumerate(lines):
        y = title_y + i * line_h
        _draw_outlined_text(
            draw,
            (TEXT_X, y),
            line,
            font_title,
            fill=tc,
            stroke_width=STROKE_W,
        )

    # ── サイト名（下部中央）─────────────────────────────────────
    site_w = draw.textlength(SITE_NAME, font=font_site)
    draw.text(
        ((WIDTH - site_w) // 2, HEIGHT - 54),
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

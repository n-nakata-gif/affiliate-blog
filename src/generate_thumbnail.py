#!/usr/bin/env python3
"""
generate_thumbnail.py
ブログ記事のサムネイル画像（1200×630px）を自動生成する

デザイン仕様:
  - 背景: 記事関連のUnsplash写真（URLで指定可）
  - 薄い暗いオーバーレイ（写真をしっかり見せる）
  - タイトル: 白い半透明カードの上に大きな濃い文字
  - バッジ: ジャンルカラーの丸角バッジ（左上）
  - サイト名: 下部中央（白文字）

単体実行:
  python3 src/generate_thumbnail.py --genre gourmet --title "タイトル" --slug gourmet_20260514
  python3 src/generate_thumbnail.py --genre gadget --title "タイトル" --slug gadget_xxx \
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
# overlay:  背景オーバーレイ・バッジ・アクセントラインに使う色（RGB）
# card_text: タイトルカード上のテキスト色
GENRE_THEMES: dict[str, dict] = {
    "gourmet": {
        "bg_color":   (80, 20, 10),
        "overlay":    (180, 40, 15),    # 暖色系レッド
        "card_text":  (140, 25, 10),
        "badge_fill": (180, 40, 15),
        "badge_text": (255, 255, 255),
        "label":      "グルメ・食",
        "default_bg": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1200&q=80",
    },
    "gadget": {
        "bg_color":   (10, 20, 60),
        "overlay":    (20, 60, 160),    # ディープブルー
        "card_text":  (15, 45, 130),
        "badge_fill": (20, 60, 160),
        "badge_text": (255, 255, 255),
        "label":      "ガジェット・テック",
        "default_bg": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200&q=80",
    },
    "business": {
        "bg_color":   (5, 40, 30),
        "overlay":    (10, 100, 75),    # エメラルドグリーン
        "card_text":  (8, 80, 60),
        "badge_fill": (10, 100, 75),
        "badge_text": (255, 255, 255),
        "label":      "ビジネス・副業",
        "default_bg": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1200&q=80",
    },
    "investment": {
        "bg_color":   (50, 30, 5),
        "overlay":    (140, 85, 10),    # ゴールド
        "card_text":  (110, 65, 8),
        "badge_fill": (140, 85, 10),
        "badge_text": (255, 255, 255),
        "label":      "投資・資産運用",
        "default_bg": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    },
    "travel": {
        "bg_color":   (5, 35, 55),
        "overlay":    (10, 95, 155),    # スカイブルー
        "card_text":  (8, 75, 125),
        "badge_fill": (10, 95, 155),
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


def _apply_light_overlay(base: Image.Image) -> Image.Image:
    """
    背景写真が活きる薄めのオーバーレイ:
      - 全体: 非常に薄い暗め（写真をしっかり見せる）
      - 下部: 少し暗くしてサイト名を読みやすく
    """
    w, h = base.size
    result = base.convert("RGBA")

    # --- レイヤー1: 全体を軽く暗くする（写真はしっかり見える）---
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 80))   # 約30%暗め（以前は60%）
    result = Image.alpha_composite(result, dark)

    # --- レイヤー2: 下部のみ暗くしてサイト名を読みやすく ---
    bottom = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw2 = ImageDraw.Draw(bottom)
    for y in range(h):
        if y < h - 110:
            continue
        t = (y - (h - 110)) / 110
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
    例: "新幹線を安く乗る方法：早割・スマートEXの使い方" → "新幹線を安く乗る方法"
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
    min_last_ratio: float = 0.35,
) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """
    ウィドウ（末尾の極端に短い行）が出ないようにフォントサイズを調整して折り返す。

    - base_size から始めて 6px ずつ下げながら最大 3回試みる
    - 最終行の幅が max_width * min_last_ratio 以上になれば OK
    - max_lines を超える場合も次のサイズへ
    """
    for delta in [0, 6, 12, 18]:
        size = max(32, base_size - delta)
        font = _load_font(font_path, size)
        lines = _wrap_text(text, font, max_width, draw)

        # 行数オーバーは除外
        if len(lines) > max_lines + 1:
            continue

        # 末尾カット（3行目以降は省略）
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [lines[max_lines][:2] + "…"]

        # ウィドウチェック: 最終行が十分な幅か
        last_w = draw.textlength(lines[-1], font=font)
        if len(lines) <= 1 or last_w >= max_width * min_last_ratio:
            return lines, font

    # どうしても解消できない場合はそのまま返す
    font = _load_font(font_path, max(32, base_size - 18))
    lines = _wrap_text(text, font, max_width, draw)
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
        # 極軽めのブラー（写真の精細さを活かす）
        bg = bg.filter(ImageFilter.GaussianBlur(radius=1))
    else:
        bg = _make_solid_bg(WIDTH, HEIGHT, theme["bg_color"])

    # ── 薄いオーバーレイ合成（背景写真を活かす）─────────────────
    img = _apply_light_overlay(bg)

    # ── サムネイル用タイトル（「：」前の主題部分だけ使う）────────
    display_title = _shorten_for_thumbnail(title)

    # ── フォント ─────────────────────────────────────────────────
    font_badge = _load_font(FONT_BOLD, 32)
    font_site  = _load_font(FONT_REGULAR, 26)

    # タイトルの文字数に応じた基準フォントサイズ（短縮後の文字数で判定）
    n = len(display_title)
    if n <= 10:
        base_font_size = 92
    elif n <= 16:
        base_font_size = 82
    elif n <= 22:
        base_font_size = 72
    elif n <= 30:
        base_font_size = 64
    else:
        base_font_size = 56

    # ── ジャンルバッジ（左上）────────────────────────────────────
    PAD_X, PAD_Y     = 56, 44
    BADGE_PH, BADGE_PV = 24, 12

    # バッジを RGBA レイヤーで描画
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
        radius=26,
        fill=(br, bg_, bb, 245),
    )
    img = Image.alpha_composite(img.convert("RGBA"), badge_layer).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.text(
        (PAD_X + BADGE_PH, PAD_Y + BADGE_PV - bbox[1]),
        badge_text,
        font=font_badge,
        fill=theme["badge_text"],
    )

    # ── タイトルの折り返し計算（ウィドウ防止）───────────────────
    CARD_MARGIN_X  = 56          # カード左右の余白
    TEXT_PAD_X     = 44          # カード内テキスト左右のパディング
    TEXT_PAD_Y     = 32          # カード内テキスト上下のパディング
    max_tw = WIDTH - CARD_MARGIN_X * 2 - TEXT_PAD_X * 2

    # ウィドウ（末尾の極端に短い行）が出ないよう調整しながら折り返す
    lines, font_title = _wrap_no_widow(
        display_title, draw, FONT_BOLD, base_font_size, max_tw,
        max_lines=2, min_last_ratio=0.35,
    )
    font_size = font_title.size

    line_gap  = 20
    line_h    = font_size + line_gap
    total_h   = line_h * len(lines) - line_gap

    badge_btm = PAD_Y + bh
    # カードの垂直位置: バッジ下 60px 以降 or 画面中央付近
    card_y1 = max(badge_btm + 50, (HEIGHT - total_h) // 2 - TEXT_PAD_Y - 20)
    card_y2 = card_y1 + total_h + TEXT_PAD_Y * 2
    card_x1 = CARD_MARGIN_X
    card_x2 = WIDTH - CARD_MARGIN_X

    # ── アクセントライン（カード上部）──────────────────────────────
    ar, ag, ab = theme["overlay"]
    draw.rectangle(
        [(card_x1, card_y1 - 8), (card_x1 + 130, card_y1 - 2)],
        fill=(ar, ag, ab),
    )
    draw.rectangle(
        [(card_x1 + 138, card_y1 - 8), (card_x1 + 165, card_y1 - 2)],
        fill=(ar, ag, ab, 120),
    )

    # ── 白い半透明カード ──────────────────────────────────────────
    card_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    card_draw  = ImageDraw.Draw(card_layer)
    _draw_rounded_rect(
        card_draw,
        (card_x1, card_y1, card_x2, card_y2),
        radius=18,
        fill=(255, 255, 255, 215),
    )
    img = Image.alpha_composite(img.convert("RGBA"), card_layer).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── タイトルテキスト（カード上に大きく）─────────────────────
    cr, cg, cb = theme["card_text"]
    title_y = card_y1 + TEXT_PAD_Y

    for i, line in enumerate(lines):
        y = title_y + i * line_h
        # 1px 程度の細いシャドウ（白カード上なので控えめに）
        draw.text((card_x1 + TEXT_PAD_X + 1, y + 1), line,
                  font=font_title, fill=(0, 0, 0, 40))
        draw.text((card_x1 + TEXT_PAD_X, y), line,
                  font=font_title, fill=(cr, cg, cb))

    # ── サイト名（下部中央）─────────────────────────────────────
    font_site_w = draw.textlength(SITE_NAME, font=font_site)
    draw.text(
        ((WIDTH - font_site_w) // 2, HEIGHT - 60),
        SITE_NAME,
        font=font_site,
        fill=(255, 255, 255, 220),
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

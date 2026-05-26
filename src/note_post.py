"""
note.comへの記事投稿スクリプト（Playwright使用）。

【認証方式】
優先: NOTE_SESSION_COOKIE 環境変数 → セッションクッキーで認証（推奨）
代替: NOTE_EMAIL + NOTE_PASSWORD → メール/パスワードでログイン

NOTE_SESSION_COOKIE の取得方法:
  1. ブラウザで https://note.com にログイン
  2. DevTools → Application → Cookies → https://note.com
  3. "_note_session" の値をコピー → GitHub Secrets に NOTE_SESSION_COOKIE として保存

必要な環境変数（いずれかのセット）:
  セット1: NOTE_SESSION_COOKIE  ← 推奨・安定
  セット2: NOTE_EMAIL + NOTE_PASSWORD
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

# ────────────────────────────────────────────
#  カバー画像生成
# ────────────────────────────────────────────

NOTE_COVERS_DIR = Path("data/note_covers")


def _find_japanese_font() -> str | None:
    """利用可能な日本語フォントのパスを返す。"""
    candidates = [
        # Ubuntu (GitHub Actions) – apt install fonts-noto-cjk 後
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        # macOS
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # fc-list でフォールバック検索
    try:
        result = subprocess.run(
            ["fc-list", ":lang=ja", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            p = line.strip()
            if p and os.path.exists(p):
                return p
    except Exception:
        pass
    return None


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """テキストを指定ピクセル幅で折り返す（最大3行）。"""
    lines: list[str] = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = ch
            if len(lines) >= 3:
                break
        else:
            current = test
    if current and len(lines) < 3:
        lines.append(current)
    return lines


_THEMES = {
    "ai": {
        "bg1": (8, 20, 50), "bg2": (15, 40, 80),
        "accent": (0, 200, 255), "badge_bg": (0, 150, 200),
        "circle": (0, 100, 180), "tag_color": (100, 220, 255),
    },
    "zaitaku": {
        "bg1": (5, 30, 25), "bg2": (10, 55, 45),
        "accent": (0, 210, 150), "badge_bg": (0, 160, 110),
        "circle": (0, 100, 75), "tag_color": (80, 230, 180),
    },
    "income": {
        "bg1": (25, 15, 5), "bg2": (50, 30, 10),
        "accent": (255, 190, 0), "badge_bg": (200, 140, 0),
        "circle": (140, 90, 0), "tag_color": (255, 210, 80),
    },
    "default": {
        "bg1": (20, 10, 45), "bg2": (40, 20, 80),
        "accent": (160, 100, 255), "badge_bg": (110, 60, 210),
        "circle": (80, 40, 160), "tag_color": (190, 140, 255),
    },
}

_THEME_RULES = [
    # (テーマキー, タイトルキーワードリスト, タグキーワードリスト)
    # 「在宅」単体は「在宅副業」でも引っかかるため、複合語のみ対象
    ("ai",      ["AI", "ChatGPT", "GPT", "自動化"],                         ["AI", "ChatGPT", "GPT"]),
    ("zaitaku", ["テレワーク", "在宅ワーク", "リモートワーク", "在宅勤務"],  ["テレワーク", "在宅ワーク", "リモートワーク"]),
    ("income",  ["稼ぐ", "収入", "月5万", "月3万", "収益", "在宅副業"],     ["稼ぐ", "収入", "月5万", "月3万", "収益"]),
]


def _pick_theme(title: str, tags: list[str]) -> dict:
    """タイトルを優先してカラーテーマを選択する。"""
    tag_str = " ".join(tags)
    # タイトルで先にマッチ
    for key, title_kws, _ in _THEME_RULES:
        if any(k in title for k in title_kws):
            return _THEMES[key]
    # タイトルでマッチしなければタグで判定
    for key, _, tag_kws in _THEME_RULES:
        if any(k in tag_str for k in tag_kws):
            return _THEMES[key]
    return _THEMES["default"]


def _get_category_label(title: str, tags: list[str]) -> str:
    """記事のカテゴリラベルを返す。"""
    tag_str = " ".join(tags)
    rules = [
        ("AI活用",      ["AI", "ChatGPT", "GPT"],                                     ["AI", "ChatGPT", "GPT"]),
        ("在宅ワーク",   ["テレワーク", "在宅ワーク", "リモートワーク", "在宅勤務"],   ["テレワーク", "在宅ワーク", "リモートワーク"]),
        ("副業・収入UP", ["稼ぐ", "収入", "月5万", "月3万", "在宅副業"],               ["稼ぐ", "収入", "月5万", "収益"]),
        ("初心者ガイド", ["初心者", "はじめて", "入門"],                                ["初心者", "はじめて", "入門"]),
    ]
    for label, title_kws, tag_kws in rules:
        if any(k in title for k in title_kws):
            return label
    for label, _, tag_kws in rules:
        if any(k in tag_str for k in tag_kws):
            return label
    return "Novlify 厳選"


def generate_cover_image(title: str, tags: list[str], output_path: str) -> str:
    """カバー画像（1280×670px）を生成して output_path に保存する。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow が必要です: pip install Pillow")

    W, H = 1280, 670
    theme = _pick_theme(title, tags)

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # ── 背景グラデーション（上→下）──
    bg1, bg2 = theme["bg1"], theme["bg2"]
    for y in range(H):
        ratio = y / H
        r = int(bg1[0] + (bg2[0] - bg1[0]) * ratio)
        g = int(bg1[1] + (bg2[1] - bg1[1]) * ratio)
        b = int(bg1[2] + (bg2[2] - bg1[2]) * ratio)
        draw.rectangle([(0, y), (W, y + 1)], fill=(r, g, b))

    # ── 右側の装飾: 大きな同心円（テーマカラーで半透明）──
    cx, cy = 1060, 280
    for i, (radius, alpha) in enumerate([(280, 0.18), (210, 0.14), (150, 0.20), (100, 0.28)]):
        circle_color = theme["circle"]
        blend = tuple(
            int(circle_color[j] * alpha + bg1[j] * (1 - alpha))
            for j in range(3)
        )
        draw.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)], fill=blend)

    # ── 右下の装飾: 小さな点パターン ──
    accent = theme["accent"]
    for row in range(4):
        for col in range(5):
            px = W - 160 + col * 22
            py = H - 90 + row * 20
            dot_alpha = 0.25
            dot_color = tuple(int(accent[j] * dot_alpha + bg2[j] * (1 - dot_alpha)) for j in range(3))
            draw.ellipse([(px - 3, py - 3), (px + 3, py + 3)], fill=dot_color)

    # ── 左アクセントバー ──
    draw.rectangle([(0, 0), (8, H)], fill=accent)

    # ── フォント ──
    font_path = _find_japanese_font()
    try:
        if font_path:
            title_font  = ImageFont.truetype(font_path, 62)
            badge_font  = ImageFont.truetype(font_path, 24)
            tag_font    = ImageFont.truetype(font_path, 26)
            brand_font  = ImageFont.truetype(font_path, 22)
        else:
            title_font = badge_font = tag_font = brand_font = ImageFont.load_default()
    except Exception:
        title_font = badge_font = tag_font = brand_font = ImageFont.load_default()

    # ── カテゴリバッジ（タイトル上部の角丸ラベル）──
    category = _get_category_label(title, tags)
    badge_x, badge_y = 40, 60
    try:
        badge_bbox = draw.textbbox((0, 0), category, font=badge_font)
        bw = badge_bbox[2] - badge_bbox[0] + 28
        bh = badge_bbox[3] - badge_bbox[1] + 14
        # 角丸矩形（ラジウス8）
        r8 = 8
        badge_bg = theme["badge_bg"]
        draw.rounded_rectangle(
            [(badge_x, badge_y), (badge_x + bw, badge_y + bh)],
            radius=r8, fill=badge_bg,
        )
        draw.text((badge_x + 14, badge_y + 7), category, font=badge_font, fill=(255, 255, 255))
        title_start_y = badge_y + bh + 24
    except Exception:
        title_start_y = 100

    # ── タイトルのラッピングと描画 ──
    title_max_w = int(W * 0.72)  # 右の円と被らないよう72%幅
    lines   = _wrap_text(draw, title, title_font, title_max_w)
    line_h  = 80
    total_title_h = len(lines) * line_h

    # バッジ下端〜下部区切り線の間で縦中央揃え
    content_top    = title_start_y
    content_bottom = H - 95  # sep_y
    center_y = (content_top + content_bottom) // 2
    title_y0 = center_y - total_title_h // 2

    for i, line in enumerate(lines):
        y = title_y0 + i * line_h
        # テキストシャドウ
        draw.text((42, y + 3), line, font=title_font, fill=(0, 0, 0))
        draw.text((40, y),     line, font=title_font, fill=(255, 255, 255))

    # ── 下部アクセントライン ──
    sep_y = H - 95
    draw.rectangle([(40, sep_y), (W - 40, sep_y + 2)], fill=accent)

    # ── タグ ──
    if tags:
        tag_text = "  ".join(f"#{t}" for t in tags[:3])
        draw.text((40, sep_y + 12), tag_text, font=tag_font, fill=theme["tag_color"])

    # ── ブランド（右寄せ）──
    brand = "Novlify 編集部"
    try:
        bb = draw.textbbox((0, 0), brand, font=brand_font)
        bw = bb[2] - bb[0]
        draw.text((W - bw - 40, sep_y + 14), brand, font=brand_font, fill=(180, 200, 220))
    except Exception:
        draw.text((W - 200, sep_y + 14), brand, font=brand_font, fill=(180, 200, 220))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    print(f"カバー画像生成完了: {output_path}")
    return output_path


def _open_cover_menu(page: Page) -> bool:
    """カバーエリアをホバー→クリックしてサブメニューを開く。
    「画像をアップロード」ボタンが現れたら True を返す（ボタンはまだクリックしない）。
    """
    editor_url = page.url

    # ── カバーボタン候補を探す（ナビゲーションボタンを除外） ──
    btns = page.locator("button").all()
    cover_btn = None
    for btn in btns:
        try:
            if not btn.is_visible(timeout=200):
                continue
            text = (btn.text_content() or "").strip()
            if text:
                continue
            cls = btn.get_attribute("class") or ""
            if "sc-c210b9dd-0" in cls:
                continue  # 既知のナビゲーションボタン → スキップ
            box = btn.bounding_box()
            if not box or not (60 <= box["y"] <= 220):
                continue
            cover_btn = btn
            print(f"[cover] カバーボタン候補: y={box['y']:.0f} cls={cls[:60]}")
            break
        except Exception:
            continue

    if cover_btn is None:
        print("[cover] カバーボタンが見つかりませんでした")
        return False

    # ── 複数の方法でクリックを試みる ──
    for method in ["hover+click", "dispatch", "force", "js"]:
        try:
            if method == "hover+click":
                cover_btn.hover(timeout=3000)
                page.wait_for_timeout(300)
                cover_btn.click(timeout=5000)
            elif method == "dispatch":
                cover_btn.dispatch_event("click")
            elif method == "force":
                cover_btn.click(force=True, timeout=5000)
            elif method == "js":
                handle = cover_btn.element_handle()
                if handle:
                    page.evaluate(
                        "(el) => { el.dispatchEvent(new MouseEvent('mouseenter', {bubbles:true})); "
                        "el.dispatchEvent(new MouseEvent('click', {bubbles:true})); }",
                        handle,
                    )

            page.wait_for_timeout(1200)

            if page.url != editor_url:
                print(f"[cover] ナビゲーション検出({method}) → エディタに戻ります")
                page.goto(editor_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                continue

            if page.locator('button:has-text("画像をアップロード")').count() > 0:
                print(f"[cover] メニュー開きました ({method})")
                return True

            print(f"[cover] {method}: メニュー未表示")
        except Exception as e:
            print(f"[cover] {method} エラー: {e}")

    return False


def upload_cover_image(page: Page, cover_path: str) -> bool:
    """カバー画像をアップロードする。成功したら True を返す。"""
    if not cover_path or not Path(cover_path).exists():
        print("カバー画像ファイルが見つかりません（スキップ）")
        return False

    print(f"カバー画像アップロード試行: {cover_path}")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1500)

    # ── ステップ1: カバーメニューを開く ──
    menu_opened = _open_cover_menu(page)
    if not menu_opened:
        print("[cover] メニューが開けませんでした（スキップ）")
        return False

    # ── ステップ2: expect_file_chooser でファイルを渡す（最も確実な方法） ──
    # "画像をアップロード" クリック → ブラウザのファイル選択ダイアログを Playwright がインターセプト
    # → React の onChange が正常に発火してCDNへアップロードされる
    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.locator('button:has-text("画像をアップロード")').first.click()
        fc_info.value.set_files(cover_path)
        print("[cover] file_chooser でファイルをセット")
        # CDN へのアップロード完了を待つ（ネットワーク遅延考慮）
        page.wait_for_timeout(8000)
        print("✅ カバー画像アップロード成功（file_chooser）")
        return True
    except Exception as e:
        print(f"[cover] file_chooser エラー: {e} → set_input_files にフォールバック")

    # ── フォールバック: set_input_files + React イベント強制発火 ──
    try:
        up_btn = page.locator('button:has-text("画像をアップロード")').first
        if up_btn.is_visible(timeout=2000):
            up_btn.click()
            page.wait_for_timeout(800)

        eyecatch = page.locator("#note-editor-eyecatch-input")
        if eyecatch.count() > 0:
            eyecatch.set_input_files(cover_path)
            handle = eyecatch.element_handle()
            if handle:
                page.evaluate(
                    "(el) => { "
                    "  el.dispatchEvent(new Event('input',  {bubbles: true})); "
                    "  el.dispatchEvent(new Event('change', {bubbles: true})); "
                    "}",
                    handle,
                )
            page.wait_for_timeout(8000)
            print("✅ カバー画像アップロード成功（set_input_files fallback）")
            return True
    except Exception as e:
        print(f"[cover] フォールバックエラー: {e}")

    print("⚠️ カバー画像アップロード失敗（スキップ）")
    return False

NOTE_DRAFTS_DIR = Path("data/note_drafts")
NOTE_POSTED_FILE = Path("data/note_posted.json")

NOTE_EMAIL = os.environ.get("NOTE_EMAIL", "")
NOTE_PASSWORD = os.environ.get("NOTE_PASSWORD", "")
NOTE_SESSION_COOKIE = os.environ.get("NOTE_SESSION_COOKIE", "")

NOTE_LOGIN_URL = "https://note.com/login"
NOTE_NEW_URL = "https://note.com/notes/new"
NOTE_HOME_URL = "https://note.com"


def load_posted() -> list[str]:
    if NOTE_POSTED_FILE.exists():
        data = json.loads(NOTE_POSTED_FILE.read_text(encoding="utf-8"))
        return data.get("posted", [])
    return []


def save_posted(posted: list[str]) -> None:
    NOTE_POSTED_FILE.write_text(
        json.dumps({"posted": posted}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_next_draft() -> tuple[Path, dict] | tuple[None, None]:
    """未投稿のドラフトを古い順に1件返す。"""
    posted = set(load_posted())
    for draft_path in sorted(NOTE_DRAFTS_DIR.glob("*.json")):
        stem = draft_path.stem
        if stem not in posted:
            data = json.loads(draft_path.read_text(encoding="utf-8"))
            return draft_path, data
    return None, None


def authenticate_with_cookie(context: BrowserContext) -> bool:
    """セッションクッキーで認証する。成功した場合 True を返す。

    確認方法: /notes/new に直接アクセスしてログインページへリダイレクトされなければ認証済み。
    """
    if not NOTE_SESSION_COOKIE:
        return False

    print("セッションクッキーで認証中...")

    # note.com は _note_session_v5 を使用（curlで確認済み）
    # domainは .note.com と note.com の両方を設定（ブラウザによって扱いが異なるため）
    for domain in [".note.com", "note.com"]:
        for name in ["_note_session_v5", "_note_session", "note_sid"]:
            try:
                context.add_cookies([{
                    "name": name,
                    "value": NOTE_SESSION_COOKIE,
                    "domain": domain,
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                }])
            except Exception:
                pass

    page = context.new_page()
    try:
        # /notes/new に直接アクセス → ログインページにリダイレクトされなければ認証済み
        page.goto(NOTE_NEW_URL, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        current_url = page.url
        print(f"クッキー確認後URL: {current_url}")

        if "login" in current_url:
            print("クッキーが無効です（ログインページにリダイレクト）。メール/パスワードを試みます...")
            page.close()
            return False

        print("クッキー認証成功")
        page.close()
        return True

    except Exception as e:
        print(f"クッキー認証エラー: {e}")
        try:
            page.close()
        except Exception:
            pass
        return False


def login_with_credentials(page: Page) -> None:
    """メール/パスワードでnote.comにログインする。"""
    print("メール/パスワードでログイン中...")
    page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # メールアドレス入力
    for sel in [
        'input[name="login_id"]',
        'input[type="email"]',
        'input[placeholder*="メール"]',
        'input[placeholder*="mail"]',
        'input[placeholder*="ID"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                loc.fill(NOTE_EMAIL)
                print(f"メール入力: {sel}")
                break
        except Exception:
            continue

    # 「次へ」ボタンがある場合（多段階フォーム対応）
    for next_sel in ['button:has-text("次へ")', 'button:has-text("Next")']:
        try:
            btn = page.locator(next_sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(1500)
                break
        except Exception:
            continue

    # パスワード入力
    for sel in ['input[type="password"]', 'input[name="password"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=4000):
                loc.fill(NOTE_PASSWORD)
                print(f"パスワード入力: {sel}")
                break
        except Exception:
            continue

    # ログインボタンクリック（複数セレクタ＋Enterフォールバック）
    login_clicked = False
    for sel in [
        'button:has-text("ログイン")',
        'button[type="submit"]',
        'button:has-text("Sign in")',
        'button:has-text("続ける")',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print(f"ログインボタン: {sel}")
                login_clicked = True
                break
        except Exception:
            continue

    if not login_clicked:
        page.keyboard.press("Enter")
        print("ログインボタン未検出 → Enterキー送信")

    try:
        page.wait_for_url(lambda url: "login" not in url and "note.com" in url, timeout=15000)
    except PlaywrightTimeoutError:
        page.screenshot(path="note_login_error.png")
        raise RuntimeError(
            "ログインに失敗しました（note_login_error.png を確認）。"
            "NOTE_SESSION_COOKIE を使用した認証方式に切り替えてください。"
        )

    print(f"ログイン成功: {page.url}")


def dismiss_modals(page: Page) -> None:
    """ReactModalPortal など、エディタを覆うモーダルを閉じる。"""
    for attempt in range(4):
        try:
            # ReactModalPortal（react-modal）または dialog/role=dialog を検索
            modal_sel = ".ReactModalPortal, [role='dialog'], [aria-modal='true']"
            if page.locator(modal_sel).count() == 0:
                break

            visible = any(
                page.locator(modal_sel).nth(i).is_visible(timeout=300)
                for i in range(page.locator(modal_sel).count())
            )
            if not visible:
                break

            print(f"[modal] モーダル検出 (試行{attempt + 1}) → 閉じます")

            # ① Escape キーで閉じる
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)

            # ② 閉じるボタンを探してクリック
            for close_sel in [
                'button:has-text("閉じる")',
                'button:has-text("あとで")',
                'button:has-text("キャンセル")',
                'button:has-text("スキップ")',
                '[aria-label="Close"]',
                '[aria-label="閉じる"]',
                '.ReactModalPortal button',
            ]:
                try:
                    btn = page.locator(close_sel).first
                    if btn.is_visible(timeout=400):
                        btn.click()
                        page.wait_for_timeout(500)
                        print(f"[modal] 閉じボタンクリック: {close_sel}")
                        break
                except Exception:
                    continue
        except Exception:
            break


def fill_title(page: Page, title: str) -> None:
    """記事タイトルを入力する。"""
    for sel in [
        'input[placeholder*="タイトル"]',
        'input[placeholder="記事タイトル"]',
        'input[name="title"]',
        'textarea[placeholder*="タイトル"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.fill(title)
                print(f"タイトル入力: {title[:30]}...")
                return
        except Exception:
            continue

    page.fill("input:first-of-type", title)
    print(f"タイトル入力（フォールバック）: {title[:30]}...")


def fill_body(page: Page, body: str) -> None:
    """記事本文をエディタに入力する（ProseMirrorエディタ対応）。"""
    # モーダルが残っていれば閉じる（カバー画像アップロード時に開いた場合など）
    dismiss_modals(page)
    page.wait_for_timeout(500)

    # JS でフォーカス（page.click はモーダルのポインターイベント干渉を受けるため回避）
    page.evaluate("""
    () => {
        const editors = document.querySelectorAll('div[contenteditable="true"]');
        const editor = editors.length > 1 ? editors[editors.length - 1] : editors[0];
        if (editor) editor.focus();
    }
    """)
    page.wait_for_timeout(500)

    safe_body = body.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    page.evaluate(
        f"""
        (function() {{
            const editors = document.querySelectorAll('div[contenteditable="true"]');
            const editor = editors.length > 1 ? editors[editors.length - 1] : editors[0];
            if (!editor) return;
            editor.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, `{safe_body}`);
        }})();
        """
    )
    page.wait_for_timeout(1000)
    print(f"本文入力完了（{len(body)}字）")


def fill_tags(page: Page, tags: list[str]) -> None:
    """ハッシュタグを入力する（最大5件）。"""
    for sel in ['input[placeholder*="タグ"]', 'input[placeholder*="ハッシュタグ"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                for tag in tags[:5]:
                    loc.fill(tag)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(400)
                print(f"タグ入力: {tags[:5]}")
                return
        except Exception:
            continue

    print("タグ入力エリアなし（スキップ）")


def publish(page: Page) -> str:
    """記事を公開してURLを返す。"""
    # STEP1: 「公開設定」ボタンをクリック（エディタ右上）
    publish_settings_clicked = False
    for sel in [
        'button:has-text("公開設定")',
        'button:has-text("公開")',
        '[data-type="publish"]',
        'button[class*="publish"]',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print(f"「公開設定」クリック: {sel}")
                publish_settings_clicked = True
                break
        except Exception:
            continue

    if not publish_settings_clicked:
        print("⚠️ 「公開設定」ボタンが見つかりませんでした")

    # 公開設定ページ（/publish/）への遷移を待つ
    page.wait_for_timeout(4000)
    print(f"公開設定後URL: {page.url}")

    # 診断：ページ上のボタン一覧をログに出力
    try:
        buttons = page.evaluate("""
        () => Array.from(document.querySelectorAll('button, [role="button"], a[class*="button"]'))
            .map(b => b.textContent.trim().replace(/\\s+/g, ' ').substring(0, 60))
            .filter(t => t.length > 0)
        """)
        print(f"ページ上のボタン一覧: {buttons}")
    except Exception as e:
        print(f"ボタン一覧取得エラー: {e}")

    # STEP2: 「公開する」ボタンをクリック（公開設定モーダル内）
    publish_clicked = False
    for sel in [
        'button:has-text("公開する")',
        'button:has-text("投稿する")',
        'button:has-text("公開")',
        '[data-type="confirm-publish"]',
        'button[class*="publish"]',
        'input[type="submit"]',
        'button[type="submit"]',
    ]:
        try:
            # 最後に見つかったボタンを使う（モーダル内のボタンを優先）
            btn = page.locator(sel).last
            if btn.is_visible(timeout=4000):
                btn.click()
                print(f"「公開する」クリック: {sel}")
                publish_clicked = True
                break
        except Exception:
            continue

    if not publish_clicked:
        print("⚠️ 「公開する」ボタンが見つかりませんでした。スクリーンショットを保存します。")
        page.screenshot(path="note_publish_error.png")

    # 公開完了・URLが確定するまで待つ
    page.wait_for_timeout(5000)
    final_url = page.url
    print(f"最終URL: {final_url}")

    # note.com の実際の公開URLを取得する
    # 公開後は /like_reaction_setting などにリダイレクトされる場合があるため
    # editor.note.com のノートIDを使って公開URLを構築する
    note_id_match = re.search(r'/notes/(n[a-z0-9]+)/', final_url)
    if not note_id_match:
        # publish ページのURLからもIDを探す
        note_id_match = re.search(r'/notes/(n[a-z0-9]+)', final_url)
    if note_id_match:
        note_id = note_id_match.group(1)
        public_url = f"https://note.com/novlify/n/{note_id}"
        print(f"公開URL: {public_url}")
        return public_url

    return final_url


def post_to_note(title: str, body: str, tags: list[str], cover_path: str = "") -> str:
    """Playwrightを使ってnote.comに記事を投稿し、URLを返す。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # クッキー認証を試みる
        cookie_ok = authenticate_with_cookie(context)

        page = context.new_page()
        try:
            if not cookie_ok:
                # メール/パスワードでログイン
                if not NOTE_EMAIL or not NOTE_PASSWORD:
                    raise RuntimeError(
                        "NOTE_SESSION_COOKIE または NOTE_EMAIL+NOTE_PASSWORD が必要です"
                    )
                login_with_credentials(page)

            print("新規記事ページへ移動...")
            page.goto(NOTE_NEW_URL, wait_until="domcontentloaded")
            # editor.note.com へのリダイレクトを待つ（note_id がURLに含まれるまで）
            try:
                page.wait_for_url(
                    lambda url: "editor.note.com" in url or "/notes/n" in url,
                    timeout=15000,
                )
            except Exception:
                pass
            page.wait_for_timeout(2000)  # エディタ初期化待ち
            print(f"エディタURL: {page.url}")

            # エディタURLを記録（カバー画像アップロードで誤ナビゲーションした場合に備える）
            editor_url = page.url

            # ① カバー画像アップロード（タイトル入力の前に実施）
            if cover_path:
                upload_cover_image(page, cover_path)
                page.wait_for_timeout(1000)

            # カバー画像アップロードで誤ってページが移動していたらエディタに戻る
            if page.url != editor_url:
                print(f"[警告] ページが移動しました ({page.url}) → エディタに戻ります")
                page.goto(editor_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

            # モーダルが開いていることがある → 必ず閉じる
            dismiss_modals(page)
            page.wait_for_timeout(500)

            fill_title(page, title)
            page.wait_for_timeout(500)
            fill_body(page, body)
            page.wait_for_timeout(500)
            fill_tags(page, tags)
            page.wait_for_timeout(500)

            note_url = publish(page)
            print(f"投稿URL: {note_url}")

        except PlaywrightTimeoutError as e:
            page.screenshot(path="note_post_error.png")
            raise RuntimeError(f"タイムアウトエラー: {e}") from e
        finally:
            browser.close()

    return note_url


def main() -> None:
    if not NOTE_SESSION_COOKIE and (not NOTE_EMAIL or not NOTE_PASSWORD):
        print("ERROR: NOTE_SESSION_COOKIE か NOTE_EMAIL+NOTE_PASSWORD を設定してください")
        sys.exit(1)

    draft_path, draft_data = get_next_draft()
    if draft_path is None:
        print("投稿待ちのドラフトがありません")
        sys.exit(0)

    stem = draft_path.stem
    print(f"投稿するドラフト: {stem}")
    print(f"タイトル: {draft_data['title']}")

    # カバー画像を自動生成
    NOTE_COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cover_path = str(NOTE_COVERS_DIR / f"{stem}.png")
    try:
        generate_cover_image(
            title=draft_data["title"],
            tags=draft_data.get("tags", []),
            output_path=cover_path,
        )
    except Exception as e:
        print(f"⚠️ カバー画像生成失敗（スキップ）: {e}")
        cover_path = ""

    try:
        note_url = post_to_note(
            title=draft_data["title"],
            body=draft_data["body"],
            tags=draft_data.get("tags", []),
            cover_path=cover_path,
        )
    except Exception as e:
        print(f"ERROR: 投稿に失敗しました: {e}")
        sys.exit(1)

    posted = load_posted()
    posted.append(stem)
    save_posted(posted)

    draft_data["note_url"] = note_url
    draft_data["posted_at"] = datetime.now(timezone.utc).isoformat()
    draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 投稿完了！")
    print(f"   URL: {note_url}")


if __name__ == "__main__":
    main()

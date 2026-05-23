"""
note.comへの記事投稿スクリプト（Playwright使用）。

data/note_drafts/ 内の未投稿ドラフトを古い順に1件取得してnote.comに投稿する。
投稿成功後に data/note_posted.json を更新してドラフトのJSONにURLを記録する。

必要な環境変数:
  NOTE_EMAIL    : noteアカウントのメールアドレス
  NOTE_PASSWORD : noteアカウントのパスワード
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeoutError

NOTE_DRAFTS_DIR = Path("data/note_drafts")
NOTE_POSTED_FILE = Path("data/note_posted.json")

NOTE_EMAIL = os.environ.get("NOTE_EMAIL", "")
NOTE_PASSWORD = os.environ.get("NOTE_PASSWORD", "")

NOTE_LOGIN_URL = "https://note.com/login"
NOTE_NEW_URL = "https://note.com/notes/new"


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


def login(page: Page) -> None:
    """note.comにログインする（多段階フォーム・SPA対応）。"""
    print("note.com ログイン中...")
    page.goto(NOTE_LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # --- メールアドレス入力 ---
    email_filled = False
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
                print(f"メール入力完了: {sel}")
                email_filled = True
                break
        except Exception:
            continue

    if not email_filled:
        page.screenshot(path="note_login_error.png")
        raise RuntimeError("メールアドレス入力欄が見つかりませんでした（note_login_error.png を確認）")

    # --- 「次へ」ボタンがある場合（多段階フォーム）は先にクリック ---
    for next_sel in [
        'button:has-text("次へ")',
        'button:has-text("Next")',
    ]:
        try:
            btn = page.locator(next_sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                print(f"「次へ」ボタンクリック")
                page.wait_for_timeout(1500)
                break
        except Exception:
            continue

    # --- パスワード入力 ---
    password_filled = False
    for sel in ['input[type="password"]', 'input[name="password"]']:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=4000):
                loc.fill(NOTE_PASSWORD)
                print(f"パスワード入力完了: {sel}")
                password_filled = True
                break
        except Exception:
            continue

    if not password_filled:
        page.screenshot(path="note_login_error.png")
        raise RuntimeError("パスワード入力欄が見つかりませんでした（note_login_error.png を確認）")

    # --- ログインボタンクリック（複数セレクタ + Enterキーフォールバック）---
    login_clicked = False
    for sel in [
        'button[type="submit"]',
        'button:has-text("ログイン")',
        'button:has-text("Sign in")',
        'button:has-text("続ける")',
        'button:has-text("送信")',
        'input[type="submit"]',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print(f"ログインボタンクリック: {sel}")
                login_clicked = True
                break
        except Exception:
            continue

    if not login_clicked:
        # フォールバック: Enterキーで送信
        page.keyboard.press("Enter")
        print("ログインボタン未検出 → Enterキーで送信")

    # --- ログイン完了待機（URLが /login 以外になる） ---
    try:
        page.wait_for_url(lambda url: "login" not in url and "note.com" in url, timeout=15000)
    except PlaywrightTimeoutError:
        page.screenshot(path="note_login_error.png")
        raise RuntimeError(
            "ログインに失敗しました（note_login_error.png を確認）。"
            "NOTE_EMAIL / NOTE_PASSWORD が正しいか確認してください。"
        )

    print(f"ログイン成功: {page.url}")


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
                print(f"タイトル入力完了: {title[:30]}...")
                return
        except Exception:
            continue

    # フォールバック
    page.fill("input:first-of-type", title)
    print(f"タイトル入力（フォールバック）: {title[:30]}...")


def fill_body(page: Page, body: str) -> None:
    """記事本文をエディタに入力する（ProseMirrorエディタ対応）。"""
    page.click('div[contenteditable="true"]')
    page.wait_for_timeout(500)

    # execCommand でテキストを挿入（ProseMirrorと互換性あり）
    safe_body = body.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    page.evaluate(
        f"""
        (function() {{
            const editors = document.querySelectorAll('div[contenteditable="true"]');
            // 本文エディタは通常2番目以降（1番目はタイトル）
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
    for sel in [
        'input[placeholder*="タグ"]',
        'input[placeholder*="ハッシュタグ"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                for tag in tags[:5]:
                    loc.fill(tag)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(400)
                print(f"タグ入力完了: {tags[:5]}")
                return
        except Exception:
            continue

    print("タグ入力エリアが見つかりませんでした（スキップ）")


def publish(page: Page) -> str:
    """記事を公開して投稿後のURLを返す。"""
    # 公開設定ボタンをクリック
    for sel in [
        'button:has-text("公開設定")',
        'button:has-text("公開")',
        '[data-type="publish"]',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=3000):
                btn.click()
                print("「公開設定」ボタンクリック")
                break
        except Exception:
            continue

    page.wait_for_timeout(2000)

    # 「公開する」確認ボタン（モーダル内）
    for sel in [
        'button:has-text("公開する")',
        'button:has-text("投稿する")',
        '[data-type="confirm-publish"]',
    ]:
        try:
            btn = page.locator(sel).last
            if btn.is_visible(timeout=3000):
                btn.click()
                print("「公開する」ボタンクリック")
                break
        except Exception:
            continue

    page.wait_for_timeout(4000)
    note_url = page.url
    print(f"投稿URL: {note_url}")
    return note_url


def post_to_note(title: str, body: str, tags: list[str]) -> str:
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
        )
        page = context.new_page()

        try:
            login(page)

            print("新規記事ページへ移動中...")
            page.goto(NOTE_NEW_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            fill_title(page, title)
            page.wait_for_timeout(500)

            fill_body(page, body)
            page.wait_for_timeout(500)

            fill_tags(page, tags)
            page.wait_for_timeout(500)

            note_url = publish(page)

        except PlaywrightTimeoutError as e:
            page.screenshot(path="note_post_error.png")
            raise RuntimeError(f"タイムアウトエラー（note_post_error.png を確認）: {e}") from e
        finally:
            browser.close()

    return note_url


def main() -> None:
    if not NOTE_EMAIL or not NOTE_PASSWORD:
        print("ERROR: 環境変数 NOTE_EMAIL と NOTE_PASSWORD を設定してください")
        sys.exit(1)

    draft_path, draft_data = get_next_draft()
    if draft_path is None:
        print("投稿待ちのドラフトがありません")
        sys.exit(0)

    stem = draft_path.stem
    print(f"投稿するドラフト: {stem}")
    print(f"タイトル: {draft_data['title']}")

    try:
        note_url = post_to_note(
            title=draft_data["title"],
            body=draft_data["body"],
            tags=draft_data.get("tags", []),
        )
    except Exception as e:
        print(f"ERROR: 投稿に失敗しました: {e}")
        sys.exit(1)

    # 投稿済みを記録
    posted = load_posted()
    posted.append(stem)
    save_posted(posted)

    # ドラフトにURLと投稿日時を記録
    draft_data["note_url"] = note_url
    draft_data["posted_at"] = datetime.now(timezone.utc).isoformat()
    draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 投稿完了！")
    print(f"   URL: {note_url}")
    print(f"   記録: {NOTE_POSTED_FILE}")


if __name__ == "__main__":
    main()

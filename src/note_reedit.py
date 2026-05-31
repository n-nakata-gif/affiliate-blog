"""
公開済み note 記事の一括修正スクリプト。

【目的】
サムネイル機能と本文HTML化の修正前に投稿された記事は、以下の問題を抱えている:
  - サムネイル（見出し画像）が無い
  - 本文の Markdown 記法（## 見出し / **太字** / [リンク](URL)）が
    そのまま生テキストで表示され、特に導線リンクがクリック不可
    → ブログへの流入＝アフィリエイト収益が機能していない

このスクリプトは data/note_drafts/ の各記事のうち「投稿済み（note_url あり）」
かつ「未修正」のものを、新しい投稿ロジック（note_post.reedit_note）で開き直し、
サムネイル付与＋本文HTML化＋再公開する。

【実行】
  python src/note_reedit.py            # 未修正を全件処理
  REEDIT_LIMIT=1 python src/note_reedit.py   # 1件だけ処理（テスト用）

【安全装置】
  - 修正済みは data/note_reedited.json に記録し、二重修正を防ぐ
  - 1件ずつ処理し、失敗しても他記事に影響しない
  - REEDIT_LIMIT で処理件数を制限できる（まず1件で検証する運用）
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from note_post import (
    NOTE_COVERS_DIR,
    NOTE_DRAFTS_DIR,
    NOTE_EMAIL,
    NOTE_PASSWORD,
    NOTE_SESSION_COOKIE,
    generate_cover_image,
    reedit_note,
)

REEDITED_FILE = Path("data/note_reedited.json")


def load_reedited() -> list[str]:
    if REEDITED_FILE.exists():
        data = json.loads(REEDITED_FILE.read_text(encoding="utf-8"))
        return data.get("reedited", [])
    return []


def save_reedited(reedited: list[str]) -> None:
    REEDITED_FILE.write_text(
        json.dumps({"reedited": reedited}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_note_id(note_url: str) -> str | None:
    """note_url からノートID（n...）を抽出する。"""
    if not note_url:
        return None
    for pattern in [r"/notes/(n[a-z0-9]+)", r"/n/(n[a-z0-9]+)"]:
        m = re.search(pattern, note_url)
        if m:
            return m.group(1)
    return None


def get_articles_to_reedit() -> list[tuple[Path, dict, str]]:
    """修正対象（投稿済み・未修正）の記事リストを古い順に返す。"""
    reedited = set(load_reedited())
    targets: list[tuple[Path, dict, str]] = []
    for draft_path in sorted(NOTE_DRAFTS_DIR.glob("*.json")):
        stem = draft_path.stem
        if stem in reedited:
            continue
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        note_url = data.get("note_url", "")
        note_id = extract_note_id(note_url)
        if not note_id:
            continue  # 未投稿（note_url なし）はスキップ
        targets.append((draft_path, data, note_id))
    return targets


def main() -> None:
    if not NOTE_SESSION_COOKIE and (not NOTE_EMAIL or not NOTE_PASSWORD):
        print("ERROR: NOTE_SESSION_COOKIE か NOTE_EMAIL+NOTE_PASSWORD を設定してください")
        sys.exit(1)

    limit = int(os.environ.get("REEDIT_LIMIT", "0"))  # 0 = 無制限
    targets = get_articles_to_reedit()

    if not targets:
        print("修正対象の記事がありません（全件修正済み）")
        sys.exit(0)

    if limit > 0:
        targets = targets[:limit]

    print(f"修正対象: {len(targets)}件（limit={limit or '無制限'}）")
    NOTE_COVERS_DIR.mkdir(parents=True, exist_ok=True)

    reedited = load_reedited()
    success = 0
    for draft_path, data, note_id in targets:
        stem = draft_path.stem
        title = data["title"]
        print("\n" + "=" * 60)
        print(f"修正開始: {stem} / note_id={note_id}")
        print(f"タイトル: {title}")

        # カバー画像を生成
        cover_path = str(NOTE_COVERS_DIR / f"{stem}.png")
        try:
            generate_cover_image(
                title=title,
                tags=data.get("tags", []),
                output_path=cover_path,
            )
        except Exception as e:
            print(f"⚠️ カバー画像生成失敗（サムネイルなしで続行）: {e}")
            cover_path = ""

        # 再編集（サムネイル付与＋本文HTML化＋再公開）
        try:
            note_url = reedit_note(
                note_id=note_id,
                title=title,
                body=data["body"],
                tags=data.get("tags", []),
                cover_path=cover_path,
            )
            reedited.append(stem)
            save_reedited(reedited)

            data["reedited_at"] = datetime.now(timezone.utc).isoformat()
            draft_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            success += 1
            print(f"✅ 修正完了: {stem} → {note_url}")
        except Exception as e:
            print(f"❌ 修正失敗: {stem}: {e}")
            # 失敗しても他記事に進む

    print("\n" + "=" * 60)
    print(f"完了: {success}/{len(targets)}件を修正しました")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
backfill_thumbnails.py
既存のブログ記事すべてにサムネイル画像を一括生成してリポジトリにプッシュする。

実行:
  GH_TOKEN=xxx python3 src/backfill_thumbnails.py [--dry-run]

オプション:
  --dry-run   画像を local に生成するが GitHub へのプッシュはしない
  --genre     特定ジャンルのみ処理 (例: --genre gourmet)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

# プロジェクトルート基準でパスを解決
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

from generate_thumbnail import create_thumbnail, GENRE_THEMES
from generate import push_binary_file, REPO, BRANCH

CONTENT_DIR = PROJECT_ROOT / "src" / "content" / "blog"
OUTPUT_DIR  = PROJECT_ROOT / "public" / "thumbnails"

KNOWN_GENRES = set(GENRE_THEMES.keys())


def extract_frontmatter(text: str) -> dict[str, str]:
    """記事の frontmatter から title / genre を抽出"""
    result: dict[str, str] = {}
    m = re.search(r'^---\n([\s\S]*?)\n---', text)
    if not m:
        return result
    for line in m.group(1).splitlines():
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"').strip("'")
            result[key] = val
    return result


def guess_genre(slug: str) -> str:
    """ファイル名のプレフィクスからジャンルを推測"""
    for genre in KNOWN_GENRES:
        if slug.startswith(genre):
            return genre
    return "business"


def main() -> None:
    parser = argparse.ArgumentParser(description="既存記事のサムネイルを一括生成")
    parser.add_argument("--dry-run", action="store_true", help="プッシュせずローカル生成のみ")
    parser.add_argument("--genre",   default=None, help="対象ジャンルを絞る")
    args = parser.parse_args()

    gh_token = os.environ.get("GH_TOKEN") if not args.dry_run else None
    if not args.dry_run and not gh_token:
        print("ERROR: GH_TOKEN が未設定です。--dry-run を使うか環境変数を設定してください。", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(CONTENT_DIR.glob("*.md"))
    print(f"対象記事: {len(md_files)} 件")

    ok = skip = err = 0

    for md_path in md_files:
        slug = md_path.stem

        # --genre フィルタ
        genre = guess_genre(slug)
        if args.genre and genre != args.genre:
            continue

        # サムネイルが既にローカルに存在するかチェック（dry-run 時）
        local_out = OUTPUT_DIR / f"{slug}.png"
        if args.dry_run and local_out.exists():
            print(f"  [SKIP] {slug} (already exists locally)")
            skip += 1
            continue

        # タイトルを frontmatter から取得
        try:
            text  = md_path.read_text(encoding="utf-8")
            fm    = extract_frontmatter(text)
            title = fm.get("title") or slug
        except Exception as e:
            print(f"  [ERR]  {slug}: frontmatter 読み取り失敗 - {e}")
            err += 1
            continue

        # サムネイル生成
        try:
            if args.dry_run:
                out_path = create_thumbnail(title, genre, slug, OUTPUT_DIR)
                print(f"  [DRY]  {slug} → {out_path}")
                ok += 1
            else:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    thumb = create_thumbnail(title, genre, slug, Path(tmp_dir))
                    thumb_bytes = thumb.read_bytes()

                repo_path = f"public/thumbnails/{slug}.png"
                push_binary_file(gh_token, repo_path, thumb_bytes, f"auto: add thumbnail {slug}")
                print(f"  [OK]   {slug} → {repo_path}")
                ok += 1

        except Exception as e:
            print(f"  [ERR]  {slug}: {e}")
            err += 1

    print(f"\n完了: OK={ok}  SKIP={skip}  ERR={err}")


if __name__ == "__main__":
    main()

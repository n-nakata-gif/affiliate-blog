"""
Pinterest スケジュール投稿スクリプト
毎日 20:00 JST（GitHub Actions: 11:00 UTC）に実行。

当日または未投稿の gadget / gourmet / travel 記事を
縦長画像＋Claude生成説明文でPinterestに投稿する。

投稿済みの記録を data/pinterest_posted.json に保存し、
二重投稿を防止する。

必要なSecrets:
  PINTEREST_ACCESS_TOKEN : Pinterest OAuth2 アクセストークン
  UNSPLASH_API_KEY       : Unsplash API キー（縦長画像取得用）
  ANTHROPIC_API_KEY      : Claude API キー（説明文生成用）
"""

from __future__ import annotations
import json, os, re, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# generate.py のユーティリティを再利用
sys.path.insert(0, str(Path(__file__).parent))
from generate import (
    extract_title,
    extract_description,
    extract_first_image,
    REPO,
    BRANCH,
    BLOG_URL,
    gh,
    push_file,
)
from pinterest_post import post_to_pinterest, PINTEREST_GENRES

JST = timezone(timedelta(hours=9))
BLOG_DIR = Path("src/content/blog")
POSTED_LOG = Path("data/pinterest_posted.json")

# ジャンル判定（ファイル名ベース）
GENRE_PATTERNS = {
    "travel":  ["travel"],
    "gourmet": ["gourmet"],
    "gadget":  ["gadget", "product"],
}


def load_posted_log() -> set:
    """投稿済みファイル名の集合を返す"""
    if POSTED_LOG.exists():
        try:
            data = json.loads(POSTED_LOG.read_text(encoding="utf-8"))
            return set(data.get("posted", []))
        except Exception:
            pass
    return set()


def save_posted_log(posted: set, gh_token: str) -> None:
    """投稿済みログをローカル保存 & GitHub にプッシュ"""
    POSTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"posted": sorted(posted)}, ensure_ascii=False, indent=2)
    POSTED_LOG.write_text(content, encoding="utf-8")
    try:
        push_file(gh_token, str(POSTED_LOG), content,
                  f"auto: pinterest posted log update")
        print(f"[Schedule] 投稿ログをGitHubへ保存: {POSTED_LOG}")
    except Exception as e:
        print(f"[Schedule] ログ保存失敗（ローカルのみ）: {e}")


def detect_genre(filename: str) -> str | None:
    """ファイル名からジャンルを判定（Pinterest対象ジャンルのみ）"""
    name = filename.lower()
    for genre, patterns in GENRE_PATTERNS.items():
        if any(p in name for p in patterns):
            return genre
    return None


def find_target_articles(mode: str = "today") -> list[tuple[str, str, str]]:
    """
    投稿対象記事を返す。各要素は (filepath, genre, slug)。

    mode:
      "today"  : 本日付の記事のみ（デフォルト）
      "all"    : 未投稿の全記事
      "YYYYMMDD": 指定日付の記事
    """
    today_jst = datetime.now(JST).strftime("%Y%m%d")

    results = []
    for md_file in sorted(BLOG_DIR.glob("*.md")):
        name = md_file.name
        # 自動生成記事のみ（_20XXXXXX.md 形式）
        m = re.search(r'_(\d{8})\.md$', name)
        if not m:
            continue

        date_str = m.group(1)
        genre = detect_genre(name)
        if genre is None:
            continue  # Pinterest対象外ジャンル

        if mode == "today" and date_str != today_jst:
            continue
        elif mode not in ("today", "all") and date_str != mode:
            continue

        slug = md_file.stem  # e.g. "gadget_20260504"
        results.append((str(md_file), genre, slug))

    return results


def run_schedule(mode: str = "today", force: bool = False,
                 dry_run: bool = False) -> None:
    gh_token = os.environ.get("GH_TOKEN", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    unsplash_key = os.environ.get("UNSPLASH_API_KEY", "")

    posted = load_posted_log()
    targets = find_target_articles(mode)

    if not targets:
        print(f"[Schedule] 投稿対象記事なし（mode={mode}）")
        return

    print(f"[Schedule] 投稿対象: {len(targets)}件")
    newly_posted = set()

    for filepath, genre, slug in targets:
        if not force and slug in posted:
            print(f"[Schedule] スキップ（投稿済み）: {slug}")
            continue

        article_body = Path(filepath).read_text(encoding="utf-8")
        title = extract_title(article_body)
        description = extract_description(article_body)
        # slugからURLを構築 (例: gadget_20260504 → /blog/gadget_20260504/)
        link = f"{BLOG_URL}/blog/{slug}/"
        image_url = extract_first_image(article_body)

        print(f"\n[Schedule] ▶ {slug} ({genre})")
        if dry_run:
            print(f"  [DRY RUN] title={title[:40]}... link={link}")
            newly_posted.add(slug)
            continue

        success = post_to_pinterest(
            title=title,
            description=description,
            link=link,
            image_url=image_url,
            genre=genre,
            article_body=article_body,
            anthropic_key=anthropic_key,
            unsplash_key=unsplash_key,
        )
        if success:
            newly_posted.add(slug)
        else:
            print(f"[Schedule] 投稿失敗: {slug}")

    if newly_posted:
        posted.update(newly_posted)
        save_posted_log(posted, gh_token)
        print(f"\n[Schedule] 完了: {len(newly_posted)}件を投稿")
    else:
        print("\n[Schedule] 新規投稿なし")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pinterest スケジュール投稿")
    parser.add_argument(
        "--mode",
        default="today",
        help='投稿対象モード: "today"（本日）, "all"（全未投稿）, "YYYYMMDD"（指定日）'
    )
    parser.add_argument("--force", action="store_true", help="投稿済みも再投稿する")
    parser.add_argument("--dry-run", action="store_true", help="実際には投稿しない")
    args = parser.parse_args()
    run_schedule(mode=args.mode, force=args.force, dry_run=args.dry_run)

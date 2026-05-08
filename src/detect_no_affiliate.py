"""
アフィリエイトリンク未挿入記事の検出スクリプト
quality_check.yml から呼び出される。

検出条件（すべて満たすもの）:
  1. draft でない（公開済み）
  2. pubDate から 30 日以上経過
  3. 本文にアフィリエイトリンクが存在しない
  4. affiliate_added フラグが未設定（処理済みでない）

結果を data/rewrite_queue.json に書き出し、
GitHub Actions 環境では rewrite_job.yml を自動トリガーする。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"
DATA_DIR = Path(__file__).parent.parent / "data"
QUEUE_FILE = DATA_DIR / "rewrite_queue.json"

DAYS_THRESHOLD = 30

# 検出対象のアフィリエイトリンクパターン
AFFILIATE_PATTERNS = [
    r"px\.a8\.net",
    r"ck\.jp\.ap\.valuecommerce\.com",
    r"tag=nexigen22-22",
    r"amazon\.co\.jp",
    r"rakuten\.co\.jp",
]

# ジャンル推定キーワード（ファイル名・タイトル・タグから判定）
GENRE_KEYWORDS = {
    "business":   ["副業", "ビジネス", "フリーランス", "在宅", "起業", "転職", "business"],
    "gadget":     ["ガジェット", "デスク", "スマホ", "家電", "PC", "grinder", "desk", "protein",
                   "コーヒー", "supplement", "setup", "gadget"],
    "investment": ["投資", "NISA", "iDeCo", "資産", "株", "積立", "investment"],
    "travel":     ["旅行", "ホテル", "宿", "観光", "旅館", "travel"],
    "gourmet":    ["グルメ", "食", "レシピ", "料理", "レストラン", "gourmet"],
}


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    yaml_block = content[3:end].strip()
    body = content[end + 4:].strip()
    meta: dict = {}
    for line in yaml_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


def has_affiliate_link(body: str) -> bool:
    for pattern in AFFILIATE_PATTERNS:
        if re.search(pattern, body):
            return True
    return False


def is_old_enough(pub_date_str: str) -> bool:
    try:
        pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=JST)
        return (datetime.now(JST) - pub_date).days >= DAYS_THRESHOLD
    except Exception:
        return False


def guess_genre(slug: str, title: str, tags_str: str) -> str:
    combined = (slug + " " + title + " " + tags_str).lower()
    # ファイル名プレフィックスが最優先
    for genre in ["business", "gadget", "investment", "travel", "gourmet"]:
        if combined.startswith(genre + "_") or combined.startswith(genre + " "):
            return genre
    # キーワードマッチ
    for genre, keywords in GENRE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in combined:
                return genre
    return "gadget"  # デフォルト


def detect() -> list[dict]:
    """アフィリエイトリンクなし記事を検出して返す"""
    targets = []
    for path in sorted(BLOG_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        # draft はスキップ
        if meta.get("draft", "").lower() == "true":
            continue
        # 処理済みはスキップ
        if meta.get("affiliate_added", "").lower() == "true":
            continue

        pub_date = meta.get("pubDate", "")
        if not pub_date or not is_old_enough(pub_date):
            continue

        if has_affiliate_link(body):
            continue

        slug = path.stem
        title = meta.get("title", "（タイトル未設定）")
        tags = meta.get("tags", "")
        genre = guess_genre(slug, title, tags)

        targets.append({
            "slug": slug,
            "file": path.name,
            "title": title,
            "tags": tags,
            "pubDate": pub_date,
            "genre": genre,
            "status": "pending",
            "detected_at": datetime.now(JST).isoformat(),
        })

    return targets


def load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return data.get("queue", [])
    except Exception:
        return []


def save_queue(new_targets: list[dict]) -> int:
    DATA_DIR.mkdir(exist_ok=True)
    existing = load_queue()
    existing_slugs = {item["slug"] for item in existing}
    added = [t for t in new_targets if t["slug"] not in existing_slugs]
    combined = existing + added
    QUEUE_FILE.write_text(json.dumps({
        "updated_at": datetime.now(JST).isoformat(),
        "total": len(combined),
        "pending": sum(1 for i in combined if i.get("status") == "pending"),
        "queue": combined,
    }, ensure_ascii=False, indent=2))
    print("キュー保存: " + str(QUEUE_FILE) + " 合計" + str(len(combined)) + "件（新規" + str(len(added)) + "件）")
    return len(added)


def trigger_rewrite_job() -> None:
    """GitHub Actions 環境で rewrite_job.yml をトリガーする"""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY 未設定のためトリガースキップ")
        return
    print("rewrite_job.yml をトリガー中... (" + repo + ")")
    result = subprocess.run(
        ["gh", "workflow", "run", "rewrite_job.yml", "--repo", repo],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("rewrite_job トリガー成功")
    else:
        print("rewrite_job トリガー失敗（GitHub Actions UI から手動実行してください）")
        print("  " + result.stderr.strip())


if __name__ == "__main__":
    print("アフィリエイトなし記事を検出中...")
    targets = detect()
    print("検出件数: " + str(len(targets)) + " 件")
    for t in targets:
        print("  [" + t["genre"] + "] " + t["file"] + ": " + t["title"][:35])

    if targets:
        added = save_queue(targets)
        # GitHub Actions 内かつ新規追加があればリライトジョブを起動
        if added > 0 and os.environ.get("GITHUB_ACTIONS"):
            trigger_rewrite_job()
    else:
        print("対象記事なし（すべての記事にアフィリエイトリンクあり）")

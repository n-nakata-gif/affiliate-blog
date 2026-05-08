"""
アフィリエイトセクション自動挿入スクリプト
data/rewrite_queue.json を読み込み、pending 記事の本文末尾に
generate.py の build_affiliate_section() を呼び出してセクションを追記する。

【仕様書との差異】
  仕様: frontmatter の affiliate_products フィールドのみ追記
  実装: 本文末尾にアフィリエイトセクションを追記
  理由: 当ブログの Astro テンプレート（Layout.astro）は affiliate_products
        フロントマターを読まないため、frontmatter のみの変更では
        記事ページに何も表示されない。generate.py と同じ方式が唯一機能する。
        フロントマターには affiliate_added: "true" を追記して処理済みをマーク。

処理上限: 1実行あたり最大 MAX_BATCH = 3 記事（API負荷・CI時間対策）
エラー: スキップして次の記事へ（止まらない設計）
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"
DATA_DIR = Path(__file__).parent.parent / "data"
QUEUE_FILE = DATA_DIR / "rewrite_queue.json"
MAX_BATCH = 3

# generate.py から build_affiliate_section をインポート
sys.path.insert(0, str(Path(__file__).parent))
from generate import build_affiliate_section  # noqa: E402


def parse_frontmatter(content: str) -> tuple[dict, str, str]:
    """(meta dict, body str, frontmatter_block str) を返す"""
    if not content.startswith("---"):
        return {}, content, ""
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content, ""
    fm_raw = content[:end + 4]   # "---\n...\n---" まで
    yaml_block = content[3:end].strip()
    body = content[end + 4:].strip()
    meta: dict = {}
    for line in yaml_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body, fm_raw


def inject_affiliate_flag(fm_raw: str) -> str:
    """frontmatter の closing --- の直前に affiliate_added: "true" を挿入する"""
    if fm_raw.rstrip().endswith("---"):
        inner = fm_raw.rstrip()[:-3].rstrip()
        return inner + '\naffiliate_added: "true"\n---'
    return fm_raw + '\naffiliate_added: "true"\n---'


def process_article(item: dict) -> bool:
    """1記事にアフィリエイトセクションを追記。成功したら True を返す。"""
    path = BLOG_DIR / item["file"]
    if not path.exists():
        print("  ファイルが見つかりません: " + item["file"])
        return False

    content = path.read_text(encoding="utf-8")
    meta, body, fm_raw = parse_frontmatter(content)

    if not fm_raw:
        print("  frontmatter が解析できません: " + item["file"])
        return False

    # 処理済みチェック（二重処理防止）
    if meta.get("affiliate_added", "").lower() == "true":
        print("  スキップ（処理済み）: " + item["file"])
        return False

    genre = item.get("genre", "gadget")
    keyword = meta.get("title", "")

    try:
        aff_section = build_affiliate_section(
            genre=genre,
            keyword=keyword,
            products=[],
            amazon_products=None,
            rakuten_aff_id="",
            rakuten_products=None,
            a8mat="",
        )
    except Exception as e:
        print("  アフィリエイトセクション生成エラー: " + str(e))
        return False

    # frontmatter に affiliate_added フラグを追記
    new_fm = inject_affiliate_flag(fm_raw)
    new_content = new_fm + "\n\n" + body + aff_section

    path.write_text(new_content, encoding="utf-8")
    print("  ✅ 更新: " + item["file"])
    return True


def load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        print("rewrite_queue.json が存在しません")
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        return data.get("queue", [])
    except Exception as e:
        print("キュー読み込みエラー: " + str(e))
        return []


def save_queue(queue: list[dict]) -> None:
    QUEUE_FILE.write_text(json.dumps({
        "updated_at": datetime.now(JST).isoformat(),
        "total": len(queue),
        "pending": sum(1 for i in queue if i.get("status") == "pending"),
        "queue": queue,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    queue = load_queue()
    pending = [item for item in queue if item.get("status") == "pending"]

    if not pending:
        print("処理対象なし（pending キューが空）")
        sys.exit(0)

    batch = pending[:MAX_BATCH]
    print("pending: " + str(len(pending)) + "件 → 今回処理: " + str(len(batch)) + "件（上限 " + str(MAX_BATCH) + "）")

    for item in batch:
        print("\n処理中: [" + item.get("genre", "?") + "] " + item.get("title", "")[:45])
        try:
            success = process_article(item)
            item["status"] = "done" if success else "error"
            item["processed_at"] = datetime.now(JST).isoformat()
        except Exception as e:
            print("  予期せぬエラー（スキップ）: " + str(e))
            item["status"] = "error"
            item["processed_at"] = datetime.now(JST).isoformat()

    save_queue(queue)

    done = sum(1 for i in batch if i.get("status") == "done")
    error = sum(1 for i in batch if i.get("status") == "error")
    remaining = sum(1 for i in queue if i.get("status") == "pending")
    print("\n--- 完了 ---")
    print("成功: " + str(done) + "件 / エラー: " + str(error) + "件 / 残り pending: " + str(remaining) + "件")

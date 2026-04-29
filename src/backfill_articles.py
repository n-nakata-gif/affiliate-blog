"""
既存記事に対してバックフィル処理を行うスクリプト
  - アフィリエイトリンクセクションを追加（--affiliate）
  - 会話シーンをClaude APIで追加（--conversation）
"""
import argparse
import os
import re
import sys
import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# generate.py のユーティリティを再利用
sys.path.insert(0, str(Path(__file__).parent))
from generate import (
    build_affiliate_section,
    fetch_rakuten_products,
    gh,
    push_file,
    REPO,
    BRANCH,
    MODEL,
)

BLOG_DIR = Path("src/content/blog")

# ジャンル判定（ファイル名ベース）
GENRE_PATTERNS = {
    "travel": ["travel"],
    "gourmet": ["gourmet"],
    "investment": ["investment"],
    "business": ["business"],
    "gadget": ["gadget", "product"],
}

def detect_genre(filename: str) -> str:
    name = filename.lower()
    for genre, patterns in GENRE_PATTERNS.items():
        if any(p in name for p in patterns):
            return genre
    return "business"

def extract_keyword_from_md(content: str) -> str:
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip()[:30] if m else "おすすめ"

def has_affiliate_section(content: str) -> bool:
    return "おすすめ商品・サービス" in content or "アフィリエイト広告" in content

def strip_affiliate_section(content: str) -> str:
    """既存のアフィリエイトセクションを末尾から除去する"""
    marker = "\n\n---\n\n## おすすめ商品・サービス"
    idx = content.find(marker)
    if idx != -1:
        return content[:idx]
    return content

def has_conversation(content: str) -> bool:
    # 💬 が2個以上あれば会話シーンあり
    return content.count("💬") >= 2


# ── アフィリエイトリンク追加 ─────────────────────────────────

def backfill_affiliate(md_files: list, gh_token: str,
                       rakuten_app_id: str, rakuten_aff_id: str,
                       dry_run: bool, force: bool = False):
    updated = 0
    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        if has_affiliate_section(content):
            if not force:
                print(f"  スキップ（既存）: {md_path.name}")
                continue
            print(f"  強制更新（既存セクションを置換）: {md_path.name}")
            content = strip_affiliate_section(content)

        genre = detect_genre(md_path.name)
        keyword = extract_keyword_from_md(content)

        # ジャンル別の短い検索キーワード（長いと楽天API 400エラー）
        _RAKUTEN_GENRE_KW = {
            "business":   "副業 ビジネス",
            "investment": "投資 資産運用",
            "gadget":     "ガジェット テック",
            "travel":     "旅行グッズ",
            "gourmet":    "グルメ ギフト",
        }
        rakuten_kw = _RAKUTEN_GENRE_KW.get(genre, keyword[:15])

        # 楽天商品取得（API設定があれば）
        if rakuten_app_id and rakuten_aff_id:
            products = fetch_rakuten_products(rakuten_kw, rakuten_app_id, rakuten_aff_id, n=3)
            time.sleep(0.5)
        else:
            products = []

        section = build_affiliate_section(genre, keyword, products)
        new_content = content.rstrip() + "\n" + section

        if dry_run:
            print(f"  [DRY RUN] 追加予定: {md_path.name} ({genre})")
            continue

        repo_path = f"src/content/blog/{md_path.name}"
        try:
            push_file(gh_token, repo_path, new_content,
                      f"feat: アフィリエイトリンクをバックフィル ({md_path.name})")
            print(f"  ✅ 更新: {md_path.name}")
            updated += 1
            time.sleep(1)  # GitHub API レート制限回避
        except Exception as e:
            print(f"  ❌ エラー: {md_path.name}: {e}")

    print(f"\nアフィリエイトリンク追加: {updated}件更新")


# ── 会話シーン追加（Claude API） ─────────────────────────────

CONVERSATION_PROMPT = """\
以下のブログ記事に、**架空の2人の人物（読者目線のAさんと詳しいBさん）が会話するシーン**を
1〜2箇所追加してください。

ルール：
- 会話は記事テーマに自然に関連した内容にする
- 既存の内容・構成・frontmatterは一切変えない
- 以下の形式で挿入する（既存のh2の直後などに追加）：

> 💬 **Aさん（読者）**：「○○って実際どうなんですか？」
>
> 💬 **Bさん（詳しい人）**：「○○ですね。コツは△△です！」

- frontmatterから末尾まで完全に出力すること（省略禁止）
- 追加する会話以外は一字も変えないこと

--- 元の記事 ---
{article}
"""


def backfill_conversation(md_files: list, gh_token: str,
                          anthropic_key: str, dry_run: bool):
    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)
    updated = 0

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        if has_conversation(content):
            print(f"  スキップ（既存）: {md_path.name}")
            continue

        print(f"  処理中: {md_path.name} ...")

        if dry_run:
            print(f"  [DRY RUN] 会話追加予定: {md_path.name}")
            continue

        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                messages=[{
                    "role": "user",
                    "content": CONVERSATION_PROMPT.format(article=content),
                }],
            )
            new_content = resp.content[0].text

            # frontmatter があることを確認
            if not new_content.startswith("---"):
                print(f"  ⚠️ 出力が不正（frontmatterなし）: {md_path.name}")
                continue

            repo_path = f"src/content/blog/{md_path.name}"
            push_file(gh_token, repo_path, new_content,
                      f"feat: 会話シーンをバックフィル ({md_path.name})")
            print(f"  ✅ 更新: {md_path.name}")
            updated += 1
            time.sleep(3)  # レート制限回避

        except Exception as e:
            print(f"  ❌ エラー: {md_path.name}: {e}")
            time.sleep(5)

    print(f"\n会話シーン追加: {updated}件更新")


# ── メイン ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="既存記事バックフィル")
    parser.add_argument("--affiliate", action="store_true", help="アフィリエイトリンクを追加")
    parser.add_argument("--conversation", action="store_true", help="会話シーンを追加（Claude API）")
    parser.add_argument("--dry-run", action="store_true", help="実際には更新しない")
    parser.add_argument("--force", action="store_true", help="既存セクションがあっても強制上書き")
    parser.add_argument("--genre", help="特定ジャンルのみ処理 (business/investment/travel/gourmet)")
    args = parser.parse_args()

    if not args.affiliate and not args.conversation:
        parser.print_help()
        sys.exit(1)

    gh_token = os.environ.get("GH_TOKEN", "")
    if not gh_token and not args.dry_run:
        print("ERROR: GH_TOKEN が未設定です", file=sys.stderr)
        sys.exit(1)

    # 対象ファイル一覧
    all_files = sorted(BLOG_DIR.glob("*.md"))
    if args.genre:
        all_files = [f for f in all_files if detect_genre(f.name) == args.genre]

    # 手動作成記事（best-coffee-grinder, protein-supplement, remote-work）は対象外
    auto_files = [f for f in all_files if re.search(r'_(202\d{5})\.md$', f.name)]
    print(f"対象記事: {len(auto_files)}件")

    if args.affiliate:
        print("\n=== アフィリエイトリンク追加 ===")
        rakuten_app_id = os.environ.get("RAKUTEN_APP_ID", "")
        rakuten_aff_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
        backfill_affiliate(auto_files, gh_token, rakuten_app_id, rakuten_aff_id, args.dry_run, args.force)

    if args.conversation:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key and not args.dry_run:
            print("ERROR: ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
            sys.exit(1)
        print("\n=== 会話シーン追加 ===")
        backfill_conversation(auto_files, gh_token, anthropic_key, args.dry_run)


if __name__ == "__main__":
    main()

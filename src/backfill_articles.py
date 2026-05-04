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
    build_editor_note,
    generate_editor_note,
    has_editor_note,
    extract_title,
    fetch_rakuten_products,
    generate_rakuten_products,
    fetch_pixabay_image_urls,
    insert_images_into_article,
    _GENRE_IMAGE_QUERIES,
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
                       dry_run: bool, force: bool = False,
                       anthropic_key: str = ""):
    import anthropic as anthropic_mod
    client = anthropic_mod.Anthropic(api_key=anthropic_key) if anthropic_key else None
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
        title = extract_title(content)

        # 楽天商品取得（API設定があれば・失敗してもスキップ）
        _RAKUTEN_GENRE_KW = {
            "business":   "副業 ビジネス",
            "investment": "投資 資産運用",
            "gadget":     "ガジェット テック",
            "travel":     "旅行グッズ",
            "gourmet":    "グルメ ギフト",
        }
        rakuten_kw = _RAKUTEN_GENRE_KW.get(genre, keyword[:15])
        if rakuten_app_id and rakuten_aff_id:
            products = fetch_rakuten_products(rakuten_kw, rakuten_app_id, rakuten_aff_id, n=3)
            time.sleep(0.5)
        else:
            products = []

        # Claude APIで楽天商品候補を生成（ANTHROPIC_API_KEY + RAKUTEN_AFFILIATE_ID があれば）
        rakuten_claude_products = []
        if client and rakuten_aff_id:
            rakuten_claude_products = generate_rakuten_products(
                client, title, keyword, genre, rakuten_aff_id
            )
            time.sleep(1)

        section = build_affiliate_section(
            genre, keyword, products,
            rakuten_aff_id=rakuten_aff_id,
            rakuten_products=rakuten_claude_products
        )
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


# ── 画像バックフィル（Pixabay API） ─────────────────────────

def has_images(content: str) -> bool:
    """記事に画像が既に含まれているか確認"""
    return bool(re.search(r'<figure.*?<img|!\[.*?\]\(https?://', content))

def backfill_images(md_files: list, gh_token: str, pixabay_key: str,
                    dry_run: bool, force: bool = False):
    updated = 0
    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        if has_images(content):
            if not force:
                print(f"  スキップ（既存）: {md_path.name}")
                continue
            print(f"  強制更新: {md_path.name}")

        genre = detect_genre(md_path.name)
        title = extract_title(content)
        # Unsplashは英語タグで検索するためジャンル別英語クエリのみ使用
        img_query = _GENRE_IMAGE_QUERIES.get(genre, "nature landscape")

        print(f"  処理中: {md_path.name} ({genre}) ...")

        if dry_run:
            print(f"  [DRY RUN] 画像追加予定: {md_path.name}")
            continue

        images = fetch_pixabay_image_urls(img_query, pixabay_key, n=3)
        if not images:
            print(f"  ⚠️ 画像取得失敗: {md_path.name}")
            time.sleep(1)
            continue

        # 本文に画像を挿入
        new_content = insert_images_into_article(content, images)

        # heroImage を frontmatter に追加（まだなければ）
        if "heroImage:" not in new_content:
            hero_url = images[0]["url"]
            new_content = re.sub(
                r'^(---\n[\s\S]*?)(---\n)',
                lambda m: m.group(1) + f'heroImage: "{hero_url}"\n' + m.group(2),
                new_content, count=1
            )

        repo_path = f"src/content/blog/{md_path.name}"
        try:
            push_file(gh_token, repo_path, new_content,
                      f"feat: Pixabay画像をバックフィル ({md_path.name})")
            print(f"  ✅ 更新: {md_path.name}")
            updated += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"  ❌ エラー: {md_path.name}: {e}")

    print(f"\n画像バックフィル: {updated}件更新")


# ── 編集者コメント追加（Claude API） ────────────────────────

def strip_editor_note(content: str) -> str:
    """既存の編集者コメントセクションを除去する"""
    marker = "\n\n---\n\n> 📝 **Noriのひとこと**"
    idx = content.find(marker)
    if idx != -1:
        # 次の --- か末尾まで除去
        rest = content[idx + len(marker):]
        next_sep = rest.find("\n\n---\n\n")
        if next_sep != -1:
            return content[:idx] + rest[next_sep:]
        else:
            return content[:idx]
    return content


def backfill_editor_note(md_files: list, gh_token: str,
                         anthropic_key: str, dry_run: bool, force: bool = False):
    import anthropic
    client = anthropic.Anthropic(api_key=anthropic_key)
    updated = 0

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        if has_editor_note(content):
            if not force:
                print(f"  スキップ（既存）: {md_path.name}")
                continue
            print(f"  強制更新（既存コメントを置換）: {md_path.name}")
            content = strip_editor_note(content)

        title = extract_title(content)
        # ジャンル判定
        genre = detect_genre(md_path.name)

        print(f"  処理中: {md_path.name} ({genre}) ...")

        if dry_run:
            print(f"  [DRY RUN] 編集者コメント追加予定: {md_path.name}")
            continue

        note_text = generate_editor_note(client, title, genre)
        if not note_text:
            print(f"  ⚠️ コメント生成失敗: {md_path.name}")
            continue

        # アフィリエイトセクションの直前に挿入
        affiliate_marker = "\n\n---\n\n## おすすめ商品・サービス"
        note_block = build_editor_note(note_text)

        if affiliate_marker in content:
            idx = content.find(affiliate_marker)
            new_content = content[:idx] + note_block + content[idx:]
        else:
            new_content = content.rstrip() + note_block

        repo_path = f"src/content/blog/{md_path.name}"
        try:
            push_file(gh_token, repo_path, new_content,
                      f"feat: 編集者コメントをバックフィル ({md_path.name})")
            print(f"  ✅ 更新: {md_path.name}")
            updated += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"  ❌ エラー: {md_path.name}: {e}")

    print(f"\n編集者コメント追加: {updated}件更新")


# ── 会話シーン追加（Claude API） ─────────────────────────────

REWRITE_PROMPT = """\
以下のブログ記事を、最新の品質ガイドラインに従ってリライトしてください。

【品質ガイドライン】
{principles}

【リライトのルール（厳守）】
- frontmatter（---で囲まれた冒頭部分）は一切変更しない
- 「---\n\n## おすすめ商品・サービス」以降のセクションは変更しない
- 「> 📝 **Noriのひとこと**」セクションは変更しない
- 記事本文（frontmatter終了〜アフィリエイトセクション開始）のみをリライトする
- h1タイトル（# ○○）は変更しない
- PR表記（> 📣 この記事はPR・広告を含みます。）は必ず冒頭付近に残す
- 本文に「{year}年{month}月時点の情報です」を自然な形で1箇所明記する
- 記事の冒頭（h1直後）で読者の悩みに共感する文章を入れる
- 商品・サービスはスペックよりも「使うことでどう変わるか（明るい未来）」を先に伝える
- 一文は短く（目安20〜40文字）、文字装飾は重要箇所のみに絞る
- 記事全体の文字数は1000〜3000文字を目安にする
- 完全な記事全文を出力すること（省略は絶対禁止）

--- 元の記事 ---
{article}
"""


def backfill_rewrite(md_files: list, gh_token: str,
                     anthropic_key: str, dry_run: bool, force: bool = False):
    """Claude APIで全記事を最新ガイドラインに従ってリライト"""
    import anthropic
    from datetime import datetime
    from generate import _COMMON_PRINCIPLES

    client = anthropic.Anthropic(api_key=anthropic_key)
    updated = 0
    now = datetime.now()
    year, month = now.year, now.month

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")

        # rewrite済みマーカー確認（frontmatterのrewritten: trueフラグ）
        if not force and re.search(r'^rewritten:\s*true', content, re.MULTILINE):
            print(f"  スキップ（リライト済み）: {md_path.name}")
            continue

        print(f"  処理中: {md_path.name} ...")

        if dry_run:
            print(f"  [DRY RUN] リライト予定: {md_path.name}")
            continue

        prompt = REWRITE_PROMPT.format(
            principles=_COMMON_PRINCIPLES,
            year=year,
            month=month,
            article=content,
        )

        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            new_content = resp.content[0].text.strip()

            # frontmatterが維持されているか確認
            if not new_content.startswith("---"):
                print(f"  ⚠️ 出力不正（frontmatterなし）: {md_path.name}")
                continue

            # rewritten: true フラグをfrontmatterに追加
            new_content = re.sub(
                r'^(---\n)([\s\S]*?)(---\n)',
                lambda m: m.group(1) + m.group(2) + "rewritten: true\n" + m.group(3),
                new_content, count=1
            )

            repo_path = f"src/content/blog/{md_path.name}"
            push_file(gh_token, repo_path, new_content,
                      f"refactor: ガイドライン反映リライト ({md_path.name})")
            print(f"  ✅ 更新: {md_path.name}")
            updated += 1
            time.sleep(3)

        except Exception as e:
            print(f"  ❌ エラー: {md_path.name}: {e}")
            time.sleep(5)

    print(f"\nリライト完了: {updated}件更新")


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
    parser.add_argument("--editor-note", action="store_true", help="Noriのひとこと編集者コメントを追加（Claude API）")
    parser.add_argument("--images", action="store_true", help="Pixabay画像を追加（PIXABAY_API_KEY必須）")
    parser.add_argument("--rewrite", action="store_true", help="最新ガイドラインで記事本文をリライト（Claude API）")
    parser.add_argument("--dry-run", action="store_true", help="実際には更新しない")
    parser.add_argument("--force", action="store_true", help="既存セクションがあっても強制上書き")
    parser.add_argument("--genre", help="特定ジャンルのみ処理 (business/investment/travel/gourmet/gadget)")
    args = parser.parse_args()

    if not args.affiliate and not args.conversation and not args.editor_note and not args.images and not args.rewrite:
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
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        backfill_affiliate(auto_files, gh_token, rakuten_app_id, rakuten_aff_id, args.dry_run, args.force, anthropic_key)

    if args.conversation:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key and not args.dry_run:
            print("ERROR: ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
            sys.exit(1)
        print("\n=== 会話シーン追加 ===")
        backfill_conversation(auto_files, gh_token, anthropic_key, args.dry_run)

    if args.editor_note:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key and not args.dry_run:
            print("ERROR: ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
            sys.exit(1)
        print("\n=== 編集者コメント（Noriのひとこと）追加 ===")
        backfill_editor_note(auto_files, gh_token, anthropic_key, args.dry_run, args.force)

    if args.images:
        pixabay_key = os.environ.get("UNSPLASH_API_KEY", "") or os.environ.get("PIXABAY_API_KEY", "")
        if not pixabay_key and not args.dry_run:
            print("ERROR: PIXABAY_API_KEY が未設定です", file=sys.stderr)
            sys.exit(1)
        print("\n=== Pixabay画像バックフィル ===")
        backfill_images(auto_files, gh_token, pixabay_key, args.dry_run, args.force)

    if args.rewrite:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key and not args.dry_run:
            print("ERROR: ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
            sys.exit(1)
        print("\n=== ガイドライン反映リライト ===")
        backfill_rewrite(auto_files, gh_token, anthropic_key, args.dry_run, args.force)


if __name__ == "__main__":
    main()

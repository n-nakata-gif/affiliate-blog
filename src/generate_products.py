import os
import sys
import json
import re
import base64
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import anthropic

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BLOG_URL = "https://affiliate-blog.nori-nakata1004.workers.dev"
REPO = "n-nakata-gif/affiliate-blog"
BRANCH = "main"
MODEL = "claude-opus-4-7"
MIN_CHARS = 2000

PRODUCTS_PATH = "data/products.json"

CATEGORY_SLUG = {
    "Electronics": "electronics",
    "Computers": "computers",
    "ガジェット・家電": "gadgets",
}

# 曜日別優先カテゴリ (0=月, 3=木)
WEEKDAY_CATEGORY = {
    0: "ガジェット・家電",
    3: "Computers",
}

CATEGORY_TITLE_JA = {
    "Electronics": "家電・ガジェット",
    "Computers": "PC・周辺機器",
    "ガジェット・家電": "ガジェット・家電",
}


# ── データ読み込み ────────────────────────────────────────────

def load_products():
    with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_images(date_str):
    path = Path(f"data/images_{date_str}.json")
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def select_products(products, weekday, limit=5):
    priority_category = WEEKDAY_CATEGORY.get(weekday)
    if priority_category:
        prioritized = [p for p in products if p.get("category") == priority_category]
        others = [p for p in products if p.get("category") != priority_category]
        ordered = prioritized + others
    else:
        ordered = products

    # レビュー数 → 評価の順でソート
    ordered.sort(
        key=lambda p: (p.get("review_count") or 0, p.get("rating") or 0.0),
        reverse=True,
    )
    return ordered[:limit]


# ── 文字数カウント ────────────────────────────────────────────

def count_body_chars(mdx):
    # frontmatter 除去
    mdx = re.sub(r"^---[\s\S]*?---\n", "", mdx, count=1)
    # HTMLタグ除去
    mdx = re.sub(r"<[^>]+>", "", mdx)
    # Markdownリンク・画像（テキスト部分は残す）
    mdx = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", mdx)
    mdx = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", mdx)
    # 表の区切り行を除去
    mdx = re.sub(r"^\|[-| :]+\|$", "", mdx, flags=re.MULTILINE)
    # Markdown記号を除去（見出し・強調・テーブル区切り）
    mdx = re.sub(r"[#*`|]", "", mdx)
    # 空白行を除去してカウント
    text = re.sub(r"\n+", "\n", mdx).strip()
    return len(text)


# ── 記事生成（Claude API） ────────────────────────────────────

def build_prompt(products, images_data, date_str, slug, category_ja):
    today = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    year = date_str[:4]
    n = len(products)
    image_dir = f"/images/articles/{date_str}_{slug}"

    hero_alt = ""
    prod1_alt = ""
    if images_data:
        for img in images_data.get("images", []):
            if img["filename"] == "hero.jpg":
                hero_alt = img["alt"]
            elif img["filename"] == "product_1.jpg":
                prod1_alt = img["alt"]

    products_json = json.dumps(products, ensure_ascii=False, indent=2)

    return f"""以下の商品データをもとに、Astro用のMDX形式アフィリエイトブログ記事を作成してください。

## 商品データ（JSON）
{products_json}

## 記事の要件

### frontmatter（必ずこの形式で出力）
```
---
title: "【{year}年最新】{category_ja}おすすめ{n}選｜売れ筋ランキング"
description: "（150字以内で{category_ja}の選び方とランキングを説明）"
pubDate: {today}
tags: ["{category_ja}", "おすすめ", "ランキング", "比較"]
image: "{image_dir}/hero.jpg"
affiliate: true
---
```

### 本文構成（合計2000字以上・日本語）

1. **導入**（200字以上）
   - 読者の悩みやニーズに共感する書き出し
   - 記事で解決できることを明示

2. **ヒーロー画像**（1箇所目）
   ```
   ![{hero_alt}]({image_dir}/hero.jpg)
   ```

3. **商品比較表**
   上位{n}商品を表形式で比較（商品名・価格・評価・レビュー数・一言コメント）

4. **各商品の詳細レビュー**（各商品300字以上）
   各商品について以下を含める：
   - 商品名をH3見出しに
   - 特徴・メリット・デメリット
   - こんな人におすすめ
   - アフィリエイトリンク（Amazon・楽天それぞれ）
     ```html
     <a href="{{affiliate_url}}" target="_blank" rel="nofollow sponsored">Amazonで見る</a>
     ```
     楽天リンクは source="rakuten" の商品があれば使用し、なければAmazonリンクを「楽天で見る」として流用

5. **商品画像**（2箇所目）
   ```
   ![{prod1_alt}]({image_dir}/product_1.jpg)
   ```

6. **選び方のポイント**（300字以上）
   {category_ja}を選ぶ際の具体的なチェックポイント3〜4点

7. **まとめ・総合おすすめ**（200字以上）
   予算別・用途別のおすすめをまとめる

8. **FAQ**（3問）
   読者がよく持つ疑問に回答（各100字以上）

## 注意事項
- MDXファイルとして有効な形式で出力する
- frontmatterから本文末尾まで完全に出力する（省略・要約禁止）
- アフィリエイトリンクには必ず target="_blank" rel="nofollow sponsored" を付与する
- 価格はproducts.jsonの値を使い「円」を付けて表示する（Noneの場合は「価格はAmazonで確認」と記載）
- 評価がNoneの商品はその旨を省略して記載する
"""


def generate_article(client, prompt):
    response = client.messages.create(
        model=MODEL,
        max_tokens=8096,
        system=[
            {
                "type": "text",
                "text": "あなたはSEOに強い日本語アフィリエイトブログのプロライターです。指定された構成・文字数・形式を厳守して、読者に役立つ高品質な記事を書きます。",
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def supplement_article(client, article, current_chars):
    shortage = MIN_CHARS - current_chars
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"""以下のMDX記事は本文が約{current_chars}字で、目標の{MIN_CHARS}字に約{shortage}字不足しています。
以下のルールで加筆して完全な記事として出力してください：
- 各商品レビューセクションをより詳しく（実際の使用感・具体的なメリット・デメリット）
- 「選び方のポイント」に1〜2点追加
- FAQに1問追加
- frontmatterや画像埋め込みはそのまま保持する

--- 元の記事 ---
{article}
""",
            }
        ],
    )
    return response.content[0].text


def ensure_min_chars(client, article, prompt):
    chars = count_body_chars(article)
    if chars >= MIN_CHARS:
        return article

    logger.info("Body chars %d < %d; supplementing...", chars, MIN_CHARS)
    article = supplement_article(client, article, chars)

    # 2回目チェック
    chars = count_body_chars(article)
    if chars < MIN_CHARS:
        logger.error("Still %d chars after supplement (target %d)", chars, MIN_CHARS)
    return article


# ── GitHub Trees API ─────────────────────────────────────────

def gh(method, path, token, body=None):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} → {e.code}: {body_text}") from e


def create_blob(token, content_bytes):
    result = gh("POST", "git/blobs", token, {
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "encoding": "base64",
    })
    return result["sha"]


def push_files_atomically(token, file_map, commit_message):
    """
    file_map: {repo_path: local_path or bytes}
    repo_pathはリポジトリ内のパス（例: "src/content/blog/foo.mdx"）
    """
    # 現在のブランチ先端
    ref = gh("GET", f"git/ref/heads/{BRANCH}", token)
    head_sha = ref["object"]["sha"]

    commit_info = gh("GET", f"git/commits/{head_sha}", token)
    base_tree_sha = commit_info["tree"]["sha"]

    # 各ファイルのblobを作成
    tree_entries = []
    for repo_path, content in file_map.items():
        if isinstance(content, (str, bytes)):
            data = content.encode("utf-8") if isinstance(content, str) else content
        else:
            raise TypeError(f"Unsupported content type for {repo_path}")

        blob_sha = create_blob(token, data)
        tree_entries.append({
            "path": repo_path,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha,
        })

    new_tree = gh("POST", "git/trees", token, {
        "base_tree": base_tree_sha,
        "tree": tree_entries,
    })

    new_commit = gh("POST", "git/commits", token, {
        "message": commit_message,
        "tree": new_tree["sha"],
        "parents": [head_sha],
    })

    gh("PATCH", f"git/refs/heads/{BRANCH}", token, {"sha": new_commit["sha"]})

    return new_commit["sha"]


# ── メイン ────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    gh_token = os.environ.get("GH_TOKEN")

    missing = [k for k, v in {"ANTHROPIC_API_KEY": api_key, "GH_TOKEN": gh_token}.items() if not v]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    if not Path(PRODUCTS_PATH).exists():
        print(f"ERROR: {PRODUCTS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    weekday = now.weekday()

    products = load_products()
    if not products:
        print(f"ERROR: {PRODUCTS_PATH} is empty", file=sys.stderr)
        sys.exit(1)

    images_data = load_images(date_str)
    selected = select_products(products, weekday)

    # スラッグ・カテゴリ名決定
    top_category = selected[0].get("category", "Electronics") if selected else "Electronics"
    slug = CATEGORY_SLUG.get(top_category, "gadgets")
    category_ja = CATEGORY_TITLE_JA.get(top_category, top_category)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = build_prompt(selected, images_data, date_str, slug, category_ja)
    article = generate_article(client, prompt)
    article = ensure_min_chars(client, article, prompt)

    from factcheck import factcheck_article
    fc_result = factcheck_article(article, "gadget")
    if not fc_result["is_safe"]:
        print("ERROR: ファクトチェック失敗 - 投稿中止", file=sys.stderr)
        sys.exit(1)
    article = fc_result["verified_content"]

    # コミットするファイルを収集
    article_repo_path = f"src/content/blog/gadget_{date_str}.mdx"
    file_map = {article_repo_path: article.encode("utf-8")}

    # 画像ファイルを追加
    image_local_dir = Path(f"public/images/articles/{date_str}_{slug}")
    if image_local_dir.exists():
        for img_file in image_local_dir.glob("*.jpg"):
            repo_path = f"public/images/articles/{date_str}_{slug}/{img_file.name}"
            file_map[repo_path] = img_file.read_bytes()
    else:
        logger.error("Image dir not found: %s", image_local_dir)

    commit_message = f"auto: add gadget article {date_str}"
    commit_sha = push_files_atomically(gh_token, file_map, commit_message)

    url = f"https://github.com/{REPO}/commit/{commit_sha}"
    print(url)

    title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', article, re.MULTILINE)
    tags_m = re.search(r'^tags:\s*\[(.+?)\]', article, re.MULTILINE)
    from notify import send_notification
    send_notification(
        article_type="gadget",
        title=title_m.group(1).strip() if title_m else f"ガジェット記事 {date_str}",
        article_url=url,
        blog_url=BLOG_URL,
        tags=[t.strip().strip("\"'") for t in tags_m.group(1).split(',')] if tags_m else [category_ja],
        word_count=count_body_chars(article),
    )


if __name__ == "__main__":
    main()

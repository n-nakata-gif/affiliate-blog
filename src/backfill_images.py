"""
画像URLをUnsplash画像に置き換えるバックフィルスクリプト
Pixabay・既存Unsplash問わず全記事を記事ごとに異なる画像に更新する
"""
from __future__ import annotations
import json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path

CONTENT_DIR = Path(__file__).parent / "content" / "blog"

# ジャンル別に複数クエリを用意して使い回しを防ぐ
GENRE_QUERIES = {
    "business": [
        "business meeting office professional",
        "entrepreneur startup laptop work",
        "freelance remote work desk",
        "business growth success strategy",
        "office team collaboration modern",
    ],
    "gadget": [
        "technology gadget device modern",
        "smartphone electronics innovation",
        "computer tech minimalist desk",
        "wireless headphones earbuds product",
        "smart home device technology",
    ],
    "investment": [
        "finance investment stock market",
        "money saving wealth management",
        "financial planning graph growth",
        "cryptocurrency bitcoin digital finance",
        "real estate property investment",
    ],
    "travel": [
        "travel landscape scenic nature",
        "japan tourism city skyline",
        "mountain hiking adventure outdoor",
        "beach ocean tropical vacation",
        "kyoto temple japanese culture",
    ],
    "gourmet": [
        "food delicious restaurant table",
        "japanese cuisine sushi ramen",
        "cooking kitchen fresh ingredients",
        "coffee cafe bakery pastry",
        "healthy meal salad vegetables",
    ],
}

# Pixabay・Unsplash両方のURLにマッチ
IMAGE_PATTERN = re.compile(r'https://(?:pixabay\.com/get|images\.unsplash\.com)/[^\s"\']+')


def fetch_unsplash_images(query: str, api_key: str, n: int = 3, page: int = 1) -> list:
    params = {
        "query": query,
        "per_page": n,
        "page": page,
        "orientation": "landscape",
        "content_filter": "high",
    }
    endpoint = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        endpoint,
        headers={"Authorization": f"Client-ID {api_key}", "Accept-Version": "v1"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    results = []
    for photo in data.get("results", [])[:n]:
        url = photo.get("urls", {}).get("regular", "")
        alt = photo.get("alt_description") or query
        if url:
            results.append({"url": url, "alt": alt[:50]})
    return results


def detect_genre(filename: str) -> str:
    for genre in GENRE_QUERIES:
        if genre in filename:
            return genre
    return "business"


def fix_article(path: Path, api_key: str, article_index: int) -> bool:
    content = path.read_text(encoding="utf-8")

    # 画像URLが存在する記事のみ処理
    if not IMAGE_PATTERN.search(content):
        return False

    genre = detect_genre(path.stem)
    queries = GENRE_QUERIES[genre]

    # 記事ごとに異なるクエリとページを使う
    query = queries[article_index % len(queries)]
    page = (article_index // len(queries)) + 1

    try:
        images = fetch_unsplash_images(query, api_key, n=4, page=page)
    except Exception as e:
        print(f"  画像取得失敗: {e}")
        return False

    if not images:
        print(f"  画像が取得できませんでした")
        return False

    img_index = [0]

    def replace_url(m):
        i = img_index[0] % len(images)
        img_index[0] += 1
        return images[i]["url"]

    new_content = IMAGE_PATTERN.sub(replace_url, content)

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
        print(f"  修正完了: クエリ='{query}' page={page}, {img_index[0]}箇所を置き換え")
        return True

    return False


def main():
    api_key = os.environ.get("UNSPLASH_API_KEY") or os.environ.get("UNSPLASH_ACCESS_KEY")
    if not api_key:
        print("エラー: UNSPLASH_API_KEY が設定されていません")
        sys.exit(1)

    md_files = sorted(CONTENT_DIR.glob("*.md"))
    fixed = 0
    article_index = 0
    for path in md_files:
        print(f"処理中: {path.name}")
        if fix_article(path, api_key, article_index):
            fixed += 1
        article_index += 1

    print(f"\n完了: {fixed}記事を修正しました")


if __name__ == "__main__":
    main()

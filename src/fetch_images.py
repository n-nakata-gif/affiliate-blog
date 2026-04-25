import os
import sys
import json
import time
import logging
import re
import urllib.request
import urllib.parse
import urllib.error
import io
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PRODUCTS_PATH = "data/products.json"
MAX_SIZE_BYTES = 500 * 1024  # 500KB

UNSPLASH_ENDPOINT = "https://api.unsplash.com/search/photos"
PIXABAY_ENDPOINT = "https://pixabay.com/api/"

CATEGORY_QUERY_MAP = {
    "Electronics": "electronics gadgets technology",
    "Computers": "computer laptop technology",
    "ガジェット・家電": "smart home gadgets electronics",
}

ALT_TEMPLATES = {
    "hero": "{category}のおすすめガジェット・家電 最新売れ筋ランキング {year}年",
    "product": "{title} レビュー・評価 {category} おすすめ商品",
}


# ── ユーティリティ ──────────────────────────────────────────────

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "gadgets"


def download_bytes(url, timeout=15):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; affiliate-blog-bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def resize_if_needed(data):
    if len(data) <= MAX_SIZE_BYTES:
        return data
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        quality = 85
        while quality >= 40:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            result = buf.getvalue()
            if len(result) <= MAX_SIZE_BYTES:
                return result
            # さらに小さくする場合はリサイズ
            w, h = img.size
            img = img.resize((int(w * 0.8), int(h * 0.8)), Image.LANCZOS)
            quality -= 10

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=40, optimize=True)
        return buf.getvalue()
    except ImportError:
        logger.error("Pillow not installed; cannot resize image")
        return data


def save_image(path, data):
    data = resize_if_needed(data)
    with open(path, "wb") as f:
        f.write(data)


# ── 画像ソース ─────────────────────────────────────────────────

def fetch_product_image(image_url):
    if not image_url:
        return None
    try:
        data, content_type = download_bytes(image_url)
        if not content_type.startswith("image/"):
            return None
        return data
    except Exception as e:
        logger.error("Product image fetch failed (%s): %s", image_url[:60], e)
        return None


def fetch_unsplash(query, access_key):
    params = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape",
        "content_filter": "high",
    }
    url = UNSPLASH_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return None, None
        photo = results[0]
        img_url = photo["urls"]["regular"]
        attribution = photo.get("user", {}).get("name", "Unsplash")
        img_data, _ = download_bytes(img_url)
        return img_data, attribution
    except Exception as e:
        logger.error("Unsplash fetch failed (query=%s): %s", query, e)
        return None, None


def fetch_pixabay(query, api_key):
    params = {
        "key": api_key,
        "q": query,
        "image_type": "photo",
        "orientation": "horizontal",
        "safesearch": "true",
        "per_page": 3,
        "order": "popular",
    }
    url = PIXABAY_ENDPOINT + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        hits = data.get("hits", [])
        if not hits:
            return None
        img_url = hits[0].get("webformatURL", "")
        if not img_url:
            return None
        img_data, _ = download_bytes(img_url)
        return img_data
    except Exception as e:
        logger.error("Pixabay fetch failed (query=%s): %s", query, e)
        return None


def fetch_fallback_image(query, unsplash_key, pixabay_key):
    if unsplash_key:
        data, attr = fetch_unsplash(query, unsplash_key)
        if data:
            return data
        time.sleep(1)

    if pixabay_key:
        data = fetch_pixabay(query, pixabay_key)
        if data:
            return data

    return None


# ── メイン処理 ─────────────────────────────────────────────────

def determine_slug(products):
    if not products:
        return "gadgets"
    # 最頻出カテゴリをスラッグに
    from collections import Counter
    counts = Counter(p.get("category", "") for p in products)
    top_category = counts.most_common(1)[0][0]
    en_map = {
        "Electronics": "electronics",
        "Computers": "computers",
        "ガジェット・家電": "gadgets",
    }
    return en_map.get(top_category, slugify(top_category)) or "gadgets"


def main():
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")

    if not unsplash_key:
        logger.error("UNSPLASH_ACCESS_KEY is not set; Unsplash fallback disabled")
    if not pixabay_key:
        logger.error("PIXABAY_API_KEY is not set; Pixabay fallback disabled")

    if not Path(PRODUCTS_PATH).exists():
        print(f"ERROR: {PRODUCTS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)

    if not products:
        print("ERROR: products.json is empty", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    slug = determine_slug(products)
    article_dir = Path(f"public/images/articles/{date_str}_{slug}")
    article_dir.mkdir(parents=True, exist_ok=True)

    alt_records = {}
    year = datetime.now(timezone.utc).year

    # hero画像: メインカテゴリに対応する英語クエリで取得
    top_category = products[0].get("category", "Electronics") if products else "Electronics"
    hero_query = CATEGORY_QUERY_MAP.get(top_category, "gadgets technology")

    hero_data = fetch_fallback_image(hero_query, unsplash_key, pixabay_key)
    if hero_data:
        hero_path = article_dir / "hero.jpg"
        save_image(hero_path, hero_data)
        alt_records["hero.jpg"] = ALT_TEMPLATES["hero"].format(
            category=top_category, year=year
        )
        print(str(hero_path))
    else:
        logger.error("hero image could not be fetched")

    time.sleep(1)

    # product画像: 上位2件
    saved_count = 0
    for product in products:
        if saved_count >= 2:
            break

        img_num = saved_count + 1
        filename = f"product_{img_num}.jpg"
        dest_path = article_dir / filename

        img_data = fetch_product_image(product.get("image_url", ""))

        if not img_data:
            category = product.get("category", "Electronics")
            query = CATEGORY_QUERY_MAP.get(category, "gadgets technology")
            img_data = fetch_fallback_image(query, unsplash_key, pixabay_key)
            time.sleep(1)

        if img_data:
            save_image(dest_path, img_data)
            alt_records[filename] = ALT_TEMPLATES["product"].format(
                title=product.get("title", "")[:40],
                category=product.get("category", ""),
            )
            print(str(dest_path))
            saved_count += 1
        else:
            logger.error("product_%d image could not be fetched (id=%s)", img_num, product.get("asin_or_id", "?"))

        time.sleep(1)

    # alt テキストを保存
    images_json_path = Path(f"data/images_{date_str}.json")
    output = {
        "date": date_str,
        "article_dir": str(article_dir),
        "images": [
            {"filename": fname, "path": str(article_dir / fname), "alt": alt}
            for fname, alt in alt_records.items()
        ],
    }
    with open(images_json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(str(images_json_path))
    print(f"Saved {saved_count + (1 if 'hero.jpg' in alt_records else 0)} images → {article_dir}")


if __name__ == "__main__":
    main()

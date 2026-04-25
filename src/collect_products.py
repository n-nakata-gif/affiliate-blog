import os
import sys
import json
import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = "data/products.json"


# ── Amazon PA-API ──────────────────────────────────────────────

def get_amazon_client():
    import paapi5_python_sdk
    from paapi5_python_sdk.api.default_api import DefaultApi
    from paapi5_python_sdk.rest import ApiException  # noqa: F401

    access_key = os.environ["AMAZON_ACCESS_KEY"]
    secret_key = os.environ["AMAZON_SECRET_KEY"]
    associate_tag = os.environ["AMAZON_ASSOCIATE_TAG"]

    config = paapi5_python_sdk.Configuration()
    config.host = "webservices.amazon.co.jp"
    client = paapi5_python_sdk.ApiClient(
        configuration=config,
        access_key=access_key,
        secret_key=secret_key,
        host="webservices.amazon.co.jp",
        region="us-east-1",
    )
    api = DefaultApi(api_client=client)
    return api, associate_tag


def fetch_amazon_browse_node(api, associate_tag, browse_node_id, category_name, limit=10):
    from paapi5_python_sdk.models.get_browse_nodes_request import GetBrowseNodesRequest
    from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
    from paapi5_python_sdk.models.search_items_resource import SearchItemsResource
    from paapi5_python_sdk.models.partner_type import PartnerType
    from paapi5_python_sdk.rest import ApiException

    resources = [
        SearchItemsResource.ITEMINFO_TITLE,
        SearchItemsResource.ITEMINFO_FEATURES,
        SearchItemsResource.OFFERS_LISTINGS_PRICE,
        SearchItemsResource.CUSTOMERREVIEWS_COUNT,
        SearchItemsResource.CUSTOMERREVIEWS_STARRATING,
        SearchItemsResource.IMAGES_PRIMARY_LARGE,
    ]

    request = SearchItemsRequest(
        partner_tag=associate_tag,
        partner_type=PartnerType.ASSOCIATES,
        browse_node_id=browse_node_id,
        sort_by="Featured",
        item_count=limit,
        resources=resources,
        marketplace="www.amazon.co.jp",
    )

    products = []
    try:
        response = api.search_items(request)
        if not response.search_result or not response.search_result.items:
            return products

        for item in response.search_result.items:
            try:
                asin = item.asin
                title = (
                    item.item_info.title.display_value
                    if item.item_info and item.item_info.title
                    else ""
                )
                price = None
                if (
                    item.offers
                    and item.offers.listings
                    and item.offers.listings[0].price
                ):
                    price = item.offers.listings[0].price.amount

                rating = None
                review_count = None
                if item.customer_reviews:
                    rating = item.customer_reviews.star_rating.display_value if item.customer_reviews.star_rating else None
                    review_count = item.customer_reviews.count.display_value if item.customer_reviews.count else None

                features = []
                if item.item_info and item.item_info.features:
                    features = item.item_info.features.display_values or []

                image_url = ""
                if item.images and item.images.primary and item.images.primary.large:
                    image_url = item.images.primary.large.url

                affiliate_url = item.detail_page_url or f"https://www.amazon.co.jp/dp/{asin}?tag={associate_tag}"

                products.append({
                    "source": "amazon",
                    "asin_or_id": asin,
                    "title": title,
                    "price": float(price) if price is not None else None,
                    "rating": float(rating) if rating is not None else None,
                    "review_count": int(review_count) if review_count is not None else None,
                    "features": list(features),
                    "image_url": image_url,
                    "affiliate_url": affiliate_url,
                    "category": category_name,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.error("Amazon item parse error (asin=%s): %s", getattr(item, "asin", "?"), e)

    except ApiException as e:
        logger.error("Amazon PA-API error (node=%s): %s", browse_node_id, e)

    return products


def collect_amazon():
    try:
        api, associate_tag = get_amazon_client()
    except Exception as e:
        logger.error("Amazon client init failed: %s", e)
        return []

    # Browse node IDs for amazon.co.jp
    categories = [
        ("3210981", "Electronics"),    # 家電・カメラ
        ("2127209051", "Computers"),   # パソコン・周辺機器
    ]

    all_products = []
    for node_id, name in categories:
        logger.info("Fetching Amazon %s (node=%s)...", name, node_id)
        products = fetch_amazon_browse_node(api, associate_tag, node_id, name)
        all_products.extend(products)
        time.sleep(1)

    return all_products


# ── 楽天 API ──────────────────────────────────────────────────

RAKUTEN_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706"

# 楽天ジャンルID: 家電・カメラ・AV機器 > AV・デジモノ
RAKUTEN_GENRES = [
    ("0", "ガジェット・家電"),  # genre_id=0 はキーワード検索で代替
]


def fetch_rakuten_genre(app_id, affiliate_id, keyword, category_name, limit=10):
    params = {
        "applicationId": app_id,
        "affiliateId": affiliate_id,
        "keyword": keyword,
        "sort": "-reviewCount",
        "hits": limit,
        "formatVersion": "2",
    }
    url = RAKUTEN_ENDPOINT + "?" + urllib.parse.urlencode(params)

    products = []
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for item in data.get("Items", []):
            try:
                products.append({
                    "source": "rakuten",
                    "asin_or_id": str(item.get("itemCode", "")),
                    "title": item.get("itemName", ""),
                    "price": float(item["itemPrice"]) if item.get("itemPrice") is not None else None,
                    "rating": float(item["reviewAverage"]) if item.get("reviewAverage") else None,
                    "review_count": int(item["reviewCount"]) if item.get("reviewCount") else None,
                    "features": [],
                    "image_url": item.get("mediumImageUrls", [{}])[0].get("imageUrl", "") if item.get("mediumImageUrls") else "",
                    "affiliate_url": item.get("affiliateUrl") or item.get("itemUrl", ""),
                    "category": category_name,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.error("Rakuten item parse error (%s): %s", item.get("itemCode", "?"), e)

    except Exception as e:
        logger.error("Rakuten API error (keyword=%s): %s", keyword, e)

    return products


def collect_rakuten():
    app_id = os.environ.get("RAKUTEN_APP_ID")
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID")

    if not app_id or not affiliate_id:
        logger.error("RAKUTEN_APP_ID or RAKUTEN_AFFILIATE_ID is not set")
        return []

    keywords = [
        ("ガジェット スマートホーム", "ガジェット・家電"),
        ("イヤホン ワイヤレス", "ガジェット・家電"),
        ("スマートウォッチ", "ガジェット・家電"),
    ]

    all_products = []
    seen_ids = set()

    for keyword, category_name in keywords:
        logger.info("Fetching Rakuten keyword='%s'...", keyword)
        products = fetch_rakuten_genre(app_id, affiliate_id, keyword, category_name)
        for p in products:
            if p["asin_or_id"] not in seen_ids:
                seen_ids.add(p["asin_or_id"])
                all_products.append(p)
        time.sleep(1)

    # 上位10件に絞る
    all_products.sort(key=lambda x: x.get("review_count") or 0, reverse=True)
    return all_products[:10]


# ── メイン ────────────────────────────────────────────────────

def main():
    os.makedirs("data", exist_ok=True)

    products = []

    amazon_products = collect_amazon()
    products.extend(amazon_products)

    rakuten_products = collect_rakuten()
    products.extend(rakuten_products)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    amazon_count = sum(1 for p in products if p["source"] == "amazon")
    rakuten_count = sum(1 for p in products if p["source"] == "rakuten")
    print(f"Collected {len(products)} products (Amazon: {amazon_count}, Rakuten: {rakuten_count}) → {OUTPUT_PATH}")


if __name__ == "__main__":
    missing = [v for v in ["AMAZON_ACCESS_KEY", "AMAZON_SECRET_KEY", "AMAZON_ASSOCIATE_TAG"] if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    main()

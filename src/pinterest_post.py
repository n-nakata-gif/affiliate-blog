"""
Pinterest 自動投稿スクリプト
ブログ記事を Pinterest にピンとして投稿する。

対象ジャンル: gadget・gourmet・travel のみ
（business・investment はビジュアル訴求が弱いため対象外）

Pinterest API v5 を使用。OAuth2アクセストークンが必要。

必要なSecrets:
  PINTEREST_ACCESS_TOKEN : Pinterest OAuth2 アクセストークン
  UNSPLASH_API_KEY       : Unsplash API キー（縦長画像取得用）
  ANTHROPIC_API_KEY      : Claude API キー（説明文生成用）
"""

from __future__ import annotations
import json, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
import requests

JST = timezone(timedelta(hours=9))
PINTEREST_API_BASE = "https://api.pinterest.com/v5"

# ── Pinterest対象ジャンル（ビジュアル訴求が有効なカテゴリのみ）─────
PINTEREST_GENRES = {"gadget", "gourmet", "travel"}

BOARD_NAMES = {
    "gadget":  "Novlify ガジェット・テック",
    "gourmet": "Novlify グルメ・食",
    "travel":  "Novlify 旅行・観光",
}

BOARD_DESCRIPTIONS = {
    "gadget":  "最新ガジェット・テックアイテムのレビューと情報をまとめたNovlifyのボードです。",
    "gourmet": "グルメ・食の情報をお届けするNovlifyのボードです。",
    "travel":  "国内外の旅行・観光情報をまとめたNovlifyのボードです。",
}

GENRE_LABELS = {
    "gadget":  "ガジェット・テック",
    "gourmet": "グルメ・食",
    "travel":  "旅行・観光",
}

# Pinterestで効果的なキーワード（ジャンル別）
GENRE_IMAGE_QUERIES = {
    "gadget":  "technology gadget minimalist",
    "gourmet": "food photography delicious",
    "travel":  "travel destination japan",
}

# ── Pinterest専用説明文生成プロンプト ─────────────────────────────
_PINTEREST_DESC_PROMPT = """\
以下のブログ記事に対して、Pinterest投稿用の説明文を400〜480文字で生成してください。

条件：
- 読者が「保存したい」「読みたい」と思える価値ある内容にする
- 記事で扱うキーワード・関連ワードを自然に10〜15個含める（Pinterest検索に効果的）
- 「です・ます」調で書く
- 絵文字を2〜3個使用してもよい
- 最後に「詳しくはブログ（Novlify）で↓」という誘導文を入れる
- 宣伝・誇張表現は避ける
- 出力は説明文のみ（見出し・記号不要）

【ジャンル】{genre_label}
【記事タイトル】{title}
【記事の概要・冒頭300文字】{intro}
"""


def generate_pinterest_description(title: str, article_body: str, genre: str,
                                   anthropic_key: str) -> str:
    """Claude APIでPinterest専用の説明文（400〜480文字・キーワードリッチ）を生成"""
    if not anthropic_key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        # frontmatterを除いた本文の先頭300文字
        body_start = article_body.split("---", 2)[-1].strip()[:300]
        prompt = _PINTEREST_DESC_PROMPT.format(
            genre_label=GENRE_LABELS.get(genre, genre),
            title=title,
            intro=body_start,
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        desc = resp.content[0].text.strip()
        print(f"[Pinterest] 説明文生成: {len(desc)}文字")
        return desc[:500]  # Pinterest上限
    except Exception as e:
        print(f"[Pinterest] 説明文生成失敗（スキップ）: {e}")
        return ""


def fetch_portrait_image_url(genre: str, api_key: str) -> str:
    """Unsplash APIからPinterest向け縦長（portrait）画像URLを取得"""
    if not api_key:
        return ""
    query = GENRE_IMAGE_QUERIES.get(genre, "blog")
    params = {
        "query": query,
        "per_page": 5,
        "orientation": "portrait",   # ← 縦長画像を指定
        "content_filter": "high",
    }
    endpoint = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": f"Client-ID {api_key}",
                "Accept-Version": "v1",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return ""
        # 最初の画像をPinterest推奨サイズ（1000×1500）でリクエスト
        photo_id = results[0].get("id", "")
        base_url = results[0].get("urls", {}).get("raw", "")
        if base_url:
            # Unsplashのrawに幅・高さ・クロップを指定して2:3の縦長画像を生成
            portrait_url = f"{base_url}&w=1000&h=1500&fit=crop&crop=center"
            print(f"[Pinterest] 縦長画像取得: {portrait_url[:80]}...")
            return portrait_url
    except Exception as e:
        print(f"[Pinterest] 縦長画像取得失敗: {e}")
    return ""


# ── Pinterest API クライアント ─────────────────────────────────────
class PinterestClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def get_user_info(self) -> dict:
        resp = requests.get(f"{PINTEREST_API_BASE}/user_account",
                            headers=self.headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def list_boards(self) -> list:
        boards, bookmark = [], None
        while True:
            params = {"page_size": 25}
            if bookmark:
                params["bookmark"] = bookmark
            resp = requests.get(f"{PINTEREST_API_BASE}/boards",
                                headers=self.headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            boards.extend(data.get("items", []))
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        return boards

    def get_or_create_board(self, genre: str) -> str:
        board_name = BOARD_NAMES[genre]
        boards = self.list_boards()
        for b in boards:
            if b["name"] == board_name:
                print(f"[Pinterest] 既存ボード: {board_name} ({b['id']})")
                return b["id"]
        desc = BOARD_DESCRIPTIONS[genre]
        body = {"name": board_name, "description": desc, "privacy": "PUBLIC"}
        resp = requests.post(f"{PINTEREST_API_BASE}/boards",
                             headers=self.headers, json=body, timeout=15)
        resp.raise_for_status()
        board = resp.json()
        print(f"[Pinterest] ボード作成: {board_name} ({board['id']})")
        return board["id"]

    def create_pin(self, board_id: str, title: str, description: str,
                   link: str, image_url: str) -> dict:
        body = {
            "board_id": board_id,
            "title": title[:100],
            "description": description[:500],
            "link": link,
            "media_source": {"source_type": "image_url", "url": image_url},
        }
        resp = requests.post(f"{PINTEREST_API_BASE}/pins",
                             headers=self.headers, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()


# ── メイン投稿関数 ────────────────────────────────────────────────
def post_to_pinterest(title: str, description: str, link: str,
                      image_url: str, genre: str,
                      article_body: str = "",
                      anthropic_key: str = "",
                      unsplash_key: str = "") -> bool:
    """
    Pinterest にピンを投稿する。

    ① 縦長画像（Unsplash portrait）を優先使用
    ② Pinterest専用説明文をClaude APIで生成
    ③ gadget / gourmet / travel のみ投稿
    """
    # 対象ジャンルチェック
    if genre not in PINTEREST_GENRES:
        print(f"[Pinterest] {genre} は対象外ジャンルのためスキップ")
        return False

    token = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    if not token:
        print("[Pinterest] PINTEREST_ACCESS_TOKEN 未設定のためスキップ")
        return False

    # ① 縦長画像を取得（失敗時は元の画像を使用）
    _unsplash_key = unsplash_key or os.environ.get("UNSPLASH_API_KEY", "")
    portrait_url = fetch_portrait_image_url(genre, _unsplash_key)
    final_image_url = portrait_url if portrait_url else image_url
    if not final_image_url:
        print("[Pinterest] 画像URLなし・スキップ")
        return False

    # ② Pinterest専用説明文を生成（失敗時は元のdescriptionを使用）
    _anthropic_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
    pinterest_desc = ""
    if article_body and _anthropic_key:
        pinterest_desc = generate_pinterest_description(
            title, article_body, genre, _anthropic_key)
    final_description = pinterest_desc if pinterest_desc else description

    # Pinterest に接続・投稿
    client = PinterestClient(token)
    try:
        user = client.get_user_info()
        print(f"[Pinterest] 接続成功: @{user.get('username', '?')}")
    except requests.HTTPError as e:
        print(f"[Pinterest] 認証失敗: {e}")
        return False

    board_id = client.get_or_create_board(genre)
    pin = client.create_pin(board_id, title, final_description, link, final_image_url)
    pin_id = pin.get("id", "?")
    pin_url = f"https://www.pinterest.jp/pin/{pin_id}/"
    print(f"[Pinterest] 投稿完了: {pin_url}")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pinterest自動投稿")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--link", required=True)
    parser.add_argument("--image_url", default="")
    parser.add_argument("--genre", required=True, choices=list(PINTEREST_GENRES))
    parser.add_argument("--article_body", default="")
    args = parser.parse_args()
    success = post_to_pinterest(
        title=args.title,
        description=args.description,
        link=args.link,
        image_url=args.image_url,
        genre=args.genre,
        article_body=args.article_body,
    )
    sys.exit(0 if success else 1)

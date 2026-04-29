"""
Pinterest 自動投稿スクリプト
ブログ記事を Pinterest にピンとして投稿する。

Pinterest API v5 を使用。OAuth2アクセストークンが必要。

必要なSecrets:
  PINTEREST_ACCESS_TOKEN : Pinterest OAuth2 アクセストークン
"""

from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timedelta, timezone
import requests

JST = timezone(timedelta(hours=9))
PINTEREST_API_BASE = "https://api.pinterest.com/v5"

BOARD_NAMES = {
    "business":   "Novlify ビジネス・副業",
    "gadget":     "Novlify ガジェット・テック",
    "investment": "Novlify 投資・資産運用",
    "travel":     "Novlify 旅行・観光",
    "gourmet":    "Novlify グルメ・食",
}

BOARD_DESCRIPTIONS = {
    "business":   "副業・ビジネスに役立つ情報をお届けするNovlifyのボードです。",
    "gadget":     "最新ガジェット・テックアイテムのレビューと情報をまとめたNovlifyのボードです。",
    "investment": "投資・資産運用の知識と最新情報をお届けするNovlifyのボードです。",
    "travel":     "国内外の旅行・観光情報をまとめたNovlifyのボードです。",
    "gourmet":    "グルメ・食の情報をお届けするNovlifyのボードです。",
}

class PinterestClient:
    def __init__(self, access_token: str):
        self.token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def get_user_info(self) -> dict:
        resp = requests.get(f"{PINTEREST_API_BASE}/user_account", headers=self.headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def list_boards(self) -> list:
        boards = []
        bookmark = None
        while True:
            params = {"page_size": 25}
            if bookmark:
                params["bookmark"] = bookmark
            resp = requests.get(f"{PINTEREST_API_BASE}/boards", headers=self.headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            boards.extend(data.get("items", []))
            bookmark = data.get("bookmark")
            if not bookmark:
                break
        return boards

    def get_or_create_board(self, genre: str) -> str:
        board_name = BOARD_NAMES.get(genre, f"Novlify {genre}")
        boards = self.list_boards()
        for b in boards:
            if b["name"] == board_name:
                print(f"既存ボード使用: {board_name} ({b['id']})")
                return b["id"]
        desc = BOARD_DESCRIPTIONS.get(genre, f"Novlifyの{genre}カテゴリーボードです。")
        body = {"name": board_name, "description": desc, "privacy": "PUBLIC"}
        resp = requests.post(f"{PINTEREST_API_BASE}/boards", headers=self.headers, json=body, timeout=15)
        resp.raise_for_status()
        board = resp.json()
        print(f"ボード作成: {board_name} ({board['id']})")
        return board["id"]

    def create_pin(self, board_id: str, title: str, description: str, link: str, image_url: str) -> dict:
        body = {
            "board_id": board_id,
            "title": title[:100],
            "description": description[:500],
            "link": link,
            "media_source": {"source_type": "image_url", "url": image_url},
        }
        resp = requests.post(f"{PINTEREST_API_BASE}/pins", headers=self.headers, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()


def post_to_pinterest(title: str, description: str, link: str, image_url: str, genre: str) -> bool:
    token = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
    if not token:
        print("PINTEREST_ACCESS_TOKEN未設定のためスキップ")
        return False
    client = PinterestClient(token)
    try:
        user = client.get_user_info()
        print(f"Pinterest接続成功: @{user.get('username', '?')}")
    except requests.HTTPError as e:
        print(f"Pinterest認証失敗: {e}")
        return False
    board_id = client.get_or_create_board(genre)
    pin = client.create_pin(board_id, title, description, link, image_url)
    pin_id = pin.get("id", "?")
    pin_url = f"https://www.pinterest.jp/pin/{pin_id}/"
    print(f"Pinterest投稿完了: {pin_url}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pinterest自動投稿")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--link", required=True)
    parser.add_argument("--image_url", required=True)
    parser.add_argument("--genre", default="gadget", choices=list(BOARD_NAMES.keys()))
    args = parser.parse_args()
    success = post_to_pinterest(args.title, args.description, args.link, args.image_url, args.genre)
    sys.exit(0 if success else 1)

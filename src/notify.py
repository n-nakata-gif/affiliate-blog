import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# ハッシュタグは2〜3個に絞る（多すぎるとスパム判定・エンゲージメント低下）
# #PR はアフィリエイト記事の景品表示法対策で必須
_X_HASHTAGS = {
    "business":   "#副業 #PR #Novlify",
    "gadget":     "#ガジェット #PR #Novlify",
    "investment": "#資産運用 #PR #Novlify",
    "travel":     "#旅行 #PR #Novlify",
    "gourmet":    "#グルメ #PR #Novlify",
}

# ジャンル別エンゲージメント促進フレーズ（リプライ・保存・クリックを促す）
_X_ENGAGEMENT = {
    "business":   "副業・仕事探しの参考にどうぞ🙌",
    "gadget":     "購入前にぜひチェックしてみてください🔍",
    "investment": "投資の参考になれば嬉しいです📊",
    "travel":     "旅の計画に役立てていただければ✈️",
    "gourmet":    "気になったらぜひチェックを🍽️",
}

_X_ESSENCE_PROMPT = """\
次のブログ記事の「読む価値が伝わるエッセンス」を80〜100文字で生成してください。

条件：
- 記事の最も重要なポイントや読者へのメリットを1〜2文に凝縮する
- 「〜の方法」「〜のコツ」など具体的なベネフィットを含める
- 「です・ます」調
- 宣伝・誘導文句は避け、素直な情報として書く
- 絵文字は1〜2個まで使用可
- 出力は本文のみ（見出し・記号・改行不要）

【記事タイトル】
{title}

【記事の冒頭300文字】
{intro}
"""


def generate_x_essence(article_type: str, title: str, article_body: str) -> str:
    """Claude APIで記事のエッセンス（約100文字）を生成する"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ""
    try:
        import anthropic
        from generate import MODEL
        client = anthropic.Anthropic(api_key=api_key)
        # frontmatterを除いた本文の先頭300文字を使用
        body_start = article_body.split("---", 2)[-1].strip()[:300]
        prompt = _X_ESSENCE_PROMPT.format(title=title, intro=body_start)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[X] エッセンス生成失敗（スキップ）: {e}")
        return ""


def post_to_x(article_type: str, title: str, blog_url: str,
              article_body: str = "") -> None:
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_SECRET")

    print(f"[X] API KEY設定: {bool(api_key)}, SECRET設定: {bool(api_secret)}, "
          f"ACCESS TOKEN設定: {bool(access_token)}, ACCESS SECRET設定: {bool(access_secret)}")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("X APIキー未設定のためスキップ")
        return

    print(f"[X] API_KEY先頭: {api_key[:4]}..., ACCESS_TOKEN先頭: {access_token[:4]}...")

    try:
        import tweepy
        print(f"[X] tweepyバージョン: {tweepy.__version__}")
    except ImportError:
        print("tweepyが見つかりません。スキップ")
        return

    hashtags = _X_HASHTAGS.get(article_type, "#Novlify")
    engagement = _X_ENGAGEMENT.get(article_type, "ぜひチェックしてみてください👀")

    # 記事のエッセンスを生成（約100文字）
    essence = ""
    if article_body:
        essence = generate_x_essence(article_type, title, article_body)

    # エッセンスが取れなければタイトルで代替
    if not essence:
        essence = title

    # 文字数調整（URL は t.co で23字固定）
    url_chars = 23
    max_essence = 280 - url_chars - len(hashtags) - len(engagement) - 4  # 改行3 + 余白1
    if len(essence) > max_essence:
        essence = essence[: max_essence - 1] + "…"

    tweet = f"{essence}\n{engagement}\n{blog_url}\n{hashtags}"
    print(f"[X] ツイート文字数: {len(tweet)}")
    print(f"[X] ツイート内容:\n{tweet}")

    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )

    try:
        response = client.create_tweet(text=tweet)
        print(f"X投稿完了: tweet_id={response.data['id']}")
    except tweepy.errors.Unauthorized as e:
        print(f"ERROR: X投稿失敗 - 401 Unauthorized")
        print(f"  原因: アプリの権限が「読み取り専用」になっているか、アクセストークンが無効です。")
        print(f"  対処: Twitter Developer Portalでアプリの権限を「Read and Write」に変更し、")
        print(f"        Access TokenとAccess Token Secretを再生成してGitHub Secretsを更新してください。")
        print(f"  詳細: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  レスポンス: {e.response.text}")
    except tweepy.errors.Forbidden as e:
        print(f"ERROR: X投稿失敗 - 403 Forbidden")
        print(f"  原因: このアカウントまたはAppで投稿が禁止されています。")
        print(f"  詳細: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  レスポンス: {e.response.text}")
    except tweepy.errors.TweepyException as e:
        print(f"ERROR: X投稿失敗 (TweepyException): {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  レスポンス: {e.response.text}")
    except Exception as e:
        print(f"ERROR: X投稿失敗 (予期しないエラー): {type(e).__name__}: {e}")

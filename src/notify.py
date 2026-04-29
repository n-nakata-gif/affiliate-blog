import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

_X_HASHTAGS = {
    "business": "#副業 #ビジネス #Novlify",
    "gadget": "#ガジェット #テック #Novlify",
    "investment": "#投資 #資産運用 #Novlify",
    "travel": "#旅行 #国内旅行 #Novlify",
    "gourmet": "#グルメ #食 #Novlify",
}

_X_INTROS = {
    "business": "副業・ビジネスで差をつけるヒントをお届けします。",
    "gadget": "話題のガジェットをピックアップしました。",
    "investment": "資産を育てるための最新情報をまとめました。",
    "travel": "次の旅先選びに役立つ情報をご紹介します。",
    "gourmet": "食通も唸る一品を発見しました。",
}


def post_to_x(article_type: str, title: str, blog_url: str) -> None:
    api_key = os.environ.get("X_API_KEY")
    api_secret = os.environ.get("X_API_SECRET")
    access_token = os.environ.get("X_ACCESS_TOKEN")
    access_secret = os.environ.get("X_ACCESS_SECRET")

    print(f"[X] API KEY設定: {bool(api_key)}, SECRET設定: {bool(api_secret)}, "
          f"ACCESS TOKEN設定: {bool(access_token)}, ACCESS SECRET設定: {bool(access_secret)}")

    if not all([api_key, api_secret, access_token, access_secret]):
        print("X APIキー未設定のためスキップ")
        return

    # 先頭4文字のみ表示して認証情報を確認
    print(f"[X] API_KEY先頭: {api_key[:4]}..., ACCESS_TOKEN先頭: {access_token[:4]}...")

    try:
        import tweepy
        print(f"[X] tweepyバージョン: {tweepy.__version__}")
    except ImportError:
        print("tweepyが見つかりません。スキップ")
        return

    intro = _X_INTROS.get(article_type, "新しい記事を投稿しました。")
    hashtags = _X_HASHTAGS.get(article_type, "#Novlify")

    # Twitterは短縮URL(t.co)を23字として計算
    url_chars = 23
    fixed_len = len(intro) + 1 + 1 + url_chars + 1 + len(hashtags)
    max_title_len = 140 - fixed_len
    trimmed = title if len(title) <= max_title_len else title[: max_title_len - 1] + "…"

    tweet = f"{intro}\n{trimmed}\n{blog_url}\n{hashtags}"
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

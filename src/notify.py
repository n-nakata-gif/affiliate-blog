import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

ACCENT = {
    "business": "#4CAF50",
    "gadget": "#FF9800",
    "investment": "#2196F3",
    "travel": "#00BCD4",
    "gourmet": "#E91E63",
}

SUBJECT_TEMPLATE = {
    "business": "【NEXIGEN】ビジネス記事を投稿しました｜{title}",
    "gadget": "【NEXIGEN】ガジェット記事を投稿しました｜{title}",
    "investment": "【NEXIGEN】投資記事を投稿しました｜{title}",
    "travel": "【NEXIGEN】旅行記事を投稿しました｜{title}",
    "gourmet": "【NEXIGEN】グルメ記事を投稿しました｜{title}",
}

_LABELS = {
    "business": "ビジネス",
    "gadget": "ガジェット",
    "investment": "投資",
    "travel": "旅行",
    "gourmet": "グルメ",
}

_X_HASHTAGS = {
    "business": "#副業 #ビジネス #NEXIGEN",
    "gadget": "#ガジェット #テック #NEXIGEN",
    "investment": "#投資 #資産運用 #NEXIGEN",
    "travel": "#旅行 #国内旅行 #NEXIGEN",
    "gourmet": "#グルメ #食 #NEXIGEN",
}

_X_INTROS = {
    "business": "副業・ビジネスで差をつけるヒントをお届けします。",
    "gadget": "話題のガジェットをピックアップしました。",
    "investment": "資産を育てるための最新情報をまとめました。",
    "travel": "次の旅先選びに役立つ情報をご紹介します。",
    "gourmet": "食通も唸る一品を発見しました。",
}


def _build_html(article_type, title, article_url, blog_url, tags, word_count):
    now_jst = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M JST")
    accent = ACCENT.get(article_type, "#4CAF50")
    label = _LABELS.get(article_type, article_type)

    tags_html = ""
    if tags:
        pills = "".join(
            f'<span style="display:inline-block;background:#e8e8e8;border-radius:12px;'
            f'padding:3px 10px;margin:2px;font-size:13px;color:#555;">{t}</span>'
            for t in tags
        )
        tags_html = f'<div style="margin:10px 0;">{pills}</div>'

    badge_html = ""
    if word_count:
        badge_html = (
            f'<div style="margin-top:8px;">'
            f'<span style="display:inline-block;background:{accent};color:#fff;'
            f'border-radius:4px;padding:2px 12px;font-size:13px;">'
            f'{word_count:,}字</span></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
body{{margin:0;padding:0;background:#f4f4f4;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:16px;}}
.wrap{{max-width:600px;width:100%;margin:0 auto;background:#fff;}}
.hd{{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:32px 24px;text-align:center;}}
.hd h1{{margin:0;color:#fff;font-size:22px;font-weight:700;letter-spacing:.05em;}}
.hd .badge{{display:inline-block;background:{accent};color:#fff;border-radius:20px;
  padding:4px 16px;font-size:13px;margin-top:10px;font-weight:600;}}
.bd{{padding:32px 24px;}}
.date{{color:#888;font-size:14px;margin-bottom:12px;}}
.title{{font-size:20px;font-weight:700;color:#1a1a2e;line-height:1.4;margin:0 0 12px;}}
.btn{{display:inline-block;padding:12px 24px;border-radius:6px;text-decoration:none;
  font-weight:600;font-size:15px;margin:6px 4px;}}
.btn-gh{{background:#24292e;color:#fff;}}
.btn-blog{{background:{accent};color:#fff;}}
.ft{{background:#f9f9f9;border-top:1px solid #eee;padding:16px 24px;
  text-align:center;color:#aaa;font-size:13px;}}
@media(max-width:600px){{
  .btn{{display:block;width:100%;box-sizing:border-box;text-align:center;margin:6px 0;}}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hd">
    <h1>NEXIGEN 記事投稿完了</h1>
    <span class="badge">{label}</span>
  </div>
  <div class="bd">
    <div class="date">{now_jst}</div>
    <div class="title">{title}</div>
    {tags_html}
    {badge_html}
    <div style="margin-top:24px;">
      <a href="{article_url}" class="btn btn-gh" target="_blank">GitHubで確認</a>
      <a href="{blog_url}" class="btn btn-blog" target="_blank">ブログで確認</a>
    </div>
  </div>
  <div class="ft">このメールはNEXIGEN自動投稿システムから送信されました</div>
</div>
</body>
</html>"""


def send_notification(
    article_type: str,
    title: str,
    article_url: str,
    blog_url: str,
    tags: list = None,
    word_count: int = 0,
) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        return

    subject = SUBJECT_TEMPLATE.get(
        article_type, "【NEXIGEN】記事を投稿しました｜{title}"
    ).format(title=title)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    msg.attach(MIMEText(
        _build_html(article_type, title, article_url, blog_url, tags, word_count),
        "html", "utf-8",
    ))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())
        print("メール送信完了")
    except Exception as e:
        print(f"ERROR: メール送信失敗: {e}")


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
    hashtags = _X_HASHTAGS.get(article_type, "#NEXIGEN")

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

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

ACCENT = {
    "business": "#4CAF50",
    "gadget": "#FF9800",
}

SUBJECT_TEMPLATE = {
    "business": "【NEXIGEN】ビジネス記事を投稿しました｜{title}",
    "gadget": "【NEXIGEN】ガジェット記事を投稿しました｜{title}",
}


def _build_html(article_type, title, article_url, blog_url, tags, word_count):
    now_jst = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M JST")
    accent = ACCENT.get(article_type, "#4CAF50")
    label = "ビジネス" if article_type == "business" else "ガジェット"

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

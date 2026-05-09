"""
週次収益レポートスクリプト
毎週月曜 10:00 JST に実行し、各収益源の状況をメールで送信する。

【AdSense 自動連携の設定方法】
  1. Google Cloud Console で「AdSense API」を有効化する
  2. AdSense 管理画面 → アカウント → ユーザー管理 → サービスアカウントのメールアドレスを追加（閲覧者）
  3. GitHub Secrets に ADSENSE_PUBLISHER_ID を登録（例: pub-1234567890123456）
  ※ GA4_SERVICE_ACCOUNT_JSON は GA4 と共用できる

【必要なSecrets】
  GMAIL_USER / GMAIL_APP_PASSWORD （必須）
  GA4_SERVICE_ACCOUNT_JSON         （AdSense 連携に使用・既存流用）
  ADSENSE_PUBLISHER_ID             （AdSense 連携・未設定時はスキップ）
"""

from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

JST = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"

# 各プラットフォームのダッシュボード URL
PLATFORM_LINKS = {
    "Google AdSense":   "https://adsense.google.com/adsense/",
    "A8.net":           "https://www.a8.net/a8v2/asTransaction.f?currency=jpy",
    "ValueCommerce":    "https://k.valuecommerce.com/affiliate/report/",
    "Amazon アソシエイト": "https://affiliate.amazon.co.jp/home/reports/summary",
    "楽天アフィリエイト":   "https://affiliate.rakuten.co.jp/reports/summary/",
}


# ---------------------------------------------------------------------------
# AdSense API
# ---------------------------------------------------------------------------

def fetch_adsense_data(publisher_id: str) -> dict | None:
    """AdSense Management API v2 で先週の収益データを取得する。失敗時は None を返す。"""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            print("GA4_SERVICE_ACCOUNT_JSON 未設定 → AdSense スキップ")
            return None

        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/adsense.readonly"],
        )
        service = build("adsense", "v2", credentials=creds, cache_discovery=False)

        today = datetime.now(JST).date()
        last_monday = today - timedelta(days=today.weekday() + 7)
        last_sunday  = last_monday + timedelta(days=6)

        account_name = "accounts/" + publisher_id.replace("pub-", "pub%2D") if "/" not in publisher_id else publisher_id
        # publisher_id が "pub-XXXX" 形式の場合は accounts/pub-XXXX に変換
        account_name = "accounts/" + publisher_id

        report = service.accounts().reports().generate(
            account=account_name,
            dateRange="CUSTOM",
            startDate_year=last_monday.year,
            startDate_month=last_monday.month,
            startDate_day=last_monday.day,
            endDate_year=last_sunday.year,
            endDate_month=last_sunday.month,
            endDate_day=last_sunday.day,
            metrics=["ESTIMATED_EARNINGS", "PAGE_VIEWS", "IMPRESSIONS", "CLICKS", "PAGE_RPM"],
        ).execute()

        totals = report.get("totals", {}).get("cells", [])
        if not totals:
            return {"earnings": 0, "pageviews": 0, "impressions": 0, "clicks": 0, "rpm": 0,
                    "period": f"{last_monday} 〜 {last_sunday}"}

        def cell(i):
            try:
                return float(totals[i].get("value", 0))
            except (IndexError, TypeError, ValueError):
                return 0.0

        return {
            "earnings":    round(cell(0), 2),
            "pageviews":   int(cell(1)),
            "impressions": int(cell(2)),
            "clicks":      int(cell(3)),
            "rpm":         round(cell(4), 2),
            "period":      f"{last_monday} 〜 {last_sunday}",
        }

    except Exception as e:
        print(f"AdSense 取得失敗（スキップ）: {e}")
        return None


# ---------------------------------------------------------------------------
# 今週の記事集計
# ---------------------------------------------------------------------------

def count_new_articles() -> dict:
    """今週（月〜日）公開された記事の本数とジャンル内訳を返す"""
    today = datetime.now(JST).date()
    monday = today - timedelta(days=today.weekday())

    genre_count: dict[str, int] = {}
    total = 0

    for path in BLOG_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        end = content.find("\n---", 3)
        if end == -1:
            continue
        meta: dict = {}
        for line in content[3:end].strip().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"').strip("'")

        pub_str = meta.get("pubDate", "")
        try:
            from datetime import date
            pub = date.fromisoformat(pub_str)
        except ValueError:
            continue

        if pub >= monday:
            total += 1
            genre = "その他"
            slug = path.stem
            for g in ["business", "gadget", "investment", "travel", "gourmet"]:
                if g in slug:
                    genre = g
                    break
            genre_count[genre] = genre_count.get(genre, 0) + 1

    return {"total": total, "by_genre": genre_count}


# ---------------------------------------------------------------------------
# HTML レポート生成
# ---------------------------------------------------------------------------

def build_html(adsense: dict | None, articles: dict, date_str: str) -> str:

    # ---- AdSense セクション ----
    if adsense:
        earnings_str = f"¥{adsense['earnings']:,.0f}" if adsense['earnings'] >= 0 else "—"
        rpm_str      = f"¥{adsense['rpm']:.2f}"
        adsense_section = (
            "<h2 style='border-left:4px solid #4ade80;padding-left:10px;'>💰 Google AdSense（先週）</h2>"
            "<p style='color:#666;font-size:13px;'>集計期間: " + adsense["period"] + "</p>"
            "<div style='display:flex;gap:12px;flex-wrap:wrap;margin:12px 0;'>"
            + _card("推定収益",    earnings_str,             "#22c55e")
            + _card("ページRPM",   rpm_str,                  "#6366f1")
            + _card("ページビュー", f"{adsense['pageviews']:,}", "#f59e0b")
            + _card("クリック数",   str(adsense["clicks"]),   "#ec4899")
            + "</div>"
        )
    else:
        adsense_section = (
            "<h2 style='border-left:4px solid #4ade80;padding-left:10px;'>💰 Google AdSense</h2>"
            "<div style='background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:14px;font-size:14px;'>"
            "⚙ <strong>未連携</strong>：GitHub Secrets に <code>ADSENSE_PUBLISHER_ID</code> を追加すると自動集計が開始されます。<br>"
            "<a href='https://adsense.google.com/adsense/' style='color:#1d4ed8;'>AdSense ダッシュボード →</a>"
            "</div>"
        )

    # ---- 記事数 ----
    genre_labels = {"business":"ビジネス","gadget":"ガジェット","investment":"投資","travel":"旅行","gourmet":"グルメ","その他":"その他"}
    genre_rows = "".join(
        f"<li>{genre_labels.get(g, g)}: {c}本</li>"
        for g, c in articles["by_genre"].items()
    )
    articles_section = (
        "<h2 style='border-left:4px solid #60a5fa;padding-left:10px;'>📝 今週の記事投稿</h2>"
        "<p>今週公開: <strong>" + str(articles["total"]) + "本</strong></p>"
        + (f"<ul style='color:#555;'>{genre_rows}</ul>" if genre_rows else "<p style='color:#888;'>今週の投稿なし</p>")
    )

    # ---- 各プラットフォームリンク ----
    links_html = "".join(
        f"<li><a href='{url}' style='color:#1d4ed8;'>{name}</a></li>"
        for name, url in PLATFORM_LINKS.items()
    )
    links_section = (
        "<h2 style='border-left:4px solid #f97316;padding-left:10px;'>🔗 各プラットフォームの確認</h2>"
        "<p style='font-size:13px;color:#666;'>以下のリンクから各プラットフォームの収益・成果を手動確認できます：</p>"
        f"<ul style='line-height:2;'>{links_html}</ul>"
        "<p style='background:#f0f4ff;border-radius:8px;padding:12px;font-size:13px;color:#555;'>"
        "💡 A8.net・ValueCommerce・Amazon・楽天アフィリエイトの自動集計は、"
        "各プラットフォームの API 資格情報を GitHub Secrets に追加することで実装可能です。"
        "</p>"
    )

    return (
        "<html><body style='font-family:sans-serif;max-width:680px;margin:0 auto;color:#333;'>"
        "<div style='background:#1a1a2e;color:#fff;padding:24px;border-radius:10px 10px 0 0;'>"
        "<h1 style='margin:0;font-size:22px;'>💴 Novlify 週次収益レポート</h1>"
        "<p style='margin:6px 0 0;color:#aaa;font-size:14px;'>" + date_str + " 自動生成</p>"
        "</div>"
        "<div style='background:#fff;padding:20px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;'>"
        + adsense_section
        + "<hr style='border:none;border-top:1px solid #e5e7eb;margin:20px 0;'>"
        + articles_section
        + "<hr style='border:none;border-top:1px solid #e5e7eb;margin:20px 0;'>"
        + links_section
        + "<p style='color:#aaa;font-size:12px;margin-top:24px;'>GitHub Actions により自動送信。AdSense データは推定値です。</p>"
        "</div></body></html>"
    )


def _card(label: str, value: str, color: str) -> str:
    return (
        "<div style='flex:1;min-width:120px;background:" + color + ";color:#fff;"
        "border-radius:10px;padding:14px;text-align:center;'>"
        "<div style='font-size:22px;font-weight:bold;'>" + value + "</div>"
        "<div style='font-size:12px;margin-top:4px;'>" + label + "</div>"
        "</div>"
    )


# ---------------------------------------------------------------------------
# メール送信
# ---------------------------------------------------------------------------

def send_email(html: str, date_str: str) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw   = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail 未設定のためスキップ")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【Novlify】収益週次レポート {date_str}"
    msg["From"] = gmail_user
    msg["To"]   = gmail_user
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())
    print("収益レポートを送信しました: " + gmail_user)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    now = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d")

    print("収益レポート生成中...")

    # AdSense（任意）
    publisher_id = os.environ.get("ADSENSE_PUBLISHER_ID", "")
    adsense_data = None
    if publisher_id:
        print("AdSense データ取得中...")
        adsense_data = fetch_adsense_data(publisher_id)
    else:
        print("ADSENSE_PUBLISHER_ID 未設定 → AdSense スキップ")

    # 記事集計
    articles = count_new_articles()
    print(f"今週の記事: {articles['total']}本")

    # HTML 生成 & 送信
    html = build_html(adsense_data, articles, date_str)
    send_email(html, date_str)
    print("完了")

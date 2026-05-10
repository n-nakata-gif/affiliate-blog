"""
週次まとめメール送信スクリプト
data/weekly_reports/ 内の各レポートを1通にまとめてGmailで送信する。
weekly_report.yml の最終ステップから呼ばれる。
"""
from __future__ import annotations
import os, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

JST      = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent.parent / "data"
REPORT_DIR = DATA_DIR / "weekly_reports"

SECTIONS = [
    ("ga4.txt",         "📊 アクセス解析（GA4）"),
    ("revenue.txt",     "💰 収益レポート"),
    ("quality.txt",     "🔍 品質チェック"),
    ("quality_fix.txt", "🔧 自動修正ログ"),
    ("keywords.txt",    "🔑 来週のキーワード提案"),
    ("ranking.txt",     "📈 検索順位"),
]

SEP = "━" * 36


def build_body(date_str: str) -> str:
    parts = [f"Novlify 週次レポート | {date_str}", ""]
    found_any = False
    for filename, title in SECTIONS:
        path = REPORT_DIR / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        parts += [SEP, title, SEP, content, ""]
        found_any = True
    if not found_any:
        parts.append("（レポートデータがありません）")
    return "\n".join(parts)


def send_summary(body: str, date_str: str) -> None:
    u = os.environ.get("GMAIL_USER")
    p = os.environ.get("GMAIL_APP_PASSWORD")
    if not u or not p:
        print("Gmail未設定のためスキップ")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"【Novlify】週次レポート | {date_str}"
    msg["From"] = msg["To"] = u
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.login(u, p)
        s.sendmail(u, u, msg.as_bytes())
    print("週次まとめメール送信完了")


if __name__ == "__main__":
    date_str = datetime.now(JST).strftime("%Y/%m/%d")
    body = build_body(date_str)
    print(body)
    send_summary(body, date_str)

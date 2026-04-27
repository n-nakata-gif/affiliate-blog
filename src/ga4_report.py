"""
GA4 自動分析レポート
毎週月曜に先週のPV・流入・記事別データを取得してGmailで送信する。

必要なSecrets:
  GA4_PROPERTY_ID  : GA4プロパティID (数字のみ, 例: 123456789)
  GA4_SERVICE_ACCOUNT_JSON : サービスアカウントJSON (文字列全体)
  GMAIL_USER / GMAIL_APP_PASSWORD
"""

from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

JST = timezone(timedelta(hours=9))

def _ga4_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2 import service_account
    sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        raise RuntimeError("GA4_SERVICE_ACCOUNT_JSON が未設定です")
    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    )
    return BetaAnalyticsDataClient(credentials=creds)

def fetch_ga4_report(property_id: str) -> dict:
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, OrderBy, RunReportRequest
    client = _ga4_client()
    today = datetime.now(JST).date()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday  = last_monday + timedelta(days=6)
    date_range = DateRange(start_date=str(last_monday), end_date=str(last_sunday))
    summary_req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        metrics=[Metric(name="screenPageViews"),Metric(name="sessions"),Metric(name="activeUsers"),Metric(name="averageSessionDuration"),Metric(name="bounceRate")],
    )
    summary_resp = client.run_report(summary_req)
    row = summary_resp.rows[0].metric_values if summary_resp.rows else None
    summary = {
        "pageviews": int(row[0].value) if row else 0,
        "sessions": int(row[1].value) if row else 0,
        "users": int(row[2].value) if row else 0,
        "avg_session_sec": float(row[3].value) if row else 0.0,
        "bounce_rate": float(row[4].value) if row else 0.0,
    }
    pages_req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="pageTitle"), Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=10,
    )
    pages_resp = client.run_report(pages_req)
    top_pages = [{"title":r.dimension_values[0].value,"path":r.dimension_values[1].value,"pv":int(r.metric_values[0].value)} for r in pages_resp.rows]
    channels_req = RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[date_range],
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[Metric(name="sessions")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=8,
    )
    channels_resp = client.run_report(channels_req)
    channels = [{"channel":r.dimension_values[0].value,"sessions":int(r.metric_values[0].value)} for r in channels_resp.rows]
    return {"period":f"{last_monday} 〜 {last_sunday}","summary":summary,"top_pages":top_pages,"channels":channels}

def send_report(data: dict) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail未設定のためスキップ")
        return
    period = data["period"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【NEXIGEN】週次レポート {period}"
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    body = f"""<html><body><h1>NEXIGEN GA4レポート</h1>
    <p>期間: {data['period']}</p>
    <p>PV: {data['summary']['pageviews']:,} / セッション: {data['summary']['sessions']:,} / ユーザー: {data['summary']['users']:,}</p>
    <h2>記事別TOP10</h2><ul>"""
    for p in data['top_pages']:
        body += f"<li>{p['title']}: {p['pv']:,} PV</li>"
    body += "</ul><h2>流入チャネル</h2><ul>"
    for c in data['channels']:
        body += f"<li>{c['channel']}: {c['sessions']:,}回</li>"
    body += "</ul></body></html>"
    msg.attach(MIMEText(body, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())
    print("GA4レポートメール送信完了")

if __name__ == "__main__":
    property_id = os.environ.get("GA4_PROPERTY_ID", "")
    if not property_id:
        print("GA4_PROPERTY_ID未設定のためスキップ")
        raise SystemExit(0)
    print("GA4データ取得中...")
    try:
        report = fetch_ga4_report(property_id)
    except Exception as e:
        print(f"GA4取得失敗（スキップ）: {e}")
        raise SystemExit(0)
    print(f"期間: {report['period']}")
    print(f"PV: {report['summary']['pageviews']}, Sessions: {report['summary']['sessions']}")
    send_report(report)

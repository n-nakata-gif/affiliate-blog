"""
キーワード選定自動化スクリプト
Search Console API → 流入キーワード分析 → Claude で次回記事テーマ提案
結果は data/keyword_suggestions.json に保存し、Gmailで送信する。

必要なSecrets:
  GSC_SITE_URL              : https://your-domain.com
  GSC_SERVICE_ACCOUNT_JSON  : サービスアカウントJSON文字列
  ANTHROPIC_API_KEY
  GMAIL_USER / GMAIL_APP_PASSWORD
"""

from __future__ import annotations
import json, os, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent.parent / "data"


def fetch_search_console_data(site_url: str) -> dict:
    """過去28日間の検索キーワードデータを取得"""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_json = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        raise RuntimeError("GSC_SERVICE_ACCOUNT_JSON が未設定です")

    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    service = build("searchconsole", "v1", credentials=creds)

    today = datetime.now(JST).date()
    end_date   = today - timedelta(days=3)
    start_date = end_date - timedelta(days=27)

    q_resp = service.searchanalytics().query(siteUrl=site_url, body={
        "startDate": str(start_date), "endDate": str(end_date),
        "dimensions": ["query"], "rowLimit": 100,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
    }).execute()
    queries = [{"query":r["keys"][0],"clicks":r.get("clicks",0),"impressions":r.get("impressions",0),
                "ctr":round(r.get("ctr",0)*100,2),"position":round(r.get("position",0),1)}
               for r in q_resp.get("rows",[])]

    p_resp = service.searchanalytics().query(siteUrl=site_url, body={
        "startDate": str(start_date), "endDate": str(end_date),
        "dimensions": ["page"], "rowLimit": 20,
        "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
    }).execute()
    pages = [{"page":r["keys"][0],"clicks":r.get("clicks",0),"impressions":r.get("impressions",0),
              "ctr":round(r.get("ctr",0)*100,2),"position":round(r.get("position",0),1)}
             for r in p_resp.get("rows",[])]

    opportunity_keywords = sorted(
        [q for q in queries if 4 <= q["position"] <= 20 and q["impressions"] >= 50],
        key=lambda x: x["impressions"], reverse=True
    )

    return {
        "period": f"{start_date} 〜 {end_date}",
        "top_queries": queries[:30],
        "top_pages": pages[:10],
        "opportunity_keywords": opportunity_keywords[:20],
    }


def generate_theme_suggestions(sc_data: dict) -> list:
    """Claude API で次回記事テーマを5ジャンル×2テーマ提案"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""あなたはSEOとコンテンツ戦略の専門家です。
以下のSearch Consoleデータを分析して、NEXIGENブログの次回記事テーマを提案してください。

【ブログジャンル】business/gadget/investment/travel/gourmet

【流入TOP20キーワード】
{json.dumps(sc_data['top_queries'][:20], ensure_ascii=False)}

【SEO機会キーワード【4〜20位】
{json.dumps(sc_data['opportunity_keywords'][:10], ensure_ascii=False)}

各ジャンル2テーマずつ、JSONのみで返答（前置き・コードブロック不要）:
[{{"genre":"business","themes":[{{"title":"記事タイトル案","target_keyword":"狙うKW","reason":"理由(50字以内)","priority":"high|medium"}}]}}...]"""

    resp = client.messages.create(model="claude-opus-4-5", max_tokens=2000,
                                  messages=[{"role":"user","content":prompt}])
    raw = resp.content[0].text.strip()
    if raw.startswith("```"): raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"): raw = "\n".join(raw.split("\n")[:-1])
    return json.loads(raw.strip())


def send_keyword_report(sc_data: dict, suggestions: list) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw   = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail未設定のためスキップ")
        return
    now_str = datetime.now(JST).strftime("%Y/%m/%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【NEXIGEN】キーワード分析＆テーマ提案 {now_str}"
    msg["From"] = gmail_user
    msg["To"] = gmail_user
    body = f"""<html><body>
    <h1>NEXIGEN キーワード分析レポート</h1>
    <p>対象期間: {sc_data['period']}</p>
    <h2>🔍 流入キーワード TOP10</h2><ul>"""
    for q in sc_data['top_queries'][:10]:
        body += f"<li>{q['query']}: {q['clicks']}クリック / {q['impressions']:,}表示 / CTR {q['ctr']}% / {q['position']}位</li>"
    body += "</ul><h2>🚀 SEO機会キーワード TOP5</h2><ul>"
    for q in sc_data['opportunity_keywords'][:5]:
        body += f"<li>{q['query']}: 現在{q['position']}位 / {q['impressions']:,}表示</li>"
    body += "</ul><h2>✍️ AI提案: 次回記事テーマ</h2>"
    for g in suggestions:
        body += f"<h3>{g['genre']}</h3><ul>"
        for t in g.get('themes', []):
            body += f"<li><strong>{t['title']}</strong><br>KW: {t['target_keyword']} / {t['reason']}</li>"
        body += "</ul>"
    body += "</body></html>"
    msg.attach(MIMEText(body, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())
    print("キーワードレポートメール送信完了")


def save_suggestions(suggestions: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / "keyword_suggestions.json"
    out_path.write_text(json.dumps({
        "generated_at": datetime.now(JST).isoformat(),
        "suggestions": suggestions,
    }, ensure_ascii=False, indent=2))
    print(f"キーワード提案を保存: {out_path}")


if __name__ == "__main__":
    site_url = os.environ.get("GSC_SITE_URL", "")
    if not site_url:
        print("GSC_SITE_URL未設定のためスキップ")
        raise SystemExit(0)
    print("Search Consoleデータ取得中...")
    try:
        sc_data = fetch_search_console_data(site_url)
    except Exception as e:
        print(f"Search Console取得失敗: {e}")
        raise SystemExit(1)
    print(f"期間: {sc_data['period']}")
    print(f"クエリ数: {len(sc_data['top_queries'])}, 機会KW: {len(sc_data['opportunity_keywords'])}")
    print("Claude でテーマ提案中...")
    suggestions = generate_theme_suggestions(sc_data)
    print(f"テーマ提案: {len(suggestions)} ジャンル")
    save_suggestions(suggestions)
    send_keyword_report(sc_data, suggestions)

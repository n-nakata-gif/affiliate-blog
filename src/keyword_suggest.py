"""
キーワード選定自動化スクリプト（GSC不要版）
Search Console API が設定されていない場合は Claude が直接キーワード提案を行う。
GSC が設定されている場合は Search Console データを使って提案する。

必要なSecrets:
  ANTHROPIC_API_KEY  （必須）
  GMAIL_USER / GMAIL_APP_PASSWORD
  GSC_SITE_URL / GSC_SERVICE_ACCOUNT_JSON  （任意・設定時のみSC使用）
"""

from __future__ import annotations
import json, os, smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent.parent / "data"

GENRES = ["business", "gadget", "investment", "travel", "gourmet"]


def fetch_search_console_data(site_url: str) -> dict | None:
    """Search Console データを取得。失敗時はNoneを返す。"""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_json = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            return None

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
            "dimensions": ["query"], "rowLimit": 50,
            "orderBy": [{"fieldName": "clicks", "sortOrder": "DESCENDING"}],
        }).execute()
        queries = [{"query":r["keys"][0],"clicks":r.get("clicks",0),
                    "impressions":r.get("impressions",0),"ctr":round(r.get("ctr",0)*100,2),
                    "position":round(r.get("position",0),1)}
                   for r in q_resp.get("rows",[])]

        opportunity_keywords = sorted(
            [q for q in queries if 4 <= q["position"] <= 20 and q["impressions"] >= 50],
            key=lambda x: x["impressions"], reverse=True
        )

        return {
            "period": f"{start_date} 〜 {end_date}",
            "top_queries": queries[:20],
            "opportunity_keywords": opportunity_keywords[:10],
            "has_sc_data": True,
        }
    except Exception as e:
        print(f"Search Console取得失敗（スキップ）: {e}")
        return None


def generate_theme_suggestions(sc_data: dict | None) -> list:
    """Claude API でキーワード・テーマ提案を生成"""
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if sc_data and sc_data.get("has_sc_data"):
        context = f"""Search Consoleデータ（{sc_data['period']}）:
流入TOP10: {json.dumps(sc_data['top_queries'][:10], ensure_ascii=False)}
SEO機会KW: {json.dumps(sc_data['opportunity_keywords'][:5], ensure_ascii=False)}"""
    else:
        now = datetime.now(JST)
        context = f"""現在日時: {now.strftime('%Y年%m月%d日')}
Search Consoleデータなし。最新トレンドと季節性を考慮してください。"""

    prompt = f"""あなたはSEOとコンテンツ戦略の専門家です。
NEXIGENブログ（日本語・アフィリエイトブログ）の次回記事テーマを提案してください。

{context}

【ブログジャンル】
- business（副業・ビジネス）
- gadget（ガジェット・テック）
- investment（投資・資産運用）
- travel（旅行・国内旅行）
- gourmet（グルメ・食）

各ジャンル2テーマずつ、以下のJSON形式のみで返してください（前置き・コードブロック不要）:

[
  {{
    "genre": "business",
    "themes": [
      {{
        "title": "記事タイトル案",
        "target_keyword": "狙うキーワード",
        "reason": "提案理由（50字以内）",
        "priority": "high"
      }}
    ]
  }}
]"""

    resp = client.messages.create(
        model="claude-opus-4-5", max_tokens=2000,
        messages=[{"role":"user","content":prompt}]
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"): raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"): raw = "\n".join(raw.split("\n")[:-1])
    return json.loads(raw.strip())


def send_keyword_report(sc_data: dict | None, suggestions: list) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw   = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail未設定のためスキップ")
        return

    now_str = datetime.now(JST).strftime("%Y/%m/%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【NEXIGEN】キーワード分析＆テーマ提案 {now_str}"
    msg["From"] = gmail_user
    msg["To"]   = gmail_user

    sc_section = ""
    if sc_data and sc_data.get("has_sc_data"):
        sc_section = "<h2>🔍 Search Console 流入TOP10</h2><ul>"
        for q in sc_data["top_queries"][:10]:
            sc_section += f"<li>{q['query']}: {q['clicks']}クリック / {q['impressions']:,}表示 / {q['position']}位</li>"
        sc_section += "</ul>"
    else:
        sc_section = "<p>ℹ️ Search Consoleデータなし（トレンドベース提案）</p>"

    theme_section = ""
    for g in suggestions:
        theme_section += f"<h3>{g['genre']}</h3><ul>"
        for t in g.get("themes", []):
            theme_section += f"<li><strong>{t['title']}</strong><br>KW: {t['target_keyword']} / {t['reason']}</li>"
        theme_section += "</ul>"

    body = f"""<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;">
<h1 style="background:#1a1a2e;color:#fff;padding:20px;">NEXIGEN キーワードレポート</h1>
{sc_section}
<h2>✍️ AI提案：次回記事テーマ</h2>
{theme_section}
<p style="color:#888;font-size:12px;">{datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')} 自動生成</p>
</body></html>"""

    msg.attach(MIMEText(body, "html", "utf-8"))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())
    print("キーワードレポートメール送信完了")


def save_suggestions(suggestions: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "keyword_suggestions.json"
    out.write_text(json.dumps({
        "generated_at": datetime.now(JST).isoformat(),
        "suggestions": suggestions,
    }, ensure_ascii=False, indent=2))
    print(f"キーワード提案を保存: {out}")


if __name__ == "__main__":
    site_url = os.environ.get("GSC_SITE_URL", "")

    # Search Console（任意）
    sc_data = None
    if site_url:
        print("Search Consoleデータ取得中...")
        sc_data = fetch_search_console_data(site_url)
    else:
        print("GSC_SITE_URL未設定 → Claudeによるトレンド提案モードで実行")

    # Claude でテーマ提案
    print("Claudeでテーマ提案中...")
    suggestions = generate_theme_suggestions(sc_data)
    print(f"テーマ提案: {len(suggestions)} ジャンル")

    save_suggestions(suggestions)
    send_keyword_report(sc_data, suggestions)

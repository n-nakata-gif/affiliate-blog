"""
週次収益レポート（端的版）
毎週月曜 10:00 JST 実行。1画面で読めるテキストメールを送信。

【AdSense 連携設定】
  1. AdSense管理画面 → ユーザー管理 → サービスアカウントのメールを追加（閲覧者）
  2. GitHub Secrets: ADSENSE_PUBLISHER_ID = pub-XXXXXXXXXXXXXXXX
  ※ GA4_SERVICE_ACCOUNT_JSON を共用

必要なSecrets: GMAIL_USER / GMAIL_APP_PASSWORD
任意のSecrets: GA4_SERVICE_ACCOUNT_JSON / ADSENSE_PUBLISHER_ID
"""
from __future__ import annotations
import json, os, smtplib
from datetime import datetime, timedelta, timezone, date
from email.mime.text import MIMEText
from pathlib import Path

JST      = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"
REVENUE_LOG = Path("data/revenue_log.json")

# 手動ログのASPキー → 表示名
ASP_LABELS = {
    "adsense": "AdSense",
    "amazon": "Amazon",
    "rakuten": "楽天",
    "a8": "A8.net",
    "moshimo": "もしも",
    "valuecommerce": "バリューコマース",
    "accesstrade": "アクセストレード",
}


def load_revenue_log() -> list[dict]:
    """手動収益ログを古い順で返す。"""
    if not REVENUE_LOG.exists():
        return []
    try:
        data = json.loads(REVENUE_LOG.read_text(encoding="utf-8"))
        return data.get("weeks", [])
    except Exception as e:
        print(f"revenue_log 読み込み失敗: {e}")
        return []


def week_total(entry: dict) -> int:
    """1週ぶんの合計報酬（円）。"""
    return sum(int(entry.get(k, 0) or 0) for k in ASP_LABELS)


def build_revenue_trend(weeks: list[dict], n: int = 6) -> str:
    """直近n週の収益トレンドをテキストで返す。"""
    if not weeks:
        return ""
    recent = weeks[-n:]
    lines = [f"■ 収益トレンド（手動記録・直近{len(recent)}週）"]
    prev = None
    for e in recent:
        total = week_total(e)
        if prev is None:
            arrow = "  "
        elif total > prev:
            arrow = "↑"
        elif total < prev:
            arrow = "↓"
        else:
            arrow = "→"
        lines.append(f"  {e.get('week','?')}  ¥{total:,}  {arrow}")
        prev = total

    # 最新週の内訳
    latest = recent[-1]
    breakdown = [f"{ASP_LABELS[k]} ¥{int(latest.get(k,0) or 0):,}"
                 for k in ASP_LABELS if int(latest.get(k, 0) or 0) > 0]
    if breakdown:
        lines.append("  └ 最新週内訳: " + " / ".join(breakdown))
    else:
        lines.append("  └ 最新週はまだ全ASP 0円（または未記録）")
    lines.append("")
    return "\n".join(lines)


DASHBOARD_LINKS = [
    ("AdSense",        "https://adsense.google.com/adsense/"),
    ("A8.net",         "https://www.a8.net/"),
    ("ValueCommerce",  "https://member.valuecommerce.com/"),
    ("Amazon",         "https://affiliate.amazon.co.jp/"),
    ("楽天アフィリエイト",  "https://affiliate.rakuten.co.jp/"),
]


def fetch_adsense(publisher_id: str) -> dict | None:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        sa = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "")
        if not sa: return None
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa),
            scopes=["https://www.googleapis.com/auth/adsense.readonly"])
        svc = build("adsense", "v2", credentials=creds, cache_discovery=False)
        today = datetime.now(JST).date()
        mon   = today - timedelta(days=today.weekday() + 7)
        sun   = mon + timedelta(days=6)
        rep   = svc.accounts().reports().generate(
            account=f"accounts/{publisher_id}",
            dateRange="CUSTOM",
            startDate_year=mon.year, startDate_month=mon.month, startDate_day=mon.day,
            endDate_year=sun.year,   endDate_month=sun.month,   endDate_day=sun.day,
            metrics=["ESTIMATED_EARNINGS","PAGE_VIEWS","CLICKS","PAGE_RPM"],
        ).execute()
        cells = rep.get("totals", {}).get("cells", [])
        def v(i):
            try: return float(cells[i].get("value", 0))
            except: return 0.0
        return {"earnings": round(v(0), 0), "pv": int(v(1)),
                "clicks": int(v(2)), "rpm": round(v(3), 2),
                "period": f"{mon} 〜 {sun}"}
    except Exception as e:
        print(f"AdSense取得失敗: {e}"); return None


def count_articles_this_week() -> dict:
    today = datetime.now(JST).date()
    monday = today - timedelta(days=today.weekday())
    genre_cnt: dict[str, int] = {}
    for path in BLOG_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"): continue
        end = content.find("\n---", 3)
        if end == -1: continue
        meta: dict = {}
        for line in content[3:end].strip().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"').strip("'")
        try:
            pub = date.fromisoformat(meta.get("pubDate", ""))
        except ValueError:
            continue
        if pub >= monday:
            g = next((g for g in ["business","gadget","investment","travel","gourmet"]
                      if g in path.stem), "other")
            genre_cnt[g] = genre_cnt.get(g, 0) + 1
    return genre_cnt


def build_text(adsense: dict | None, genre_cnt: dict, date_str: str,
               revenue_weeks: list[dict] | None = None) -> str:
    lines = [f"Novlify 収益レポート {date_str}", ""]

    # 手動収益トレンド（最優先で表示）
    trend = build_revenue_trend(revenue_weeks or [])
    if trend:
        lines.append(trend)

    # AdSense
    if adsense:
        lines += [
            f"■ AdSense（{adsense['period']}）",
            f"  推定収益  ¥{adsense['earnings']:,.0f}",
            f"  RPM       ¥{adsense['rpm']:.2f}",
            f"  PV {adsense['pv']:,}  クリック {adsense['clicks']}",
            "",
        ]
    else:
        lines += ["■ AdSense  未連携（ADSENSE_PUBLISHER_ID を Secrets に追加で自動集計）", ""]

    # 今週の投稿
    total = sum(genre_cnt.values())
    label = {"business":"ビジネス","gadget":"ガジェット","investment":"投資",
             "travel":"旅行","gourmet":"グルメ","other":"その他"}
    detail = "  " + "  ".join(f"{label.get(g,g)} {c}本" for g, c in genre_cnt.items())
    lines += [f"■ 今週の投稿  {total}本", detail if genre_cnt else "  （なし）", ""]

    # ダッシュボードリンク
    lines.append("■ 各プラットフォーム確認")
    for name, url in DASHBOARD_LINKS:
        lines.append(f"  {name}: {url}")

    return "\n".join(lines)


def send_email(text: str, date_str: str, adsense: dict | None) -> None:
    u = os.environ.get("GMAIL_USER")
    p = os.environ.get("GMAIL_APP_PASSWORD")
    if not u or not p:
        print("Gmail未設定スキップ"); return
    # 件名: 手動ログ最新週 + AdSense を合算
    manual_latest = week_total(load_revenue_log()[-1]) if load_revenue_log() else 0
    adsense_earn = int(adsense["earnings"]) if adsense else 0
    grand = manual_latest + adsense_earn
    earn = f"¥{grand:,}" if grand > 0 else "¥0（計測中）"
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = f"【Novlify】収益 {earn} | {date_str}"
    msg["From"] = msg["To"] = u
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.login(u, p)
        s.sendmail(u, u, msg.as_bytes())
    print("収益レポートメール送信完了")


if __name__ == "__main__":
    now      = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d")
    pub_id   = os.environ.get("ADSENSE_PUBLISHER_ID", "")
    adsense  = fetch_adsense(pub_id) if pub_id else None
    if not pub_id: print("ADSENSE_PUBLISHER_ID 未設定")
    genre_cnt = count_articles_this_week()
    revenue_weeks = load_revenue_log()
    text = build_text(adsense, genre_cnt, date_str, revenue_weeks)
    print(text)
    if os.environ.get("WEEKLY_BATCH") == "1":
        from pathlib import Path
        report_dir = Path("data/weekly_reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "revenue.txt").write_text(text, encoding="utf-8")
        print("収益レポートを保存（週次まとめ送信）")
    else:
        send_email(text, date_str, adsense)

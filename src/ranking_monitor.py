"""
検索順位監視 & リライトトリガー検出スクリプト

機能:
  ② 検索順位の自動監視 — 記事ごとの順位を週次トラッキング、急落・圏外を通知
  ③ リライトトリガー検出 — CTR高×順位低の記事を自動ピックアップして通知

必要なSecrets:
  GSC_SITE_URL           （例: sc-domain:novlify.jp）
  GSC_OAUTH_CREDENTIALS  （refresh tokenを含むJSON）
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
HISTORY_FILE = DATA_DIR / "ranking_history.json"
BLOG_URL = "https://novlify.jp"

# 閾値設定
DROP_ALERT_THRESHOLD = 5        # 順位が何位以上下がったら警告するか
OUT_OF_RANK_POSITION = 30       # この順位より低い = 「圏外に近い」と判定
REWRITE_CTR_MIN = 0.03          # CTRがこれ以上（3%）
REWRITE_POSITION_MIN = 8        # かつ順位がこれより低い（8位以下）
REWRITE_IMPRESSIONS_MIN = 30    # かつ表示回数がこれ以上


def get_gsc_service():
    """GSC OAuth2認証でサービスオブジェクトを返す"""
    import google.oauth2.credentials
    import google.auth.transport.requests
    from googleapiclient.discovery import build

    oauth_json = os.environ.get("GSC_OAUTH_CREDENTIALS", "")
    if not oauth_json:
        raise RuntimeError("GSC_OAUTH_CREDENTIALS が未設定です")

    info = json.loads(oauth_json)
    creds = google.oauth2.credentials.Credentials(
        token=info.get("token"),
        refresh_token=info["refresh_token"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=info.get("scopes"),
    )
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())

    return build("searchconsole", "v1", credentials=creds)


def fetch_page_rankings(service, site_url: str) -> list[dict]:
    """記事URLごとの順位・CTR・クリック数・表示回数を取得"""
    today = datetime.now(JST).date()
    end_date = today - timedelta(days=3)
    start_date = end_date - timedelta(days=27)

    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": str(start_date),
                "endDate": str(end_date),
                "dimensions": ["page"],
                "rowLimit": 100,
                "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}],
            }
        ).execute()

        rows = []
        for r in resp.get("rows", []):
            url = r["keys"][0]
            # /blog/ 配下の記事のみ対象
            if "/blog/" not in url:
                continue
            rows.append({
                "url": url,
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr": round(r.get("ctr", 0) * 100, 2),   # パーセント表示
                "position": round(r.get("position", 0), 1),
            })
        return rows
    except Exception as e:
        print(f"GSCページ別データ取得失敗: {e}")
        return []


def fetch_top_queries_per_page(service, site_url: str) -> dict[str, list]:
    """URLごとの上位クエリを取得（リライト分析用）"""
    today = datetime.now(JST).date()
    end_date = today - timedelta(days=3)
    start_date = end_date - timedelta(days=27)

    try:
        resp = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": str(start_date),
                "endDate": str(end_date),
                "dimensions": ["page", "query"],
                "rowLimit": 200,
                "orderBy": [{"fieldName": "impressions", "sortOrder": "DESCENDING"}],
            }
        ).execute()

        result: dict[str, list] = {}
        for r in resp.get("rows", []):
            url, query = r["keys"][0], r["keys"][1]
            if "/blog/" not in url:
                continue
            result.setdefault(url, []).append({
                "query": query,
                "clicks": int(r.get("clicks", 0)),
                "impressions": int(r.get("impressions", 0)),
                "ctr": round(r.get("ctr", 0) * 100, 2),
                "position": round(r.get("position", 0), 1),
            })
        return result
    except Exception as e:
        print(f"GSCクエリ別データ取得失敗: {e}")
        return {}


def load_history() -> dict:
    """過去の順位履歴を読み込む"""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_history(history: dict) -> None:
    """順位履歴を保存する"""
    DATA_DIR.mkdir(exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"順位履歴を保存しました: {HISTORY_FILE}")


def detect_ranking_changes(
    current: list[dict],
    last_week: dict[str, dict],
) -> dict:
    """今週と先週の順位を比較して変動を検出する"""
    improved, dropped, new_entries, out_of_rank = [], [], [], []

    for row in current:
        url = row["url"]
        pos = row["position"]

        if pos >= OUT_OF_RANK_POSITION:
            out_of_rank.append(row)

        if url not in last_week:
            new_entries.append(row)
            continue

        prev_pos = last_week[url]["position"]
        diff = pos - prev_pos  # 正 = 順位下降（悪化）、負 = 順位上昇（改善）

        if diff >= DROP_ALERT_THRESHOLD:
            dropped.append({**row, "prev_position": prev_pos, "diff": diff})
        elif diff <= -DROP_ALERT_THRESHOLD:
            improved.append({**row, "prev_position": prev_pos, "diff": diff})

    return {
        "improved": sorted(improved, key=lambda x: x["diff"]),
        "dropped": sorted(dropped, key=lambda x: -x["diff"]),
        "new_entries": new_entries,
        "out_of_rank": out_of_rank,
    }


def detect_rewrite_triggers(
    current: list[dict],
    queries_per_page: dict[str, list],
) -> list[dict]:
    """
    リライト候補を検出する:
    - CTR高 × 順位低 → タイトル/コンテンツのミスマッチ
    - 表示回数多 × CTR低 → メタディスクリプション改善の余地
    - 順位10〜20位 × 表示回数多 → もう少しで上位表示できる
    """
    triggers = []

    for row in current:
        url = row["url"]
        pos = row["position"]
        ctr = row["ctr"]
        impressions = row["impressions"]
        clicks = row["clicks"]
        queries = queries_per_page.get(url, [])

        reasons = []
        priority = "low"

        # ① CTR高 × 順位低（タイトルは良いのに内容が弱い）
        if ctr >= REWRITE_CTR_MIN * 100 and pos >= REWRITE_POSITION_MIN and impressions >= REWRITE_IMPRESSIONS_MIN:
            reasons.append(f"CTR {ctr}%（良好）なのに順位 {pos}位 → 内容強化でTop5を狙える")
            priority = "high"

        # ② 表示回数多 × CTR低 × 10〜30位（タイトル・メタ改善で伸びる）
        elif impressions >= 100 and ctr < 2.0 and 10 <= pos <= 30:
            reasons.append(f"表示{impressions}回あるがCTR {ctr}%と低い → タイトル・メタ改善余地あり")
            priority = "medium"

        # ③ 圏外直前（11〜20位）× そこそこ表示（強化でTop10入り可能）
        elif 11 <= pos <= 20 and impressions >= 50:
            reasons.append(f"現在{pos}位 → あと少しでTop10。内容充実でページ1入りを狙える")
            priority = "medium"

        if reasons:
            # 上位クエリを2件まで取得
            top_queries = sorted(queries, key=lambda q: -q["impressions"])[:2]
            triggers.append({
                "url": url,
                "position": pos,
                "ctr": ctr,
                "impressions": impressions,
                "clicks": clicks,
                "reasons": reasons,
                "priority": priority,
                "top_queries": top_queries,
            })

    # 優先度順（high → medium → low）にソート
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(triggers, key=lambda x: (priority_order[x["priority"]], -x["impressions"]))


def shorten_url(url: str) -> str:
    """URLをスラグ部分だけに短縮して表示"""
    return url.replace(BLOG_URL, "").rstrip("/") or url


def build_report_html(
    date_str: str,
    current: list[dict],
    changes: dict,
    rewrite_triggers: list[dict],
) -> str:
    """メールHTML本文を生成"""

    # ── ランキング変動セクション ──
    drop_rows = ""
    for r in changes["dropped"][:10]:
        drop_rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #fee2e2;'>"
            f"<a href='{r['url']}' style='color:#dc2626;'>{shorten_url(r['url'])}</a></td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #fee2e2;text-align:center;'>"
            f"{r['prev_position']}位 → <strong style='color:#dc2626;'>{r['position']}位</strong> "
            f"(▼{r['diff']})</td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #fee2e2;text-align:center;'>"
            f"{r['impressions']:,}回 / CTR {r['ctr']}%</td>"
            f"</tr>"
        )
    drop_section = f"""
    <h2 style="color:#dc2626;margin-top:28px;">📉 順位急落アラート（{len(changes['dropped'])}件）</h2>
    {"<p style='color:#888;'>今週の急落はありませんでした。</p>" if not changes['dropped'] else f"""
    <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
      <thead>
        <tr style="background:#fee2e2;">
          <th style="padding:8px 10px;text-align:left;">記事URL</th>
          <th style="padding:8px 10px;text-align:center;">順位変動</th>
          <th style="padding:8px 10px;text-align:center;">表示/CTR</th>
        </tr>
      </thead>
      <tbody>{drop_rows}</tbody>
    </table>"""}
    """ if changes["dropped"] else f"""
    <h2 style="color:#dc2626;margin-top:28px;">📉 順位急落アラート</h2>
    <p style="color:#888;">今週の急落はありませんでした ✅</p>
    """

    improve_rows = ""
    for r in changes["improved"][:5]:
        improve_rows += (
            f"<tr>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d1fae5;'>"
            f"<a href='{r['url']}' style='color:#059669;'>{shorten_url(r['url'])}</a></td>"
            f"<td style='padding:6px 10px;border-bottom:1px solid #d1fae5;text-align:center;'>"
            f"{r['prev_position']}位 → <strong style='color:#059669;'>{r['position']}位</strong> "
            f"(▲{abs(r['diff'])})</td>"
            f"</tr>"
        )

    # ── リライトトリガーセクション ──
    trigger_rows = ""
    for t in rewrite_triggers[:10]:
        priority_badge = {
            "high":   "<span style='background:#dc2626;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.78rem;'>🔴 高優先</span>",
            "medium": "<span style='background:#f59e0b;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.78rem;'>🟡 中優先</span>",
            "low":    "<span style='background:#6b7280;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.78rem;'>⚪ 低優先</span>",
        }.get(t["priority"], "")

        queries_str = "、".join([f"\"{q['query']}\"({q['impressions']}回)" for q in t["top_queries"]]) or "データなし"

        trigger_rows += (
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top;'>"
            f"{priority_badge}<br>"
            f"<a href='{t['url']}' style='color:#374151;font-size:0.82rem;'>{shorten_url(t['url'])}</a></td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:center;vertical-align:top;'>"
            f"{t['position']}位 / CTR {t['ctr']}%<br>"
            f"<span style='font-size:0.8rem;color:#888;'>{t['impressions']:,}表示</span></td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;font-size:0.82rem;vertical-align:top;'>"
            f"{''.join(f'• {r}<br>' for r in t['reasons'])}"
            f"<span style='color:#6b7280;'>流入KW: {queries_str}</span></td>"
            f"</tr>"
        )

    high_count = sum(1 for t in rewrite_triggers if t["priority"] == "high")
    med_count  = sum(1 for t in rewrite_triggers if t["priority"] == "medium")

    return f"""<html>
<body style="font-family:'Noto Sans JP',sans-serif;max-width:700px;margin:0 auto;color:#333;">

<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:28px 32px;border-radius:12px 12px 0 0;">
  <h1 style="margin:0;font-size:1.4rem;">📊 Novlify 週次検索順位レポート</h1>
  <p style="margin:6px 0 0;color:#a5b4fc;font-size:0.9rem;">{date_str}　全{len(current)}記事を分析</p>
</div>

<div style="padding:24px 32px;background:#f8fafc;border:1px solid #e2e8f0;border-top:none;">

  <!-- サマリー -->
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:28px;">
    <div style="background:#fff;border-radius:8px;padding:14px;text-align:center;border:1px solid #e5e7eb;">
      <div style="font-size:1.6rem;font-weight:900;color:#1e40af;">{len(current)}</div>
      <div style="font-size:0.78rem;color:#64748b;">計測記事数</div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:14px;text-align:center;border:1px solid #e5e7eb;">
      <div style="font-size:1.6rem;font-weight:900;color:#dc2626;">{len(changes['dropped'])}</div>
      <div style="font-size:0.78rem;color:#64748b;">順位急落</div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:14px;text-align:center;border:1px solid #e5e7eb;">
      <div style="font-size:1.6rem;font-weight:900;color:#059669;">{len(changes['improved'])}</div>
      <div style="font-size:0.78rem;color:#64748b;">順位改善</div>
    </div>
    <div style="background:#fff;border-radius:8px;padding:14px;text-align:center;border:1px solid #e5e7eb;">
      <div style="font-size:1.6rem;font-weight:900;color:#d97706;">{high_count + med_count}</div>
      <div style="font-size:0.78rem;color:#64748b;">リライト候補</div>
    </div>
  </div>

  <!-- 順位急落 -->
  {drop_section}

  <!-- 順位改善 -->
  <h2 style="color:#059669;margin-top:28px;">📈 順位改善（{len(changes['improved'])}件）</h2>
  {"<p style='color:#888;'>今週の改善はありませんでした。</p>" if not changes['improved'] else f"""
  <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
    <thead>
      <tr style="background:#d1fae5;">
        <th style="padding:8px 10px;text-align:left;">記事URL</th>
        <th style="padding:8px 10px;text-align:center;">順位変動</th>
      </tr>
    </thead>
    <tbody>{improve_rows}</tbody>
  </table>"""}

  <!-- リライトトリガー -->
  <h2 style="color:#d97706;margin-top:28px;">✍️ リライト候補（🔴高優先 {high_count}件 / 🟡中優先 {med_count}件）</h2>
  <p style="font-size:0.85rem;color:#64748b;margin-top:-8px;">
    CTR高×順位低、または表示多×クリック少の記事です。リライトで収益UPを狙えます。
  </p>
  {"<p style='color:#888;'>今週のリライト候補はありませんでした。</p>" if not rewrite_triggers else f"""
  <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
    <thead>
      <tr style="background:#fef3c7;">
        <th style="padding:8px 10px;text-align:left;">記事</th>
        <th style="padding:8px 10px;text-align:center;">指標</th>
        <th style="padding:8px 10px;text-align:left;">改善ポイント</th>
      </tr>
    </thead>
    <tbody>{trigger_rows}</tbody>
  </table>"""}

  <!-- 全記事一覧TOP20 -->
  <h2 style="margin-top:28px;">🏆 全記事 順位一覧（表示回数順 TOP 20）</h2>
  <table style="width:100%;border-collapse:collapse;font-size:0.82rem;">
    <thead>
      <tr style="background:#e5e7eb;">
        <th style="padding:6px 10px;text-align:left;">記事</th>
        <th style="padding:6px 10px;text-align:center;">順位</th>
        <th style="padding:6px 10px;text-align:center;">表示</th>
        <th style="padding:6px 10px;text-align:center;">CTR</th>
        <th style="padding:6px 10px;text-align:center;">クリック</th>
      </tr>
    </thead>
    <tbody>
      {"".join(
        f"<tr>"
        f"<td style='padding:5px 10px;border-bottom:1px solid #f3f4f6;'>"
        f"<a href='{r['url']}' style='color:#374151;'>{shorten_url(r['url'])}</a></td>"
        f"<td style='padding:5px 10px;border-bottom:1px solid #f3f4f6;text-align:center;"
        f"color:{'#059669' if r['position'] <= 10 else '#d97706' if r['position'] <= 20 else '#dc2626'};font-weight:bold;'>"
        f"{r['position']}位</td>"
        f"<td style='padding:5px 10px;border-bottom:1px solid #f3f4f6;text-align:center;'>{r['impressions']:,}</td>"
        f"<td style='padding:5px 10px;border-bottom:1px solid #f3f4f6;text-align:center;'>{r['ctr']}%</td>"
        f"<td style='padding:5px 10px;border-bottom:1px solid #f3f4f6;text-align:center;'>{r['clicks']}</td>"
        f"</tr>"
        for r in sorted(current, key=lambda x: -x['impressions'])[:20]
      )}
    </tbody>
  </table>

</div>

<div style="background:#1a1a2e;color:#64748b;padding:16px 32px;border-radius:0 0 12px 12px;font-size:0.78rem;text-align:center;">
  <p style="margin:0;">Novlify 週次順位レポート | {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')} 自動生成</p>
</div>

</body>
</html>"""


def send_report_email(html: str, date_str: str) -> None:
    """レポートをメールで送信する"""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw   = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail未設定のためメール送信スキップ")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"【Novlify】週次検索順位レポート {date_str}"
    msg["From"]    = gmail_user
    msg["To"]      = gmail_user
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())

    print("レポートメール送信完了")


def main():
    site_url = os.environ.get("GSC_SITE_URL", "")
    if not site_url:
        print("ERROR: GSC_SITE_URL が未設定です", flush=True)
        return

    oauth_creds = os.environ.get("GSC_OAUTH_CREDENTIALS", "")
    if not oauth_creds:
        print("ERROR: GSC_OAUTH_CREDENTIALS が未設定です", flush=True)
        return

    now_jst  = datetime.now(JST)
    date_str = now_jst.strftime("%Y/%m/%d")
    week_key = now_jst.strftime("%Y-W%W")

    print("GSCサービス接続中...")
    service = get_gsc_service()

    print("記事ごとの順位データを取得中...")
    current = fetch_page_rankings(service, site_url)
    print(f"  → {len(current)}記事のデータ取得完了")

    print("クエリ別データを取得中...")
    queries_per_page = fetch_top_queries_per_page(service, site_url)

    # 履歴の読み込みと比較
    history = load_history()
    last_week_key = (now_jst - timedelta(weeks=1)).strftime("%Y-W%W")
    last_week_data: dict[str, dict] = history.get(last_week_key, {})

    print(f"先週（{last_week_key}）のデータ: {len(last_week_data)}記事")

    # 順位変動検出
    current_map = {r["url"]: r for r in current}
    changes = detect_ranking_changes(current, last_week_data)
    print(f"急落: {len(changes['dropped'])}件、改善: {len(changes['improved'])}件、圏外: {len(changes['out_of_rank'])}件")

    # リライトトリガー検出
    rewrite_triggers = detect_rewrite_triggers(current, queries_per_page)
    print(f"リライト候補: {len(rewrite_triggers)}件（高優先: {sum(1 for t in rewrite_triggers if t['priority'] == 'high')}件）")

    # 履歴に今週データを保存
    history[week_key] = current_map
    # 古い履歴を12週分まで保持（それ以前は削除）
    all_weeks = sorted(history.keys())
    if len(all_weeks) > 12:
        for old_key in all_weeks[:-12]:
            del history[old_key]
    save_history(history)

    # メールレポート送信
    html = build_report_html(date_str, current, changes, rewrite_triggers)
    send_report_email(html, date_str)

    # コンソールサマリー出力
    print("\n=== リライト高優先候補 ===")
    for t in rewrite_triggers:
        if t["priority"] == "high":
            print(f"  {t['url']} → {t['position']}位 / CTR {t['ctr']}%")

    print("\n=== 順位急落 ===")
    for r in changes["dropped"][:5]:
        print(f"  {r['url']} → {r['prev_position']}位→{r['position']}位 (▼{r['diff']})")


if __name__ == "__main__":
    main()

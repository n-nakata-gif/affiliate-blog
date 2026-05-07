"""
記事品質チェックスクリプト
毎週木曜 10:00 JST に自動実行。3項目をチェックしてメールレポートを送信する。

チェック項目:
  1. 本文文字数   （2,000字未満は要注意）
  2. タイトル文字数（32字未満 or 60字超は要注意）
  3. 重複タイトル  （同一タイトルが複数記事に存在）

来週追加予定:
  - リンク切れチェック
  - アフィリエイトセクション有無
  - 画像（heroImage）有無
  - h2見出し数（3本未満は要注意）
  - description 長さ（70〜160字を推奨）
  - 記事の鮮度（pubDate が 1 年以上前）

必要なSecrets:
  GMAIL_USER / GMAIL_APP_PASSWORD
"""

from __future__ import annotations

import os
import re
import smtplib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

JST = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"

# ---- 基準値 ----
MIN_BODY_CHARS = 2000
MIN_TITLE_CHARS = 32
MAX_TITLE_CHARS = 60


# ---------------------------------------------------------------------------
# Frontmatter パーサー
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Markdown の YAML frontmatter を解析して (meta, body) を返す。"""
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_block = content[3:end].strip()
    body = content[end + 4:].strip()

    meta: dict = {}
    for line in yaml_block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")

    return meta, body


# ---------------------------------------------------------------------------
# 本文文字数カウント（HTML タグ・Markdown 記法を除去）
# ---------------------------------------------------------------------------

def count_body_chars(body: str) -> int:
    """本文から HTML タグと主要 Markdown 記法を除いた文字数を返す。"""
    # HTML タグを除去
    text = re.sub(r"<[^>]+>", "", body)
    # Markdown 見出し / 水平線 / 強調などを除去
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", text)
    # Markdown リンク・画像 → テキスト部分だけ残す
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)
    # コードブロック除去
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # 空白・改行を圧縮して純粋な文字数を計算
    text = re.sub(r"\s+", "", text)
    return len(text)


# ---------------------------------------------------------------------------
# 全記事チェック
# ---------------------------------------------------------------------------

def check_articles() -> dict:
    """BLOG_DIR 内の全 .md ファイルを走査し、品質問題をまとめて返す。"""
    files = sorted(BLOG_DIR.glob("*.md"))

    short_articles: list[dict] = []       # 文字数不足
    bad_title_length: list[dict] = []     # タイトル文字数異常
    title_map: dict[str, list[str]] = defaultdict(list)  # タイトル重複チェック用

    for path in files:
        content = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        filename = path.name
        title = meta.get("title", "（タイトル未設定）")
        pub_date = meta.get("pubDate", "")

        # 1. 本文文字数チェック
        char_count = count_body_chars(body)
        if char_count < MIN_BODY_CHARS:
            short_articles.append({
                "file": filename,
                "title": title,
                "chars": char_count,
                "pubDate": pub_date,
            })

        # 2. タイトル文字数チェック
        title_len = len(title)
        if title_len < MIN_TITLE_CHARS or title_len > MAX_TITLE_CHARS:
            bad_title_length.append({
                "file": filename,
                "title": title,
                "length": title_len,
                "pubDate": pub_date,
                "issue": "短すぎ" if title_len < MIN_TITLE_CHARS else "長すぎ",
            })

        # 3. 重複タイトル収集
        title_map[title].append(filename)

    # タイトル重複を抽出
    duplicate_titles: list[dict] = []
    for title, fnames in title_map.items():
        if len(fnames) >= 2:
            duplicate_titles.append({
                "title": title,
                "files": fnames,
                "count": len(fnames),
            })

    return {
        "total_files": len(files),
        "short_articles": short_articles,
        "bad_title_length": bad_title_length,
        "duplicate_titles": duplicate_titles,
    }


# ---------------------------------------------------------------------------
# HTML レポート生成
# ---------------------------------------------------------------------------

def _row_style(i: int) -> str:
    return "background:#f9f9f9;" if i % 2 == 0 else "background:#ffffff;"


def _issue_badge(count: int) -> str:
    if count == 0:
        return "<span style='background:#22c55e;color:#fff;padding:2px 10px;border-radius:12px;font-size:13px;'>✅ 問題なし</span>"
    return "<span style='background:#ef4444;color:#fff;padding:2px 10px;border-radius:12px;font-size:13px;'>⚠ " + str(count) + "件</span>"


def build_report_html(results: dict, date_str: str) -> str:
    total = results["total_files"]
    short = results["short_articles"]
    bad_title = results["bad_title_length"]
    dup = results["duplicate_titles"]
    total_issues = len(short) + len(bad_title) + len(dup)

    # ---- サマリーカード ----
    summary = (
        "<div style='display:flex;gap:12px;flex-wrap:wrap;margin:16px 0;'>"
        + "<div style='flex:1;min-width:140px;background:#1a1a2e;color:#fff;border-radius:10px;padding:16px;text-align:center;'>"
        + "<div style='font-size:28px;font-weight:bold;'>" + str(total) + "</div>"
        + "<div style='font-size:12px;margin-top:4px;'>総記事数</div></div>"
        + "<div style='flex:1;min-width:140px;background:" + ("#ef4444" if total_issues else "#22c55e") + ";color:#fff;border-radius:10px;padding:16px;text-align:center;'>"
        + "<div style='font-size:28px;font-weight:bold;'>" + str(total_issues) + "</div>"
        + "<div style='font-size:12px;margin-top:4px;'>要対応件数</div></div>"
        + "<div style='flex:1;min-width:140px;background:#f59e0b;color:#fff;border-radius:10px;padding:16px;text-align:center;'>"
        + "<div style='font-size:28px;font-weight:bold;'>" + str(len(short)) + "</div>"
        + "<div style='font-size:12px;margin-top:4px;'>文字数不足</div></div>"
        + "<div style='flex:1;min-width:140px;background:#6366f1;color:#fff;border-radius:10px;padding:16px;text-align:center;'>"
        + "<div style='font-size:28px;font-weight:bold;'>" + str(len(bad_title)) + "</div>"
        + "<div style='font-size:12px;margin-top:4px;'>タイトル異常</div></div>"
        + "</div>"
    )

    # ---- 1. 文字数不足 ----
    sec1 = (
        "<h2 style='border-left:4px solid #f59e0b;padding-left:10px;'>① 本文文字数不足（2,000字未満）"
        + _issue_badge(len(short)) + "</h2>"
    )
    if short:
        sec1 += (
            "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
            "<tr style='background:#1a1a2e;color:#fff;'>"
            "<th style='padding:8px;text-align:left;'>ファイル名</th>"
            "<th style='padding:8px;text-align:left;'>タイトル</th>"
            "<th style='padding:8px;text-align:right;'>文字数</th>"
            "<th style='padding:8px;text-align:center;'>公開日</th>"
            "</tr>"
        )
        for i, art in enumerate(short):
            rs = _row_style(i)
            sec1 += (
                "<tr style='" + rs + "'>"
                "<td style='padding:8px;font-family:monospace;font-size:12px;'>" + art["file"] + "</td>"
                "<td style='padding:8px;'>" + art["title"] + "</td>"
                "<td style='padding:8px;text-align:right;color:#ef4444;font-weight:bold;'>" + str(art["chars"]) + "字</td>"
                "<td style='padding:8px;text-align:center;color:#888;'>" + art["pubDate"] + "</td>"
                "</tr>"
            )
        sec1 += "</table>"
    else:
        sec1 += "<p style='color:#22c55e;'>✅ 2,000字未満の記事はありません。</p>"

    # ---- 2. タイトル文字数異常 ----
    sec2 = (
        "<h2 style='border-left:4px solid #6366f1;padding-left:10px;'>② タイトル文字数異常（推奨：32〜60字）"
        + _issue_badge(len(bad_title)) + "</h2>"
    )
    if bad_title:
        sec2 += (
            "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
            "<tr style='background:#1a1a2e;color:#fff;'>"
            "<th style='padding:8px;text-align:left;'>ファイル名</th>"
            "<th style='padding:8px;text-align:left;'>タイトル</th>"
            "<th style='padding:8px;text-align:right;'>文字数</th>"
            "<th style='padding:8px;text-align:center;'>判定</th>"
            "</tr>"
        )
        for i, art in enumerate(bad_title):
            rs = _row_style(i)
            color = "#f59e0b" if art["issue"] == "短すぎ" else "#ef4444"
            sec2 += (
                "<tr style='" + rs + "'>"
                "<td style='padding:8px;font-family:monospace;font-size:12px;'>" + art["file"] + "</td>"
                "<td style='padding:8px;'>" + art["title"] + "</td>"
                "<td style='padding:8px;text-align:right;font-weight:bold;'>" + str(art["length"]) + "字</td>"
                "<td style='padding:8px;text-align:center;color:" + color + ";font-weight:bold;'>" + art["issue"] + "</td>"
                "</tr>"
            )
        sec2 += "</table>"
    else:
        sec2 += "<p style='color:#22c55e;'>✅ タイトル文字数に問題のある記事はありません。</p>"

    # ---- 3. 重複タイトル ----
    sec3 = (
        "<h2 style='border-left:4px solid #ec4899;padding-left:10px;'>③ 重複タイトル"
        + _issue_badge(len(dup)) + "</h2>"
    )
    if dup:
        sec3 += (
            "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
            "<tr style='background:#1a1a2e;color:#fff;'>"
            "<th style='padding:8px;text-align:left;'>タイトル</th>"
            "<th style='padding:8px;text-align:right;'>重複数</th>"
            "<th style='padding:8px;text-align:left;'>対象ファイル</th>"
            "</tr>"
        )
        for i, item in enumerate(dup):
            rs = _row_style(i)
            files_str = "<br>".join(item["files"])
            sec3 += (
                "<tr style='" + rs + "'>"
                "<td style='padding:8px;'>" + item["title"] + "</td>"
                "<td style='padding:8px;text-align:right;color:#ec4899;font-weight:bold;'>" + str(item["count"]) + "件</td>"
                "<td style='padding:8px;font-family:monospace;font-size:12px;'>" + files_str + "</td>"
                "</tr>"
            )
        sec3 += "</table>"
    else:
        sec3 += "<p style='color:#22c55e;'>✅ 重複タイトルはありません。</p>"

    # ---- 来週追加予定チェック項目 ----
    next_week = (
        "<div style='background:#f0f4ff;border:1px solid #c7d2fe;border-radius:8px;padding:16px;margin-top:24px;'>"
        "<h3 style='color:#4f46e5;margin-top:0;'>🗓 来週追加予定のチェック項目</h3>"
        "<ul style='color:#555;line-height:1.9;margin:0;'>"
        "<li>🔗 <strong>リンク切れチェック</strong>：記事内リンクの HTTP ステータスを確認</li>"
        "<li>💰 <strong>アフィリエイトセクション有無</strong>：収益化リンクが挿入済みか確認</li>"
        "<li>🖼 <strong>画像（heroImage）有無</strong>：アイキャッチ画像が設定されているか確認</li>"
        "<li>📑 <strong>h2 見出し数</strong>：構成として 3 本以上あるか確認</li>"
        "<li>📝 <strong>description 長さ</strong>：SEO 推奨の 70〜160 字に収まっているか確認</li>"
        "<li>📅 <strong>鮮度チェック</strong>：pubDate が 1 年以上前の記事を抽出・更新促進</li>"
        "</ul>"
        "</div>"
    )

    # ---- 全体組み立て ----
    status_text = "✅ 問題なし" if total_issues == 0 else "⚠ " + str(total_issues) + " 件の要対応あり"
    html = (
        "<html><body style='font-family:sans-serif;max-width:700px;margin:0 auto;color:#333;'>"
        "<div style='background:#1a1a2e;color:#fff;padding:24px;border-radius:10px 10px 0 0;'>"
        "<h1 style='margin:0;font-size:22px;'>📊 Novlify 記事品質チェックレポート</h1>"
        "<p style='margin:6px 0 0;color:#aaa;font-size:14px;'>" + date_str + " 自動生成</p>"
        "</div>"
        "<div style='background:#fff;padding:20px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;'>"
        + summary
        + "<p style='font-size:15px;'><strong>総合判定：</strong>" + status_text + "</p>"
        + "<hr style='border:none;border-top:1px solid #e5e7eb;margin:20px 0;'>"
        + sec1
        + "<hr style='border:none;border-top:1px solid #e5e7eb;margin:20px 0;'>"
        + sec2
        + "<hr style='border:none;border-top:1px solid #e5e7eb;margin:20px 0;'>"
        + sec3
        + next_week
        + "<p style='color:#aaa;font-size:12px;margin-top:24px;'>このメールは GitHub Actions により自動送信されました。</p>"
        + "</div></body></html>"
    )
    return html


# ---------------------------------------------------------------------------
# メール送信
# ---------------------------------------------------------------------------

def send_report_email(html: str, date_str: str, total_issues: int) -> None:
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pw:
        print("Gmail 未設定のためメール送信をスキップ")
        return

    status = "⚠ 要対応あり" if total_issues > 0 else "✅ 問題なし"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "【Novlify】記事品質チェック " + date_str + "（" + status + "）"
    msg["From"] = gmail_user
    msg["To"] = gmail_user

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_pw)
        smtp.sendmail(gmail_user, gmail_user, msg.as_bytes())

    print("品質チェックレポートを送信しました: " + gmail_user)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

def main() -> None:
    now = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d %H:%M JST")

    print("記事品質チェック開始...")
    results = check_articles()

    total = results["total_files"]
    total_issues = len(results["short_articles"]) + len(results["bad_title_length"]) + len(results["duplicate_titles"])

    print("総記事数: " + str(total))
    print("文字数不足: " + str(len(results["short_articles"])) + " 件")
    print("タイトル異常: " + str(len(results["bad_title_length"])) + " 件")
    print("重複タイトル: " + str(len(results["duplicate_titles"])) + " 件")
    print("要対応合計: " + str(total_issues) + " 件")

    html = build_report_html(results, date_str)
    send_report_email(html, now.strftime("%Y/%m/%d"), total_issues)
    print("完了")


if __name__ == "__main__":
    main()

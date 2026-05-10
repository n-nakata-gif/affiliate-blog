"""
記事品質チェック（端的版）
毎週木曜 10:00 JST 実行。問題記事のみ列挙して1画面で読めるメールを送信。
問題があれば data/quality_issues.json に書き出し、自動修正をトリガーする。
"""
from __future__ import annotations
import json, os, re, smtplib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

JST      = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"
DATA_DIR = Path(__file__).parent.parent / "data"
MIN_BODY  = 2000
MIN_TITLE = 32
MAX_TITLE = 60


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"): return {}, content
    end = content.find("\n---", 3)
    if end == -1: return {}, content
    meta: dict = {}
    for line in content[3:end].strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, content[end + 4:].strip()


def count_chars(body: str) -> int:
    t = re.sub(r"<[^>]+>", "", body)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", t)
    t = re.sub(r"!\[.*?\]\(.*?\)", "", t)
    t = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", t)
    t = re.sub(r"```[\s\S]*?```", "", t)
    return len(re.sub(r"\s+", "", t))


def check_articles() -> dict:
    files = sorted(BLOG_DIR.glob("*.md"))
    short, bad_title, title_map = [], [], defaultdict(list)
    for path in files:
        content = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)
        fn    = path.name
        title = meta.get("title", "（未設定）")
        pub   = meta.get("pubDate", "")
        chars = count_chars(body)
        tlen  = len(title)
        if chars < MIN_BODY:
            short.append({"file": fn, "title": title, "chars": chars, "pubDate": pub})
        if tlen < MIN_TITLE or tlen > MAX_TITLE:
            bad_title.append({"file": fn, "title": title, "length": tlen,
                               "issue": "短すぎ" if tlen < MIN_TITLE else "長すぎ", "pubDate": pub})
        title_map[title].append(fn)
    dups = [{"title": t, "files": f, "count": len(f)}
            for t, f in title_map.items() if len(f) >= 2]
    return {"total": len(files), "short": short, "bad_title": bad_title, "dups": dups}


def save_issues(results: dict) -> int:
    """問題を JSON に保存。自動修正スクリプトが読む。件数を返す。"""
    issues = []
    for a in results["short"]:
        issues.append({"type": "short_body",  "file": a["file"], "chars": a["chars"],
                       "title": a["title"], "status": "pending"})
    for a in results["bad_title"]:
        issues.append({"type": "bad_title",   "file": a["file"], "length": a["length"],
                       "issue": a["issue"], "title": a["title"], "status": "pending"})
    for d in results["dups"]:
        issues.append({"type": "dup_title",   "files": d["files"], "title": d["title"],
                       "status": "pending"})
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "quality_issues.json").write_text(
        json.dumps({"updated_at": datetime.now(JST).isoformat(), "issues": issues},
                   ensure_ascii=False, indent=2))
    return len(issues)


def build_text(results: dict, date_str: str) -> str:
    total  = results["total"]
    short  = results["short"]
    bad    = results["bad_title"]
    dups   = results["dups"]
    n      = len(short) + len(bad) + len(dups)

    lines = [f"Novlify 品質チェック {date_str}  総記事 {total}本 / 要対応 {n}件", ""]

    if short:
        lines.append(f"■ 文字数不足（{MIN_BODY}字未満）{len(short)}件")
        for a in short:
            lines.append(f"  {a['file']}  {a['chars']}字")
    if bad:
        lines.append(f"■ タイトル文字数異常（{MIN_TITLE}〜{MAX_TITLE}字）{len(bad)}件")
        for a in bad:
            lines.append(f"  {a['file']}  {a['length']}字（{a['issue']}）")
    if dups:
        lines.append(f"■ 重複タイトル {len(dups)}件")
        for d in dups:
            lines.append(f"  「{d['title'][:30]}」← {', '.join(d['files'])}")
    if n == 0:
        lines.append("✅ 問題なし")

    lines += ["", "── 来週追加予定のチェック ──",
              "リンク切れ / アフィリエイト有無 / 画像有無 / h2数 / description長 / 鮮度"]
    return "\n".join(lines)


def send_email(text: str, date_str: str, n_issues: int) -> None:
    u = os.environ.get("GMAIL_USER")
    p = os.environ.get("GMAIL_APP_PASSWORD")
    if not u or not p:
        print("Gmail未設定スキップ"); return
    status = f"⚠ {n_issues}件" if n_issues else "✅ 問題なし"
    msg = MIMEText(text, "plain", "utf-8")
    msg["Subject"] = f"【Novlify】品質 {status} | {date_str}"
    msg["From"] = msg["To"] = u
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.login(u, p)
        s.sendmail(u, u, msg.as_bytes())
    print("品質チェックメール送信完了")


if __name__ == "__main__":
    now      = datetime.now(JST)
    date_str = now.strftime("%Y/%m/%d")
    print("品質チェック開始...")
    results  = check_articles()
    n        = len(results["short"]) + len(results["bad_title"]) + len(results["dups"])
    print(f"総記事: {results['total']}  要対応: {n}")
    save_issues(results)
    text = build_text(results, date_str)
    print(text)
    if os.environ.get("WEEKLY_BATCH") == "1":
        report_dir = DATA_DIR / "weekly_reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "quality.txt").write_text(text, encoding="utf-8")
        print("品質レポートを保存（週次まとめ送信）")
    else:
        send_email(text, date_str, n)

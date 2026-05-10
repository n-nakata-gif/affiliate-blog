"""
自動修正スクリプト
2つのモードで動作する:

  --mode quality   : data/quality_issues.json を読んでタイトル異常・重複を Claude で修正
  --mode error     : 直近の失敗ワークフローのエラーログを Claude で解析してコードを修正

どちらも修正内容を git commit して Gmail で通知する。

呼び出し元:
  quality_check.yml → python src/auto_fix.py --mode quality
  blog_auto.yml     → python src/auto_fix.py --mode error --job <job名>
"""
from __future__ import annotations

import argparse, json, os, re, smtplib, subprocess, sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

JST      = timezone(timedelta(hours=9))
BLOG_DIR = Path(__file__).parent / "content" / "blog"
DATA_DIR = Path(__file__).parent.parent / "data"
SRC_DIR  = Path(__file__).parent
CLIENT   = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL    = "claude-sonnet-4-5"

# ── ユーティリティ ──────────────────────────────────────────────

def git_commit(paths: list[str], message: str) -> bool:
    subprocess.run(["git", "config", "user.name",  "github-actions[bot]"], check=False)
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
    for p in paths:
        subprocess.run(["git", "add", p], check=False)
    r = subprocess.run(["git", "commit", "-m", message], capture_output=True)
    if r.returncode == 0:
        subprocess.run(["git", "push"], check=False)
        return True
    return False


def send_notify(subject: str, body: str) -> None:
    u = os.environ.get("GMAIL_USER")
    p = os.environ.get("GMAIL_APP_PASSWORD")
    if not u or not p:
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = msg["To"] = u
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo(); s.starttls(); s.login(u, p)
        s.sendmail(u, u, msg.as_bytes())


def parse_frontmatter(content: str) -> tuple[dict, str, str]:
    """(meta, body, fm_raw) を返す"""
    if not content.startswith("---"):
        return {}, content, ""
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content, ""
    fm_raw = content[:end + 4]
    meta: dict = {}
    for line in content[3:end].strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, content[end + 4:].strip(), fm_raw


# ── MODE: quality ───────────────────────────────────────────────

def fix_quality_issues() -> list[str]:
    """quality_issues.json の pending 問題を修正して変更ファイルリストを返す"""
    issues_path = DATA_DIR / "quality_issues.json"
    if not issues_path.exists():
        print("quality_issues.json なし"); return []

    data   = json.loads(issues_path.read_text(encoding="utf-8"))
    issues = [i for i in data.get("issues", []) if i.get("status") == "pending"]
    if not issues:
        print("修正対象なし"); return []

    changed_files: list[str] = []
    log_lines: list[str] = []

    for issue in issues:
        itype = issue.get("type", "")
        try:
            if itype == "bad_title":
                result = fix_bad_title(issue)
            elif itype == "dup_title":
                result = fix_dup_title(issue)
            else:
                # short_body は本文拡張リスクが高いため人間判断に委ねる
                issue["status"] = "skipped"
                log_lines.append(f"SKIP {itype}: {issue.get('file','')} (人間判断推奨)")
                continue

            if result:
                issue["status"] = "done"
                changed_files.append(result)
                log_lines.append(f"FIX {itype}: {result}")
            else:
                issue["status"] = "error"
                log_lines.append(f"ERR {itype}: {issue.get('file','')}")
        except Exception as e:
            issue["status"] = "error"
            log_lines.append(f"ERR {itype}: {e}")

    # 更新したキューを保存
    issues_path.write_text(
        json.dumps({"updated_at": datetime.now(JST).isoformat(), "issues": data["issues"]},
                   ensure_ascii=False, indent=2))
    changed_files.append(str(issues_path))

    print("\n".join(log_lines))
    return changed_files, log_lines


def fix_bad_title(issue: dict) -> str | None:
    """Claude にタイトルを修正させてフロントマターを更新する"""
    path = BLOG_DIR / issue["file"]
    if not path.exists(): return None

    content = path.read_text(encoding="utf-8")
    meta, body, fm_raw = parse_frontmatter(content)
    old_title = meta.get("title", "")
    direction = issue.get("issue", "")   # "短すぎ" or "長すぎ"
    target = f"32〜60字"

    resp = CLIENT.messages.create(
        model=MODEL, max_tokens=200,
        messages=[{"role": "user", "content":
            f"次の記事タイトルを{target}になるよう修正してください。"
            f"方向性:「{direction}」。タイトルのみ返してください（前置き不要）。\n\n{old_title}"}]
    )
    new_title = resp.content[0].text.strip().strip('"').strip("'")
    if not (32 <= len(new_title) <= 60):
        return None

    new_fm = fm_raw.replace(f'title: "{old_title}"', f'title: "{new_title}"')
    if new_fm == fm_raw:
        new_fm = fm_raw.replace(f"title: {old_title}", f'title: "{new_title}"')
    if new_fm == fm_raw:
        return None  # 置換できなかった

    path.write_text(new_fm + "\n\n" + body, encoding="utf-8")
    print(f"  タイトル更新: {old_title[:30]} → {new_title[:30]}")
    return str(path)


def fix_dup_title(issue: dict) -> str | None:
    """重複タイトルのうち新しい方を Claude に修正させる"""
    files = issue.get("files", [])
    if len(files) < 2: return None

    # pubDate が新しい方を修正対象にする
    candidates = []
    for fn in files:
        p = BLOG_DIR / fn
        if not p.exists(): continue
        content = p.read_text(encoding="utf-8")
        meta, _, _ = parse_frontmatter(content)
        candidates.append((meta.get("pubDate", ""), fn, p))
    if not candidates: return None
    candidates.sort(reverse=True)   # 新しい順
    _, fn, path = candidates[0]

    content = path.read_text(encoding="utf-8")
    meta, body, fm_raw = parse_frontmatter(content)
    old_title = meta.get("title", "")

    resp = CLIENT.messages.create(
        model=MODEL, max_tokens=200,
        messages=[{"role": "user", "content":
            f"次の記事タイトルと重複しない別タイトルを32〜60字で提案してください。"
            f"ファイル名「{fn}」の内容に合わせて変更してください。"
            f"タイトルのみ返してください（前置き不要）。\n\n{old_title}"}]
    )
    new_title = resp.content[0].text.strip().strip('"').strip("'")
    if new_title == old_title or not (32 <= len(new_title) <= 60):
        return None

    new_fm = fm_raw.replace(f'title: "{old_title}"', f'title: "{new_title}"')
    if new_fm == fm_raw:
        return None

    path.write_text(new_fm + "\n\n" + body, encoding="utf-8")
    print(f"  重複タイトル修正: {old_title[:30]} → {new_title[:30]}")
    return str(path)


# ── MODE: error ─────────────────────────────────────────────────

def fetch_failed_log(run_id: str) -> str:
    r = subprocess.run(
        ["gh", "run", "view", run_id, "--log-failed"],
        capture_output=True, text=True)
    return (r.stdout + r.stderr)[:8000]   # Claude の入力上限に合わせて切り詰め


def detect_python_error(log: str) -> tuple[str, str]:
    """(エラー概要, 原因ファイルパス) を返す。不明なら ("", "")"""
    tb = re.search(r'Traceback \(most recent call last\):.*', log, re.DOTALL)
    if not tb: return "", ""
    error_block = tb.group(0)[:3000]

    # src/ 内のファイルだけを対象にする
    files = re.findall(r'File "([^"]*src/[^"]+\.py)"', error_block)
    target = files[-1] if files else ""
    return error_block, target


def ask_claude_fix(error_log: str, file_path: str) -> str | None:
    """Claude にコード修正を依頼。修正済みファイル全文を返す。失敗なら None。"""
    code = Path(file_path).read_text(encoding="utf-8") if Path(file_path).exists() else ""
    if not code:
        return None

    resp = CLIENT.messages.create(
        model=MODEL, max_tokens=8000,
        messages=[{"role": "user", "content":
            f"以下のPythonエラーを修正してください。\n\n"
            f"=== エラーログ ===\n{error_log}\n\n"
            f"=== {file_path} ===\n```python\n{code}\n```\n\n"
            f"修正後のファイル全体を```python ... ```で返してください。"
            f"修正できない場合は \"CANNOT_FIX: 理由\" と返してください。"}]
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("CANNOT_FIX"):
        print("Claude: " + raw)
        return None

    # コードブロックを抽出
    m = re.search(r"```python\n([\s\S]+?)```", raw)
    return m.group(1) if m else None


def fix_error(job_name: str) -> tuple[bool, str]:
    """エラーを修正して (成功フラグ, サマリー) を返す"""
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not run_id:
        return False, "GITHUB_RUN_ID 未設定"

    log = fetch_failed_log(run_id)
    if not log:
        return False, "ログ取得失敗"

    error_block, target_file = detect_python_error(log)
    if not error_block:
        # Python エラーでない（インフラ障害など）→ 通知のみ
        return False, f"Pythonエラーではないためコード修正をスキップ\nログ先頭:\n{log[:500]}"

    print(f"エラー検出: {target_file}")
    print(f"エラー内容: {error_block[:300]}")

    new_code = ask_claude_fix(error_block, target_file)
    if not new_code:
        return False, f"Claude が修正できませんでした\nエラー:\n{error_block[:500]}"

    Path(target_file).write_text(new_code, encoding="utf-8")
    err_summary = re.search(r'(\w+Error[^\n]*)', error_block)
    err_short   = err_summary.group(1)[:60] if err_summary else "unknown error"
    committed   = git_commit([target_file],
                              f"fix: auto-fix {Path(target_file).name} ({err_short}) [skip ci]")
    if committed:
        return True, f"修正適用: {target_file}\nエラー: {err_short}"
    else:
        return False, f"修正コードは生成されましたが commit に失敗しました"


# ── メイン ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["quality", "error"], required=True)
    parser.add_argument("--job",  default="", help="ジョブ名（error モード用）")
    args = parser.parse_args()

    now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    if args.mode == "quality":
        print("品質問題の自動修正を開始...")
        result = fix_quality_issues()
        if isinstance(result, tuple):
            changed, log_lines = result
        else:
            changed, log_lines = result, []

        if len(changed) > 1:   # quality_issues.json 以外に変更があった
            git_commit(changed, "fix: auto-fix quality issues [skip ci]")
            body = "品質チェック自動修正\n\n" + "\n".join(log_lines)
            if os.environ.get("WEEKLY_BATCH") == "1":
                report_dir = DATA_DIR / "weekly_reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / "quality_fix.txt").write_text(body, encoding="utf-8")
                print("修正ログを保存（週次まとめ送信）")
            else:
                send_notify(f"【Novlify】品質 自動修正完了 | {now}", body)
        else:
            print("修正対象なし or 全スキップ")

    elif args.mode == "error":
        print(f"エラー自動修正を開始... job={args.job}")
        success, summary = fix_error(args.job)
        status  = "✅ 修正済み" if success else "⚠ 修正不可"
        subject = f"【Novlify】{status} {args.job} | {now}"
        body    = f"ジョブ: {args.job}\nステータス: {status}\n\n{summary}"
        send_notify(subject, body)
        print(body)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

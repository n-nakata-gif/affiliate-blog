"""
既存ブログ記事の「AIっぽい文体」を一括修正するスクリプト。

7つの観点でリライトする:
1. 文末の単調さ（同じ語尾の連続）
2. 具体性不足（抽象表現・体験・数字・感情の欠如）
3. 内容の反復（同じ意味の言い換え繰り返し）
4. テンポの単調さ（文の長さのリズムが均一）
5. 理由・根拠の弱さ（結論だけで終わる）
6. 前提条件の欠落・飛躍
7. キーワードの過剰反復

実行方法:
  python src/rewrite_human.py                    # 未処理記事を全件処理
  python src/rewrite_human.py --file path/to.md  # 1ファイル指定
  python src/rewrite_human.py --dry-run          # 実際には書き込まない
  python src/rewrite_human.py --genre business   # ジャンル絞り込み
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import anthropic

CONTENT_DIR = Path("src/content/blog")
MODEL = "claude-sonnet-4-6"
REWRITTEN_FLAG = "human_rewritten: true"

# ───────────────────────────────────────────────────────────────────
# プロンプト
# ───────────────────────────────────────────────────────────────────

_SYSTEM = """\
あなたは読者に寄り添う日本語ライターです。
与えられたブログ記事の本文を、より「人間らしく・読みやすく」書き直してください。

【最重要ルール】
- HTMLブロック（<div>、<a>、<figure>、<img>、<table> など）は一切変更しない。そのままコピーする。
- frontmatter（---で囲まれた部分）は変更しない。
- Markdown見出し（# ## ###）の構成・順序は変えない。
- アフィリエイトURLや内部リンクのURLは絶対に変更しない。
- 記事の情報量・主張・構成は維持する。文体と表現だけを改善する。
- 改善後の文字数は元の文章の±15%以内に収める。
"""

_HUMAN_REWRITE_PROMPT = """\
以下のブログ記事本文を、次の7つの観点で書き直してください。

【書き直しの7ルール】

1. 文末の多様化
   - 「〜です」「〜ます」「〜と思います」が3文以上連続しないようにする
   - 体言止め・問いかけ・短文・「〜でしょうか」など語尾を混ぜる
   - 悪い例：「便利です。使いやすいです。おすすめです。」
   - 良い例：「使いやすく、導入も簡単。迷ったらまずこれを試してみてください。」

2. 具体性の強化
   - 「〜と言われています」「〜と感じる方も多い」などの曖昧表現を減らす
   - 数字・状況・場面・感情を加えて読者がイメージできるようにする
   - 悪い例：「とても便利なツールです。」
   - 良い例：「月5時間かかっていた帳簿作業が、30分で終わるようになりました。」

3. 反復の削除
   - 同じ内容を少し言い換えて繰り返している文を削除または統合する
   - 特に「〜で悩む方が多い」→「〜は多くの人が悩むポイントだ」のような言い換え反復を削除

4. テンポの変化
   - 長い文（60文字超）の後には短い文（20文字以下）を置く
   - 箇条書き→文章→問いかけ、のようにリズムを変える
   - 均一な文の長さが5文以上続かないようにする

5. 根拠・理由の追加
   - 「おすすめです」「効果があります」で終わる箇所には「なぜなら〜」を添える
   - 比較・体験・数字のいずれかを根拠として使う

6. 主体の明確化
   - 「〜と感じます」→「筆者が実際に試したところ〜」など、誰の体験・意見かを明示
   - 「〜することが大切です」→「特に〇〇の場合は〜が効いてきます」のように対象を絞る

7. キーワード分散
   - 同じ単語・表現が3文以内に2回以上出てきたら、類語・代名詞・省略で分散する
   - 特にタイトルのキーワードを本文内で連発しない

【禁止事項】
- HTMLタグ・URL・frontmatter の変更・削除
- 事実情報（数字・法律・制度名）の変更
- 見出し構成の変更
- アフィリエイトリンクの変更

【出力形式】
書き直した記事本文のみを出力してください。説明文・コメントは不要です。

---
{article_body}
---
"""

# ───────────────────────────────────────────────────────────────────
# ユーティリティ
# ───────────────────────────────────────────────────────────────────

def extract_frontmatter(text: str) -> tuple[str, str]:
    """frontmatter と本文を分離する。"""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    fm = text[: end + 4]   # "---\n...---" 部分
    body = text[end + 4 :]  # 残り（改行含む）
    return fm, body


def is_already_rewritten(frontmatter: str) -> bool:
    return "human_rewritten" in frontmatter


def add_rewritten_flag(frontmatter: str) -> str:
    """frontmatter の末尾 --- の直前に human_rewritten: true を追加。"""
    lines = frontmatter.rstrip().splitlines()
    # 最後の --- の前に挿入
    insert_idx = len(lines) - 1
    lines.insert(insert_idx, REWRITTEN_FLAG)
    return "\n".join(lines) + "\n"


def rewrite_article_body(client: anthropic.Anthropic, body: str) -> str:
    prompt = _HUMAN_REWRITE_PROMPT.format(article_body=body)
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except anthropic.RateLimitError:
            if attempt < 2:
                print("  ⚠ レートリミット。60秒待機…", flush=True)
                time.sleep(60)
            else:
                raise
        except anthropic.APIError as e:
            print(f"  ✗ API エラー: {e}", flush=True)
            raise


def process_file(client: anthropic.Anthropic, path: Path, dry_run: bool = False) -> bool:
    """1ファイルをリライトする。成功したら True を返す。"""
    text = path.read_text(encoding="utf-8")
    fm, body = extract_frontmatter(text)

    if is_already_rewritten(fm):
        print(f"  スキップ（処理済）: {path.name}")
        return False

    print(f"  処理中: {path.name} ({len(body):,}字)", flush=True)
    new_body = rewrite_article_body(client, body)

    if not dry_run:
        new_fm = add_rewritten_flag(fm)
        new_text = new_fm + new_body
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ 完了: {path.name}")
    else:
        print(f"  [dry-run] {path.name} → {len(new_body):,}字 (元: {len(body):,}字)")

    return True


# ───────────────────────────────────────────────────────────────────
# main
# ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ブログ記事を人間らしい文体にリライト")
    parser.add_argument("--file", help="特定ファイルのみ処理")
    parser.add_argument("--genre", help="ジャンル絞り込み (business/investment/gadget/travel/gourmet)")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなし（確認用）")
    parser.add_argument("--limit", type=int, default=0, help="処理件数上限（0=無制限）")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY が未設定です", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # 対象ファイル収集
    if args.file:
        targets = [Path(args.file)]
    else:
        pattern = f"{args.genre}_*.md" if args.genre else "*.md"
        targets = sorted(CONTENT_DIR.glob(pattern))
        # best-coffee・remote-work などの固定記事は除外
        targets = [p for p in targets if re.match(r"[a-z]+_\d{8}\.md", p.name)]

    print(f"対象: {len(targets)} ファイル (dry_run={args.dry_run})")
    processed = 0

    for path in targets:
        if args.limit and processed >= args.limit:
            print(f"--limit {args.limit} に達したので終了")
            break
        try:
            if process_file(client, path, dry_run=args.dry_run):
                processed += 1
                time.sleep(2)  # レートリミット回避
        except Exception as e:
            print(f"  ✗ エラー({path.name}): {e}", flush=True)
            continue

    print(f"\n完了: {processed} 件リライト")


if __name__ == "__main__":
    main()

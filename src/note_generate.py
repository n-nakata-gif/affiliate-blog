"""
Novlifyブログのビジネス記事をnote向けに変換するスクリプト。

note収益化セミナー（中村青さん）で学んだ以下の戦略を反映：
- 「1人の具体的な読者」にピンポイントで刺さる記事
- 悩み共感→問題提起→解決策→まとめ の構成
- 数字入りタイトルで内容を明確に
- 小学生でも分かる平易な言葉
- noteでは楽天・Amazon以外のアフィリエイトリンク不可
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

BLOG_CONTENT_DIR = Path("src/content/blog")
NOTE_DRAFTS_DIR = Path("data/note_drafts")
NOTE_POSTED_FILE = Path("data/note_posted.json")
BLOG_BASE_URL = "https://novlify.jp/blog"
MODEL = "claude-sonnet-4-6"

_GENERATION_PROMPT = """\
あなたはnoteで月5万円以上稼ぐ副業・ライフスタイル系ライターです。
以下のブログ記事を「参考情報」として、note向けの無料記事を一から書いてください。
ブログ記事のコピペは絶対NGです。あくまで題材として活用し、note読者向けに新しく書き直してください。

## note記事作成ルール

### ターゲット読者（必ず1人の具体的な人物をイメージして書く）
「副業を始めたいけど何から手をつければいいかわからない30代会社員」
- テレワークで通勤時間は浮いたのに何もできていない
- 子育て・家事と両立できるか不安
- 特別なスキルがなくても始められるか知りたい

### タイトルのルール
- 数字を必ず1つ以上含める（例：「3つの方法」「月5万円」「7ステップ」）
- 読者の悩みと解決後の状態が伝わるもの
- 50文字以内
- 例：「在宅副業で月5万円稼いだ私が最初にやった7つのこと」

### 記事構成（この順序で書く）

**1. 冒頭・共感パート（300字程度）**
「〜で悩んでいませんか？」と読者の悩みに正面から寄り添う。
「この記事を読めば〜できます」と読み続けるメリットを約束する。

**2. 問題提起パート（300字程度）**
なぜその悩みが生まれるのかを解説する。
読者が「そうそう、それが知りたかった！」と思える内容。

**3. メインコンテンツ（1500〜2000字）**
具体的な情報・解決策を親しみやすい語りかけ調で届ける。
## 見出しを3〜5個使って読みやすく構成する（### 以下は使わない）。
数字・具体例・比較を積極的に使う。

**4. まとめパート（300字程度）**
記事の要点を3点以内で箇条書き。
Novlify.jpへの誘導CTA（下記）を必ず入れる。

### 文体のルール
- 小学6年生でも分かる平易な言葉で書く
- 「〜ですね」「〜じゃないでしょうか」など親しみやすい語りかけ調
- 一文は40文字以内を目安に短く切る
- 専門用語は使わない（使う場合は必ず説明を入れる）

### アフィリエイトリンクのルール
- noteの規約上、楽天・Amazon以外のアフィリエイトリンクは使わない
- 無料記事なのでリンクは最小限に。Novlifyブログへの誘導が主目的

### 末尾のCTA（必ず最後に入れる）
---
もっと詳しく知りたい方は、こちらもチェックしてみてください👉
[Novlify.jp で詳しく読む]({blog_url})
---

### 禁止事項
- 「絶対」「必ず」「100%」などの断定的な表現
- 根拠のない「1位」「最強」などの表現
- HTMLタグ（noteはMarkdownのみ）
- ブログ記事のコピペ（内容が被っても表現は必ず変える）

## 参考にするブログ記事
タイトル：{title}
ブログURL：{blog_url}

---
{content}
---

## 出力形式（必ずこのJSON形式で出力すること）
```json
{{
  "title": "note記事のタイトル（50文字以内、数字を含む）",
  "body": "note記事の本文（Markdown形式、2000〜3000字）",
  "tags": ["副業", "在宅ワーク", "会社員副業", "副業初心者", "収入アップ"]
}}
```
"""


def load_posted() -> set[str]:
    if NOTE_POSTED_FILE.exists():
        data = json.loads(NOTE_POSTED_FILE.read_text(encoding="utf-8"))
        return set(data.get("posted", []))
    return set()


def get_unprocessed_article() -> Path | None:
    """未処理のビジネス記事を1件返す（古い順）。"""
    posted = load_posted()
    existing_drafts = {p.stem for p in NOTE_DRAFTS_DIR.glob("*.json")} if NOTE_DRAFTS_DIR.exists() else set()

    for path in sorted(BLOG_CONTENT_DIR.glob("business_*.md")):
        stem = path.stem
        if stem not in posted and stem not in existing_drafts:
            return path
    return None


def extract_blog_content(md_text: str) -> tuple[str, str]:
    """frontmatterからtitleを抽出し、本文のHTMLタグとアフィリエイトリンクを除去する。"""
    lines = md_text.splitlines()
    title = ""
    in_fm = False
    content_start = 0

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_fm = True
            continue
        if in_fm:
            if line.strip() == "---":
                content_start = i + 1
                in_fm = False
            elif line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"')

    content = "\n".join(lines[content_start:])

    # HTMLタグを除去
    content = re.sub(r"<[^>]+>", "", content)
    # PR表記コメントを除去
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    # アフィリエイトURLを含むMarkdownリンクをテキストのみに変換
    content = re.sub(
        r"\[([^\]]+)\]\(https?://[^\)]*(?:affiliate|aff|click|ad|rcm|a8|felmat|moshimo|vc|vavc)[^\)]*\)",
        r"\1",
        content,
        flags=re.IGNORECASE,
    )
    # 連続する空行を2行に圧縮
    content = re.sub(r"\n{3,}", "\n\n", content)

    return title, content.strip()


def generate_note_article(article_path: Path) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    md_text = article_path.read_text(encoding="utf-8")
    title, content = extract_blog_content(md_text)

    slug = article_path.stem
    blog_url = f"{BLOG_BASE_URL}/{slug}/"

    prompt = _GENERATION_PROMPT.format(
        title=title,
        blog_url=blog_url,
        content=content[:8000],  # トークン上限対策
    )

    print(f"Claude API呼び出し中 (model={MODEL})...")
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text

    # JSONブロックを抽出
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        note_data = json.loads(json_match.group(1))
    else:
        # フォールバック：JSON部分を直接パース
        note_data = json.loads(response_text)

    note_data["source_file"] = article_path.name
    note_data["blog_url"] = blog_url
    note_data["created_at"] = datetime.now(timezone.utc).isoformat()

    return note_data


def main() -> None:
    NOTE_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    article_path = get_unprocessed_article()
    if article_path is None:
        print("未処理のビジネス記事がありません（全記事変換済み）")
        sys.exit(0)

    print(f"変換対象: {article_path.name}")

    try:
        note_data = generate_note_article(article_path)
    except Exception as e:
        print(f"ERROR: 記事変換に失敗しました: {e}")
        sys.exit(1)

    out_path = NOTE_DRAFTS_DIR / f"{article_path.stem}.json"
    out_path.write_text(json.dumps(note_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ ドラフト保存: {out_path}")
    print(f"   タイトル: {note_data['title']}")
    print(f"   文字数: {len(note_data['body'])}字")
    print(f"   タグ: {note_data.get('tags', [])}")


if __name__ == "__main__":
    main()

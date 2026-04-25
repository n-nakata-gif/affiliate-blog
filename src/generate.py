import argparse
import os
import sys
import re
import json
import base64
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import anthropic

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BLOG_URL = "https://affiliate-blog.nori-nakata1004.workers.dev"
REPO = "n-nakata-gif/affiliate-blog"
BRANCH = "main"
MODEL = "claude-opus-4-7"
MIN_CHARS = 3000
TOPICS_PATH = "data/topics.json"

_COMMON_PRINCIPLES = """\
- 常に最新トレンドを意識し、読者に有益な情報を提供する
- 読者の気持ちに寄り添い、共感を持って語りかける
- 数値・データは出典を明記するか「〜といわれています」と表現する
- 誇張表現（絶対・必ず・100%）は使わない
- デメリット・リスク・注意点も正直に記載する
- 薬機法・景品表示法・著作権を遵守する
- ファクトチェック済みの事実のみ記載する"""


def _sys(genre_label: str, extra: str) -> str:
    return (
        f"あなたは{genre_label}の誠実な日本語ブログライターです。\n"
        f"以下の原則を必ず守ってください：\n{_COMMON_PRINCIPLES}\n\n{extra}"
    )


GENRE_CONFIG = {
    "business": {
        "system": _sys(
            "ビジネス・副業ジャンル",
            "副業・ビジネスの記事では、再現性のある具体的な方法を提示し、"
            "読者が実際に行動に移せるよう誘導してください。"
            "リスクや向いていない人の情報も必ず含めてください。",
        ),
        "default_tags": ["ビジネス", "副業"],
        "article_type": "business",
    },
    "investment": {
        "system": _sys(
            "投資・資産運用ジャンル",
            "投資・資産運用の記事では、リスク説明を必ず含め、投資助言にならないよう注意してください。\n"
            "「必ず儲かる」「元本保証」等の表現は絶対に使わず、"
            "税制・制度情報には「最新情報は金融機関・税務署でご確認ください」を添えてください。",
        ),
        "default_tags": ["投資", "資産運用", "NISA"],
        "article_type": "investment",
    },
    "travel": {
        "system": _sys(
            "旅行ジャンル",
            "旅行の記事では、最新の営業状況・料金は変動する旨を必ず明記してください。\n"
            "読者が実際に計画を立てられるよう、アクセス・費用・所要時間などの実用情報を具体的に記載してください。",
        ),
        "default_tags": ["旅行", "観光", "旅"],
        "article_type": "travel",
    },
    "gourmet": {
        "system": _sys(
            "グルメ・食ジャンル",
            "グルメ・食の記事では、季節感と入手しやすさを考慮した情報を提供してください。\n"
            "味・食感・香り・見た目などの五感に訴える描写を豊かに表現し、"
            "価格・営業時間は変動する旨を明記してください。",
        ),
        "default_tags": ["グルメ", "食べ物", "グルメスポット"],
        "article_type": "gourmet",
    },
}

_BODY_SECTIONS = {
    "business": """\
1. **導入（PREP法の P）**（200字以上）
   - 読者の悩みに共感する書き出し・記事で得られる価値・具体的な数字

2. **なぜ重要か（R）**（300字以上）
   - 読者がこの情報を必要とする背景・知らないと損する理由

3. **具体的な方法・事例（E）**（600字以上）
   - 再現性のある具体的ステップ・成功例と失敗例・デメリットも正直に

4. **実践のポイントと落とし穴**（300字以上）
   - 初心者がつまずくポイント・根拠のある推薦のみ

5. **まとめ（再 P）**（200字以上）
   - 要点整理・読者への励ましと次のアクション提案

6. **FAQ**（3問以上・各100字以上）
   - 読者のリアルな疑問に丁寧に回答""",

    "investment": """\
1. **導入**（200字以上）
   - 読者の資産形成の悩みに共感・記事で得られる知識を明示

2. **この投資手法のしくみ**（300字以上）
   - 仕組みをわかりやすく解説・制度の概要と特徴

3. **具体的な始め方・手順**（600字以上）
   - 口座開設から運用開始まで再現性のあるステップ

4. **リスクと注意事項**（400字以上・必須）
   - 元本割れリスク・流動性リスク・為替リスク等を正直に説明
   - 「投資にはリスクがあります」を本文に明記
   - 投資判断は自己責任であることを記載

5. **実践のポイント**（300字以上）
   - 長期・分散・積立の考え方・続けるためのコツ

6. **まとめ**（200字以上）
   - 要点整理・専門家や金融機関への相談を推奨

7. **FAQ**（3問以上・各100字以上）
   - 読者のリアルな疑問に丁寧に回答""",

    "travel": """\
1. **導入**（200字以上）
   - 旅の魅力や読者のワクワク感を引き出す書き出し

2. **この旅先・旅行術の見どころ**（300字以上）
   - 他にはない魅力・体験できること・季節のおすすめ

3. **アクセス・料金・営業時間**（400字以上・必須）
   - 交通手段と所要時間の目安・費用の目安（宿泊・飲食・入場料）
   - 定休日・営業時間・予約の要否
   - 「〜年〜月時点の情報です。最新情報は公式サイトでご確認ください」を必ず記載

4. **具体的な楽しみ方・モデルプラン**（600字以上）
   - 日程例・おすすめスポットの巡り方・穴場情報

5. **注意点・持ち物・混雑情報**（300字以上）
   - 季節・天候の注意・混雑しやすい時期・持ち物リスト

6. **まとめ**（200字以上）
   - 旅の魅力を再確認・読者の背中を押す言葉

7. **FAQ**（3問以上・各100字以上）
   - 読者のリアルな疑問に丁寧に回答""",

    "gourmet": """\
1. **導入**（200字以上）
   - 食欲をそそる臨場感ある書き出し・記事で得られる体験価値を明示

2. **この料理・スポットの魅力**（300字以上）
   - 味・食感・香り・見た目など五感に訴える描写・季節感

3. **食材・レシピ・お店情報**（600字以上・必須）
   - 旬の食材とその選び方・入手方法・具体的な調理手順（レシピの場合）
   - または店の詳細情報（住所・最寄り駅・予約方法）
   - 「〜年〜月時点の情報です。営業時間・料金は変動する場合があります」を必ず記載

4. **実際の味・価格・コスパ評価**（300字以上）
   - 正直なレビュー・デメリットや向き不向きも記載

5. **注意点（アレルギー・価格・予約・混雑）**（200字以上）
   - アレルギー情報・繁忙期の混雑・駐車場情報など

6. **まとめ**（200字以上）
   - 食の楽しさを再確認・次の食体験への橋渡し

7. **FAQ**（3問以上・各100字以上）
   - 読者のリアルな疑問に丁寧に回答""",
}


# ── トピック読み込み ──────────────────────────────────────────

def load_topics() -> list:
    with open(TOPICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def select_topic(topics: list, date_str: str, genre: str) -> dict:
    if not topics:
        raise ValueError(f"{TOPICS_PATH} が空です")
    filtered = [t for t in topics if t.get("genre", "business") == genre]
    if not filtered:
        filtered = topics
    idx = int(date_str) % len(filtered)
    t = filtered[idx]
    if isinstance(t, str):
        return {"title": t, "genre": genre, "tags": GENRE_CONFIG[genre]["default_tags"]}
    return t


def _get(topic: dict, *keys, default=""):
    for k in keys:
        v = topic.get(k)
        if v:
            return v
    return default


# ── 文字数カウント ────────────────────────────────────────────

def count_body_chars(md: str) -> int:
    text = re.sub(r"^---[\s\S]*?---\n", "", md, count=1)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#*`|]", "", text)
    return len(re.sub(r"\n+", "\n", text).strip())


# ── 記事生成（Claude API） ────────────────────────────────────

def build_prompt(topic: dict, date_str: str, genre: str) -> str:
    today = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    config = GENRE_CONFIG.get(genre, GENRE_CONFIG["business"])

    title_hint    = _get(topic, "title", "topic", "keyword")
    tags          = _get(topic, "tags", default=config["default_tags"])
    summary       = _get(topic, "summary", "notes", "description",
                          default="記事タイトルから最適な内容を考えてください")
    key_points    = _get(topic, "key_points", "points", default=[])
    keyword_main  = _get(topic, "keyword_main", default="")
    keyword_sub   = _get(topic, "keyword_sub",  default=[])
    target_reader = _get(topic, "target_reader", default="")

    tags_str = json.dumps(tags, ensure_ascii=False)
    kp_str   = ("\n".join(f"- {p}" for p in key_points)
                if key_points else "（自由に構成してください）")

    if keyword_main:
        sub_str = (json.dumps(keyword_sub, ensure_ascii=False)
                   if isinstance(keyword_sub, list) else str(keyword_sub))
        seo_section = (
            f"\n## SEO要件\n"
            f"- メインキーワード「{keyword_main}」をtitle・冒頭100字・h2見出し1つ以上に自然に含める\n"
            f"- サブキーワード {sub_str} を各セクションに自然に分散させる\n"
            f"- ターゲット読者: {target_reader}\n"
            f"- h2見出しは4〜6個、各h2の下にh3を2〜3個設ける\n"
            f"- メタディスクリプションは120字以内\n"
        )
    else:
        seo_section = ""

    body_sections = _BODY_SECTIONS.get(genre, _BODY_SECTIONS["business"])

    return f"""以下のトピックについて、ブログ記事（Markdown形式）を作成してください。

## トピック情報
- テーマ: {title_hint}
- 概要: {summary}
- キーポイント:
{kp_str}
{seo_section}
## 記事の要件

### frontmatter（必ずこの形式で出力）
```
---
title: "（読者が思わずクリックしたくなる具体的なタイトル）"
description: "（150字以内・記事で得られる価値を具体的に説明）"
pubDate: {today}
tags: {tags_str}
---
```

### 本文構成（合計{MIN_CHARS}字以上・日本語）

{body_sections}

## 最重要：記事執筆の姿勢
- **誠実さを最優先**: PVや収益より読者の利益を優先する
- **デメリットも正直に書く**: 良い点だけを誇張しない
- **確認できない数値は柔らかい表現に**: 「〜といわれています」「〜とされています」
- **誇張表現禁止**: 「絶対」「必ず」「100%」「最高」は根拠なく使わない
- **魂のこもった文章**: 一人の読者に語りかけるように書く
- frontmatterから末尾まで完全に出力すること（省略・要約禁止）
"""


def generate_article(client: anthropic.Anthropic, prompt: str, genre: str) -> str:
    config = GENRE_CONFIG.get(genre, GENRE_CONFIG["business"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=8096,
        system=[
            {
                "type": "text",
                "text": config["system"],
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def supplement_article(client: anthropic.Anthropic, article: str, current_chars: int) -> str:
    shortage = MIN_CHARS - current_chars
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    f"以下のMarkdown記事は本文が約{current_chars}字で、"
                    f"目標の{MIN_CHARS}字に約{shortage}字不足しています。\n"
                    "以下のルールで加筆して完全な記事として出力してください：\n"
                    "- 各セクションをより詳しく（実体験・具体的なステップ・注意点を追加）\n"
                    "- FAQに1〜2問追加\n"
                    "- 誠実さを保ち、誇張表現は引き続き使わない\n"
                    "- frontmatter・見出し構成はそのまま保持する\n\n"
                    f"--- 元の記事 ---\n{article}\n"
                ),
            }
        ],
    )
    return response.content[0].text


def ensure_min_chars(client: anthropic.Anthropic, article: str, prompt: str) -> str:
    chars = count_body_chars(article)
    if chars >= MIN_CHARS:
        return article
    logger.info("本文 %d字 < %d字 → 補完実行", chars, MIN_CHARS)
    article = supplement_article(client, article, chars)
    chars = count_body_chars(article)
    if chars < MIN_CHARS:
        logger.error("補完後も %d字（目標 %d字）", chars, MIN_CHARS)
    return article


# ── GitHub API ────────────────────────────────────────────────

def gh(method: str, path: str, token: str, body=None):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} → {e.code}: {body_text}") from e


def push_file(token: str, repo_path: str, content: str, commit_message: str) -> str:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    try:
        existing = gh("GET", f"contents/{repo_path}?ref={BRANCH}", token)
        sha = existing.get("sha")
    except RuntimeError as e:
        if "404" in str(e):
            sha = None
        else:
            raise

    body = {"message": commit_message, "content": encoded, "branch": BRANCH}
    if sha:
        body["sha"] = sha

    result = gh("PUT", f"contents/{repo_path}", token, body)
    return result["commit"]["sha"]


# ── frontmatterパース ─────────────────────────────────────────

def extract_title(content: str) -> str:
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_tags(content: str) -> list:
    m = re.search(r'^tags:\s*\[(.+?)\]', content, re.MULTILINE)
    if not m:
        return []
    return [t.strip().strip("\"'") for t in m.group(1).split(',')]


# ── メイン ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--genre",
        choices=["business", "investment", "travel", "gourmet"],
        default="business",
    )
    args = parser.parse_args()
    genre = args.genre
    config = GENRE_CONFIG[genre]

    api_key  = os.environ.get("ANTHROPIC_API_KEY")
    gh_token = os.environ.get("GH_TOKEN")

    missing = [k for k, v in {"ANTHROPIC_API_KEY": api_key, "GH_TOKEN": gh_token}.items() if not v]
    if missing:
        print(f"ERROR: 環境変数が未設定です: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    if not Path(TOPICS_PATH).exists():
        print(f"ERROR: {TOPICS_PATH} が見つかりません", file=sys.stderr)
        sys.exit(1)

    now      = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")

    topics = load_topics()
    topic  = select_topic(topics, date_str, genre)

    client = anthropic.Anthropic(api_key=api_key)

    prompt  = build_prompt(topic, date_str, genre)
    article = generate_article(client, prompt, genre)
    article = ensure_min_chars(client, article, prompt)

    from factcheck import factcheck_article
    fc_result = factcheck_article(article, config["article_type"])
    if not fc_result["is_safe"]:
        print("ERROR: ファクトチェック失敗 - 投稿中止", file=sys.stderr)
        sys.exit(1)
    article = fc_result["verified_content"]

    repo_path      = f"src/content/blog/{genre}_{date_str}.md"
    commit_message = f"auto: add {genre} article {date_str}"
    commit_sha     = push_file(gh_token, repo_path, article, commit_message)

    commit_url = f"https://github.com/{REPO}/commit/{commit_sha}"
    print(commit_url)

    from notify import send_notification
    send_notification(
        article_type=config["article_type"],
        title=extract_title(article),
        article_url=commit_url,
        blog_url=BLOG_URL,
        tags=extract_tags(article),
        word_count=count_body_chars(article),
    )


if __name__ == "__main__":
    main()

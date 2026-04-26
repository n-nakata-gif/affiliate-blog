import os
import sys
import json
import logging

import anthropic

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

COLLECTED_PATH = "data/collected_business.json"
TOPICS_PATH = "data/topics.json"
MODEL = "claude-opus-4-7"
GENRE = "business"

_SYSTEM = (
    "あなたはビジネス・副業ジャンルのブログ編集長です。"
    "与えられたトピック候補を読者価値・SEO・法令遵守の観点で審査し、"
    "品質の高いものだけを選んで返してください。"
)

_PROMPT = """\
以下は自動収集されたビジネス・副業ジャンルのブログ記事トピック候補です。

{topics_json}

以下の基準で審査し、品質の高い順に最大5件を選んでください。
- 読者がすぐ行動に移せる具体性があるか
- 誇張表現（絶対・必ず・100%・最高）が含まれていないか
- タイトルに数字や具体的なベネフィットが含まれているか
- 投資助言・医療断言など法令リスクがないか

選んだトピックを必要に応じてタイトル・summary・key_points を改善し、
以下のJSON配列のみを返してください（説明文・コードブロック記号は不要）:
[
  {{
    "genre": "business",
    "title": "...",
    "tags": [...],
    "summary": "...",
    "key_points": [...],
    "keyword_main": "...",
    "keyword_sub": [...],
    "target_reader": "..."
  }}
]
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rsplit("```", 1)[0].strip()
    return text


def review_topics(client: anthropic.Anthropic, raw_topics: list) -> list:
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": _PROMPT.format(
                topics_json=json.dumps(raw_topics, ensure_ascii=False, indent=2)
            ),
        }],
    )
    raw = _strip_code_fence(response.content[0].text)
    try:
        reviewed = json.loads(raw)
        if not isinstance(reviewed, list):
            raise ValueError("レスポンスがリストではありません")
        logger.info("審査後トピック %d件", len(reviewed))
        return reviewed
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("JSONパース失敗: %s\nレスポンス:\n%s", e, raw)
        return raw_topics  # 審査失敗時は元のトピックをそのまま使う


def update_topics_json(approved: list) -> None:
    try:
        with open(TOPICS_PATH, "r", encoding="utf-8") as f:
            all_topics = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_topics = []

    # business エントリを差し替え、他ジャンルは保持
    others = [t for t in all_topics if t.get("genre") != GENRE]
    merged = approved + others

    with open(TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    logger.info("topics.json を更新しました（business: %d件, 合計: %d件）",
                len(approved), len(merged))


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    try:
        with open(COLLECTED_PATH, "r", encoding="utf-8") as f:
            raw_topics = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("%s が見つからないか不正です。スキップします", COLLECTED_PATH)
        return

    if not raw_topics:
        logger.warning("収集トピックが空です。スキップします")
        return

    if not api_key:
        logger.warning("ANTHROPIC_API_KEY が未設定のため審査をスキップし、収集結果をそのまま使います")
        update_topics_json(raw_topics)
        return

    client = anthropic.Anthropic(api_key=api_key)
    approved = review_topics(client, raw_topics)
    update_topics_json(approved)
    print(f"Analyzed {len(raw_topics)} → {len(approved)} topics → {TOPICS_PATH}")


if __name__ == "__main__":
    main()

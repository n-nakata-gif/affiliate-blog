import os
import sys
import json
import logging
import time
from datetime import datetime, timezone

import anthropic

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = "data/collected_business.json"
MODEL = "claude-opus-4-7"

_SYSTEM = (
    "あなたはビジネス・副業ジャンルのブログ編集長です。"
    "読者が今まさに検索している具体的なテーマを、SEOと読者ニーズの両面から提案してください。"
)

_PROMPT = """\
今日の日付: {today}

ビジネス・副業ジャンルで、今の読者が検索しそうなブログ記事トピックを5つ生成してください。

以下のJSON配列のみを出力してください（説明文・コードブロック記号は不要）:
[
  {{
    "genre": "business",
    "title": "（読者がクリックしたくなる具体的なタイトル）",
    "tags": ["タグ1", "タグ2", "タグ3"],
    "summary": "（記事の概要、100字以内）",
    "key_points": ["ポイント1", "ポイント2", "ポイント3", "ポイント4"],
    "keyword_main": "（メインSEOキーワード）",
    "keyword_sub": ["サブキーワード1", "サブキーワード2", "サブキーワード3"],
    "target_reader": "（ターゲット読者の具体的な説明）"
  }}
]

条件:
- 副業・在宅ワーク・スキルアップ・フリーランス・起業などビジネス系テーマ
- 誇張表現（絶対・必ず・100%）は使わない
- タイトルには数字や具体的なベネフィットを含める
- すべて日本語で出力
"""


def collect_business_topics(client: anthropic.Anthropic) -> list:
    today = datetime.now(timezone.utc).strftime("%Y年%m月%d日")
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": _PROMPT.format(today=today)}],
            )
            break
        except anthropic.RateLimitError:
            if attempt < 2:
                logger.warning("レートリミット。60秒後にリトライ (%d/3)", attempt + 1)
                time.sleep(60)
            else:
                logger.error("レートリミットのため3回失敗しました。スキップします")
                return []
    raw = response.content[0].text.strip()

    # コードブロックで囲まれている場合を除去
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        topics = json.loads(raw)
        if not isinstance(topics, list):
            raise ValueError("レスポンスがリストではありません")
        logger.info("トピック %d件を生成しました", len(topics))
        return topics
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("JSONパース失敗: %s\nレスポンス:\n%s", e, raw)
        return []


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY が未設定のためスキップします")
        os.makedirs("data", exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    client = anthropic.Anthropic(api_key=api_key)

    os.makedirs("data", exist_ok=True)
    topics = collect_business_topics(client)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

    print(f"Collected {len(topics)} business topics → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

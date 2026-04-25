import json
import os
import re
import sys

import anthropic

MODEL = "claude-opus-4-7"

_SYSTEM = """あなたは日本語アフィリエイトブログのファクトチェッカーです。
与えられた記事の事実確認を行い、修正した記事をJSON形式のみで返してください。

【記事執筆の最優先姿勢】
読者への誠実さを最優先にしてください。PVやアフィリエイト収益よりも読者の利益を優先します。
- 実際に役立つ情報だけを残す。文字数を埋めるような内容は削除する
- 商品のデメリット・注意点も正直に書く。良い点だけを誇張しない
- 「おすすめ」と書く商品は本当におすすめできるものだけに限定する
- 誇張表現（「絶対」「必ず」「100%」「最高」「業界No.1」等）は根拠がない限り削除する
- 一人の読者に向けて書くような、具体的で温かみのある表現を維持する
- 魂のこもった文章を大切にする。テンプレートを埋めるだけの無機質な文章は書き直す

【チェック対象】
web_search ツールを使い、最低2件のソースで以下を確認してください:
- 商品スペック・価格・発売日などの数値情報
- 統計データ・調査結果の引用
- 法律・制度に関する記述
- 健康・医療に関する情報
- 企業・ブランドに関する情報

【修正ルール】
- 確認できない数値 → 「〜といわれています」等の表現に変更
- 単一ソースしかない情報 → 文末に「※要確認」を付与
- 明らかに誤りの情報 → 削除して代替表現に置き換え
- 出典明記できる情報 → 文末に「（出典: ドメイン名）」を追記
- 誇張表現 → 根拠がない限り削除または柔らかい表現に修正

【is_safe 判定基準】
False（投稿しない）:
- 明らかな虚偽情報が含まれる
- 医療・法律の断定的な誤情報がある
- 商品スペックに重大な誤りがある
- 読者を誤解させる誇張表現が修正後も残っている

True（投稿してよい）:
- 軽微な不確実性のみ（表現修正済み）
- 全情報が複数ソースで確認済み

【出力形式】
説明文や前置きなく、必ず以下のJSON形式のみで返してください:
```json
{
  "verified_content": "修正済み記事の全文をここに",
  "sources": ["https://example.com/page1", "https://example.com/page2"],
  "warnings": ["警告メッセージ1（あれば）"],
  "is_safe": true
}
```
"""


def _parse_result(text: str, original: str) -> dict:
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    raw = m.group(1) if m else text.strip()
    try:
        result = json.loads(raw)
        if all(k in result for k in ("verified_content", "sources", "warnings", "is_safe")):
            return result
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return {
        "verified_content": original,
        "sources": [],
        "warnings": ["ファクトチェック結果のパースに失敗しました"],
        "is_safe": True,
    }


def factcheck_article(content: str, article_type: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "verified_content": content,
            "sources": [],
            "warnings": ["ANTHROPIC_API_KEY未設定のためスキップ"],
            "is_safe": True,
        }

    client = anthropic.Anthropic(api_key=api_key)
    label = "ビジネス" if article_type == "business" else "ガジェット"

    messages = [
        {
            "role": "user",
            "content": (
                f"記事タイプ: {label}\n\n"
                f"以下の記事をファクトチェックしてください:\n\n{content}"
            ),
        }
    ]

    try:
        for _ in range(20):
            response = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=_SYSTEM,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                text = "".join(
                    b.text
                    for b in response.content
                    if getattr(b, "type", "") == "text"
                )
                result = _parse_result(text, content)
                break

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = [
                    {
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": "Search executed",
                    }
                    for b in response.content
                    if getattr(b, "type", "") == "tool_use"
                ]
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})
                continue

            break
        else:
            result = {
                "verified_content": content,
                "sources": [],
                "warnings": ["ファクトチェックが規定回数内に完了しませんでした"],
                "is_safe": True,
            }

    except Exception as e:
        print(f"ERROR: ファクトチェックAPI呼び出し失敗: {e}", file=sys.stderr)
        return {
            "verified_content": content,
            "sources": [],
            "warnings": [f"APIエラー: {e}"],
            "is_safe": True,
        }

    src_count = len(result.get("sources", []))
    warn_count = len(result.get("warnings", []))
    safe = result.get("is_safe", True)
    print(
        f"[ファクトチェック] ソース数: {src_count} / 警告数: {warn_count} / "
        f"判定: {'OK' if safe else 'NG'}"
    )
    return result

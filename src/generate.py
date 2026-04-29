import argparse
import os
import sys
import re
import json
import base64
import logging
import urllib.request
import urllib.parse
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
- 読者の気持ちに寄り添い、共感を持って語りかける文体にする
- 数値・データは出典を明記するか「〜といわれています」と表現する
- 誇張表現（絶対・必ず・100%・最高）は根拠なく使わない
- デメリット・リスク・注意点も正直に記載する
- 薬機法・景品表示法・著作権を遵守する
- ファクトチェック済みの事実のみ記載する
- 一人の読者に語りかけるように書く"""

_TITLE_TECHNIQUES = """\
- 数字を使う（例：「5つの方法」「月3万円」「3ステップで」）
- 読者の悩みに直接刺さる言葉（例：「なぜ〜できないのか」「〜で失敗しない」）
- 具体的なベネフィット（例：「〜するだけで」「〜が変わる」）
- 疑問形・驚き（例：「知らないと損する」「実は〜だった」）
- 対象読者を明確に（例：「初心者でも」「忙しい人でも」）"""


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

2. **この旅先・旅行術の見どころとベストシーズン**（300字以上）
   - 他にはない魅力・体験できること
   - おすすめの季節・ベストシーズンと避けるべき時期

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

3. **食材・レシピ手順・お店情報・アレンジ**（600字以上・必須）
   - 旬の食材とその選び方・入手方法・アレルギー情報
   - 具体的な調理手順とアレンジバリエーション（レシピの場合）
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
## タイトル生成の指針
以下の技法を組み合わせて、読者がクリックしたくなるタイトルを作成してください：
{_TITLE_TECHNIQUES}

## 記事の要件

### frontmatter（必ずこの形式で出力）
```
---
title: "（上記技法を使った、読者が思わずクリックしたくなる具体的なタイトル）"
description: "（150字以内・記事で得られる価値を具体的に説明）"
pubDate: {today}
tags: {tags_str}
---
```

### 本文構成（合計{MIN_CHARS}字以上・日本語）

{body_sections}

## 会話シーンの挿入（必須）
記事中の自然な箇所に、以下の形式で **1〜2箇所**「読者Aさんと詳しいBさんの会話」を挿入してください。

```
> 💬 **Aさん（読者）**：「○○って実際どうなんですか？難しそうで…」
>
> 💬 **Bさん（詳しい人）**：「確かに最初はとっつきにくいですよね。でも実は○○のコツさえ押さえれば大丈夫です！」
```

- 会話は記事テーマに関連した自然な内容にする
- Aさんは読者が感じる素直な疑問・不安を代弁する
- Bさんは共感しつつ具体的なヒントを答える（断定的すぎない）
- 見出しの直後など、テキストの流れを補完する位置に置く

## SVG図解の挿入（必須）
記事内容を視覚的に説明する **SVG図解を1枚** 生成し、適切な箇所に挿入してください。

### 図解の内容と出典
以下の優先順位でデータ・統計を使って図解を作成してください：
1. **優先1**: 官公庁・省庁（国土交通省・観光庁・総務省・金融庁など）
2. **優先2**: 研究機関・大学・公益法人（JNTO・各種研究所など）
3. **優先3**: 企業の公式レポート・統計データ

### SVG出力形式
```html
<figure style="margin:2rem 0;text-align:center;">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300" style="max-width:100%;height:auto;border-radius:8px;">
  <!-- 図解の内容（棒グラフ・フローチャート・比較表など） -->
  <!-- 背景: #f9fafb、メインカラー: #2563eb、アクセント: #f59e0b -->
  <!-- テキストは日本語、フォントサイズは12px以上 -->
</svg>
<figcaption style="font-size:0.8em;color:#666;margin-top:8px;">
出典：【出典名】（【取得元URL】）/ 【取得・参照年月】
</figcaption>
</figure>
```

## 最重要：記事執筆の姿勢
- **誠実さを最優先**: PVや収益より読者の利益を優先する
- **デメリットも正直に書く**: 良い点だけを誇張しない
- **確認できない数値は柔らかい表現に**: 「〜といわれています」「〜とされています」
- **誇張表現禁止**: 「絶対」「必ず」「100%」「最高」は根拠なく使わない
- **魂のこもった文章**: 一人の読者に語りかけるように書く
- frontmatterから末尾まで完全に出力すること（省略・要約禁止）
"""


def generate_article(client: anthropic.Anthropic, prompt: str, genre: str) -> str:
    import time
    config = GENRE_CONFIG.get(genre, GENRE_CONFIG["business"])
    for attempt in range(3):
        try:
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
        except anthropic.RateLimitError:
            if attempt < 2:
                logger.warning("レートリミット。60秒後にリトライ (%d/3)", attempt + 1)
                time.sleep(60)
            else:
                raise


def supplement_article(client: anthropic.Anthropic, article: str, current_chars: int) -> str:
    import time
    shortage = MIN_CHARS - current_chars
    for attempt in range(3):
        try:
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
        except anthropic.RateLimitError:
            if attempt < 2:
                logger.warning("レートリミット。60秒後にリトライ (%d/3)", attempt + 1)
                time.sleep(60)
            else:
                raise


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


# ── Pixabay 画像取得 ──────────────────────────────────────────

_GENRE_IMAGE_QUERIES = {
    "business": "professional business workspace success",
    "investment": "finance investment growth chart",
    "travel": "travel landscape scenic beautiful",
    "gourmet": "delicious food beautiful plating",
}


def fetch_pixabay_image_urls(query: str, api_key: str, n: int = 3) -> list:
    """Pixabay API から n 枚の画像情報（url, alt）を取得して返す"""
    params = {
        "key": api_key,
        "q": query,
        "image_type": "photo",
        "orientation": "horizontal",
        "safesearch": "true",
        "per_page": max(n, 3),
        "order": "popular",
        "lang": "ja",
    }
    endpoint = "https://pixabay.com/api/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(endpoint, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for hit in data.get("hits", [])[:n]:
            url = hit.get("webformatURL", "")
            if url:
                results.append({
                    "url": url,
                    "alt": hit.get("tags", query).split(",")[0].strip(),
                    "page": hit.get("pageURL", ""),
                })
        logger.info("Pixabay: %d件取得 (query=%s)", len(results), query[:30])
        return results
    except Exception as e:
        logger.warning("Pixabay画像取得失敗 (query=%s): %s", query, e)
        return []


def insert_images_into_article(article: str, images: list) -> str:
    """記事の3箇所（h1直後・中間・まとめ前）に画像を挿入する"""
    if not images:
        return article

    def img_block(img: dict) -> str:
        return (
            f'\n<figure style="margin:1.5rem 0;text-align:center;">'
            f'<img src="{img["url"]}" alt="{img["alt"]}" '
            f'style="width:100%;max-width:800px;height:auto;border-radius:8px;" loading="lazy">'
            f'</figure>\n'
        )

    # frontmatter を除いた body 部分のみ操作
    fm_match = re.match(r'^---\n[\s\S]*?\n---\n', article)
    if fm_match:
        frontmatter = article[:fm_match.end()]
        body = article[fm_match.end():]
    else:
        frontmatter = ""
        body = article

    lines = body.split('\n')

    # 挿入位置を先に全部決めておく（後で逆順に挿入してインデックスズレを防ぐ）
    insertions = []  # (line_index, text)

    # 1枚目: h1 の直後
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith('# ')), -1)
    if h1_idx >= 0 and len(images) >= 1:
        insertions.append((h1_idx + 1, img_block(images[0])))

    # 2枚目: h2 見出しの中間付近
    h2_indices = [i for i, l in enumerate(lines) if re.match(r'^## ', l)]
    if len(h2_indices) >= 2 and len(images) >= 2:
        mid_idx = h2_indices[len(h2_indices) // 2]
        insertions.append((mid_idx, img_block(images[1])))

    # 3枚目: まとめセクションの直前
    matome_idx = next(
        (i for i, l in enumerate(lines) if re.match(r'^##\s+まとめ|^##\s+おわりに|^##\s+最後に', l)),
        -1,
    )
    if matome_idx >= 0 and len(images) >= 3:
        insertions.append((matome_idx, img_block(images[2])))

    # 逆順に挿入（インデックスがズレないように）
    for idx, text in sorted(insertions, key=lambda x: x[0], reverse=True):
        lines.insert(idx, text)

    return frontmatter + '\n'.join(lines)


# ── アフィリエイトリンク ──────────────────────────────────────

# 旅行・グルメ固定アフィリエイトリンク
# ※ リンクURLはA8.net/もしもアフィリエイトの発行IDに差し替えてください
_TRAVEL_LINKS = [
    {"name": "じゃらんnet", "url": "https://www.jalan.net", "desc": "全国の宿・ホテルをお得に予約"},
    {"name": "楽天トラベル", "url": "https://travel.rakuten.co.jp", "desc": "楽天ポイントで宿・航空券をお得に"},
    {"name": "一休.com", "url": "https://www.ikyu.com", "desc": "高級旅館・ホテルの特別プラン"},
    {"name": "Booking.com", "url": "https://www.booking.com", "desc": "世界中の宿を最安値で比較"},
    {"name": "skyticket", "url": "https://skyticket.jp", "desc": "格安航空券・新幹線・ホテル比較"},
]

_GOURMET_LINKS = [
    {"name": "ホットペッパーグルメ", "url": "https://www.hotpepper.jp", "desc": "お得なクーポンでレストラン予約"},
    {"name": "一休.comレストラン", "url": "https://restaurant.ikyu.com", "desc": "高級レストランの特別プラン"},
    {"name": "ふるさと納税（楽天）", "url": "https://www.furusato-tax.jp", "desc": "お取り寄せグルメをふるさと納税で"},
    {"name": "Oisix（オイシックス）", "url": "https://www.oisix.com", "desc": "有機野菜・安心食材のお試しセット"},
]

_BUSINESS_LINKS = [
    {"name": "クラウドワークス", "url": "https://crowdworks.jp", "desc": "副業・フリーランス案件を探す"},
    {"name": "ランサーズ", "url": "https://www.lancers.jp", "desc": "スキルを活かした副業マッチング"},
    {"name": "ストアカ", "url": "https://www.street-academy.com", "desc": "ビジネス・副業スキルを学ぶ"},
    {"name": "Udemy", "url": "https://www.udemy.com/ja/", "desc": "オンライン講座でスキルアップ"},
]

_INVESTMENT_LINKS = [
    {"name": "SBI証券", "url": "https://www.sbisec.co.jp", "desc": "新NISA・つみたて投資ならSBI証券"},
    {"name": "楽天証券", "url": "https://www.rakuten-sec.co.jp", "desc": "楽天ポイントで投資デビュー"},
    {"name": "マネーフォワード ME", "url": "https://moneyforward.com", "desc": "資産・家計を一括管理"},
    {"name": "ウェルスナビ", "url": "https://www.wealthnavi.com", "desc": "おまかせロボアドバイザー投資"},
]

_GADGET_LINKS = [
    {"name": "Amazon", "url": "https://www.amazon.co.jp", "desc": "最新ガジェットをお得に購入"},
    {"name": "ヨドバシカメラ", "url": "https://www.yodobashi.com", "desc": "家電・ガジェットをポイント還元で"},
    {"name": "楽天市場", "url": "https://www.rakuten.co.jp", "desc": "楽天ポイントでお得にショッピング"},
    {"name": "価格.com", "url": "https://kakaku.com", "desc": "最安値・スペック比較で賢く購入"},
]


def fetch_rakuten_products(keyword: str, app_id: str, affiliate_id: str, n: int = 3) -> list:
    """楽天市場商品検索 API でキーワード検索し上位 n 件を返す"""
    # デバッグ: app_idの形式確認（先頭8文字・末尾4文字・長さのみ表示）
    app_id = app_id.strip().replace("-", "")  # ハイフンを除去（UUID対応）
    logger.info("楽天API app_id: 長さ=%d, 先頭=%s..., 末尾=...%s",
                len(app_id), app_id[:8], app_id[-4:])
    # キーワードを20文字以内に短縮（長いと400エラーになる）
    short_kw = keyword[:20]
    params = {
        "applicationId": app_id,
        "affiliateId": affiliate_id,
        "keyword": short_kw,
        "hits": n,
        "sort": "standard",
        "availability": 1,
    }
    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        items = data.get("Items", [])
        results = []
        for item_wrap in items[:n]:
            item = item_wrap.get("Item", item_wrap)
            results.append({
                "name": item.get("itemName", "")[:50],
                "url": item.get("affiliateUrl") or item.get("itemUrl", "#"),
                "price": item.get("itemPrice", 0),
                "image": (item.get("mediumImageUrls") or [{}])[0].get("imageUrl", ""),
            })
        logger.info("楽天API: %d件取得 (keyword=%s)", len(results), short_kw)
        return results
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.warning("楽天API呼び出し失敗 (keyword=%s): HTTP %s: %s", short_kw, e.code, body[:300])
        return []
    except Exception as e:
        logger.warning("楽天API呼び出し失敗 (keyword=%s): %s", short_kw, e)
        return []


def build_affiliate_section(genre: str, keyword: str, products: list) -> str:
    """記事末尾に追加するアフィリエイトリンクセクションのMarkdownを生成"""
    lines = ["\n\n---\n\n## おすすめ商品・サービス\n"]

    # 楽天商品（全ジャンル共通）
    if products:
        lines.append("### 楽天市場のおすすめ商品\n")
        for p in products:
            price_str = f"（税込 {p['price']:,}円〜）" if p.get("price") else ""
            img_html = (
                f'<img src="{p["image"]}" alt="{p["name"]}" '
                f'style="width:80px;height:80px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:8px;">'
                if p.get("image") else ""
            )
            lines.append(
                f'<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:8px 0;'
                f'display:flex;align-items:center;gap:12px;">'
                f'{img_html}'
                f'<div><a href="{p["url"]}" target="_blank" rel="noopener sponsored" '
                f'style="font-weight:bold;color:#bf0000;">{p["name"]}</a>'
                f'<br><span style="color:#666;font-size:0.9em;">{price_str}</span></div>'
                f'</div>\n'
            )

    # ジャンル別固定リンク
    _GENRE_LINK_MAP = {
        "travel":     (_TRAVEL_LINKS,     "旅行の予約・比較サービス"),
        "gourmet":    (_GOURMET_LINKS,    "グルメ・食の関連サービス"),
        "business":   (_BUSINESS_LINKS,   "副業・スキルアップに役立つサービス"),
        "investment": (_INVESTMENT_LINKS, "投資・資産運用に役立つサービス"),
        "gadget":     (_GADGET_LINKS,     "ガジェット購入に役立つサービス"),
    }
    genre_links = []
    if genre in _GENRE_LINK_MAP:
        genre_links, section_title = _GENRE_LINK_MAP[genre]
        lines.append(f"\n### {section_title}\n")

    if genre_links:
        lines.append(
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:1rem 0;">\n'
        )
        for link in genre_links:
            lines.append(
                f'<a href="{link["url"]}" target="_blank" rel="noopener sponsored" '
                f'style="display:block;border:1px solid #e5e7eb;border-radius:8px;padding:14px;'
                f'text-decoration:none;color:inherit;transition:box-shadow 0.2s;" '
                f'onmouseenter="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
                f'onmouseleave="this.style.boxShadow=\'\'">'
                f'<strong style="color:#bf0000;">{link["name"]}</strong><br>'
                f'<span style="font-size:0.85em;color:#555;">{link["desc"]}</span>'
                f'</a>\n'
            )
        lines.append("</div>\n")

    lines.append(
        '\n<p style="font-size:0.8em;color:#999;">'
        "※本記事にはアフィリエイト広告が含まれます。</p>\n"
    )
    return "".join(lines)


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

    try:
        result = gh("PUT", f"contents/{repo_path}", token, body)
        return result["commit"]["sha"]
    except RuntimeError as e:
        if "409" in str(e):
            logger.warning("409 Conflict: %s は既に存在するためスキップします", repo_path)
            return None
        raise


# ── frontmatterパース ─────────────────────────────────────────

def extract_title(content: str) -> str:
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""



def extract_description(content: str) -> str:
    m = re.search(r'^description:\s*["\'\']?(.+?)["\'\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_first_image(content: str) -> str:
    """記事本文から最初の画像URLを取得"""
    m = re.search(r'!\[.*?\]\((https?://[^\)]+)\)', content)
    if m:
        return m.group(1)
    return "https://cdn.pixabay.com/photo/2016/11/29/08/41/apple-1868496_1280.jpg"

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

    # ── Pixabay 画像を記事に挿入 ─────────────────────────────
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    if pixabay_key:
        title_hint = _get(topic, "title", "topic", "keyword")
        img_query = f"{title_hint} {_GENRE_IMAGE_QUERIES.get(genre, genre)}"
        images = fetch_pixabay_image_urls(img_query, pixabay_key, n=3)
        article = insert_images_into_article(article, images)
        logger.info("画像挿入完了: %d枚", len(images))
    else:
        logger.info("PIXABAY_API_KEY 未設定のため画像挿入スキップ")

    from factcheck import factcheck_article
    fc_result = factcheck_article(article, config["article_type"])
    if not fc_result["is_safe"]:
        print("ERROR: ファクトチェック失敗 - 投稿中止", file=sys.stderr)
        sys.exit(1)
    article = fc_result["verified_content"]

    # ── アフィリエイトリンクセクションを追加 ─────────────────
    rakuten_app_id    = os.environ.get("RAKUTEN_APP_ID", "")
    rakuten_aff_id    = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    title_hint = _get(topic, "title", "topic", "keyword")
    # ジャンル別の短い検索キーワード（楽天APIは長いキーワードで400エラーになるため）
    _RAKUTEN_GENRE_KW = {
        "business":   "副業 ビジネス",
        "investment": "投資 資産運用",
        "gadget":     "ガジェット テック",
        "travel":     "旅行グッズ",
        "gourmet":    "グルメ ギフト",
    }
    rakuten_kw = _RAKUTEN_GENRE_KW.get(genre, title_hint[:15])
    if rakuten_app_id and rakuten_aff_id:
        rakuten_products = fetch_rakuten_products(rakuten_kw, rakuten_app_id, rakuten_aff_id, n=3)
    else:
        logger.info("RAKUTEN_APP_ID/AFFILIATE_ID 未設定のため楽天商品取得スキップ")
        rakuten_products = []
    affiliate_section = build_affiliate_section(genre, title_hint, rakuten_products)
    article = article.rstrip() + "\n" + affiliate_section

    repo_path      = f"src/content/blog/{genre}_{date_str}.md"
    commit_message = f"auto: add {genre} article {date_str}"
    commit_sha     = push_file(gh_token, repo_path, article, commit_message)

    if commit_sha is None:
        print(f"スキップ: {repo_path} は既に存在します")
        return

    commit_url = f"https://github.com/{REPO}/commit/{commit_sha}"
    print(commit_url)

    from notify import post_to_x
    post_to_x(
        article_type=config["article_type"],
        title=extract_title(article),
        blog_url=BLOG_URL,
    )
    # ── Pinterest 自動投稿 ───────────────────────────────────
    try:
        from pinterest_post import post_to_pinterest
        post_to_pinterest(
            title=extract_title(article),
            description=extract_description(article),
            link=f"{BLOG_URL}/blog/{genre}_{date_str}/",
            image_url=extract_first_image(article),
            genre=genre,
        )
    except Exception as e:
        print(f"Pinterest投稿スキップ: {e}")



if __name__ == "__main__":
    main()

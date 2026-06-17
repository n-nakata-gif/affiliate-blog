from __future__ import annotations  # Python 3.9 互換（dict | None 型ヒント対応）
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

BLOG_URL = "https://novlify.jp"
REPO = "n-nakata-gif/affiliate-blog"
BRANCH = "main"
MODEL = "claude-sonnet-4-6"
RAKUTEN_ROOM_URL = "https://room.rakuten.co.jp/room_5034e46bc3/"
MIN_CHARS = 3000
TOPICS_PATH       = "data/topics.json"
SUGGESTIONS_PATH  = "data/keyword_suggestions.json"

_COMMON_PRINCIPLES = """\
- 常に最新トレンドを意識し、読者に有益な情報を提供する
- 読者の気持ちに寄り添い、共感を持って語りかける文体にする
- 数値・データは出典を明記するか「〜といわれています」と表現する
- 誇張表現（絶対・必ず・100%・最高・業界No.1・ダントツ・断然有利・必勝・常勝・コスパ最強・日本一・世界一）は根拠なく使わない
- ランキング・比較記事を書く場合は「選定基準（価格・○○・○○で比較）」を冒頭に明記し、1位/2位/3位表記ではなく番号（1・2・3）か「編集部セレクト」形式を使う
- デメリット・リスク・注意点も正直に記載する
- 薬機法・景品表示法・金融商品取引法・著作権を遵守する
- ファクトチェック済みの事実のみ記載する
- 一人の読者に語りかけるように書く
- PR表記は記事冒頭（h1直後）と末尾の両方に必ず記載する（冒頭はシステムが自動挿入）
- 情報の鮮度を示すため「○○年○○月時点の情報です」を本文中に明記する
- 架空の体験談・第三者を装った表現は使わない
- 他社・他商品を不当に貶める表現は使わない
- 商品・サービスの価格を記載する場合は税込み総額表示（例：「○○円（税込）」）とする
- Amazonの商品を紹介する場合は「Amazonのアソシエイトとして、当メディアは適格販売により収入を得ています」の表記がサイトフッターに存在する前提で記事を書く（記事本文では重複記載不要）
- Amazonを「公式サイト」「Amazonが認定した」などと誤認させる表現は使わない
- 楽天市場・楽天トラベル等を紹介する場合、「楽天公式」「楽天認定」「楽天の店舗公式」など楽天グループの公式サイトと誤認させる表現は使わない
- せどり・転売を促進・助長するような表現や内容は記載しない
- 記事本文中にも読者が検索しそうなキーワードを自然に含める
- 記事は「解説」「比較」「レビュー・感想」のいずれかの形式を意識して構成する
- 地名（都道府県・市区町村名）だけを入れ替えた内容の薄い記事は作成しない
- 読者の滞在時間を意識し、見出し・画像・まとめを活用して最後まで読まれる構成にする
- 記事は1000〜3000文字を目安にする（1000文字未満は情報不足、3000文字超は読者が離脱しやすい）
- 「購入前キーワード」を意識して記事を書く（商品を買う前に検索するキーワード例：「○○ おすすめ」「○○ 比較」「○○ 選び方」）。購入後に検索するキーワード（「○○ 使い方」「○○ 設定方法」）は購買につながりにくい
- 記事の書き出し（冒頭200字）は特に丁寧に書き、読者が「この記事を読み続けたい」と思える内容にする
- Amazon商品の価格を記載する場合は「○年○月時点の価格」と明記し、最新価格はAmazonでご確認くださいと添える
- ポイントサイト・ポイ活・せどり・転売を促す内容は記載しない（Amazonアソシエイト規約違反）
- 競合が少ないニッチな切り口・角度で記事テーマを設定する（例：「副業」より「副業 初心者 30代 スマホだけ」）
- 同じテーマでも「初心者向け」「コスト重視」「時間がない人向け」など複数の切り口で展開できる記事を作る
- Googleサジェストや関連検索ワードを活用し、実際に検索されている複合キーワードを取り込む
- 一文一文は短く（目安20〜40文字）書き、文字装飾（太字・マーカー）は本当に重要な箇所だけに絞って使いすぎない
- ターゲット読者を明確に想定し、「その読者が今まさに抱えている具体的な悩み」に正面から答える記事を書く（例：過去の自分、家族・友人など身近な人をイメージする）
- 読者の悩みフェーズを意識する：「不満を感じている」→「解決方法を知りたい」→「おすすめを教えてほしい」の順に購入行動に近づく。最後のフェーズに答える記事が成果につながりやすい
- 商品・サービスの紹介は購入誘導感を出しすぎず、読者が自分で判断できる余白を意識する（デメリット・代替案・注意点を必ず盛り込む）
- 単価が高くても自分が本当におすすめできない商品は紹介しない。テキトーな商品紹介は読者に見抜かれ、信頼を損なう
- E-A-T（専門性・権威性・信頼性）を意識し、情報の根拠・公的データ・専門的な視点を示す表現を入れる
- 他のサイトにない独自の切り口・視点・情報（一次情報）を1つ以上盛り込む
- 記事の冒頭（前半）で読者の悩みへの共感を示し、「この記事は自分のために書かれている」と感じてもらってから情報を届ける
- 商品・サービスの紹介はスペック（機能・成分・仕様）の羅列から始めず、「使うことで悩みがどう解決されるか（購入後の明るい未来）」を先に伝える
- 複数の商品・サービスを紹介する場合は比較表を使って視覚化し、読者が迷わず選べるようにする（選定基準・比較ポイントを明示すること）
- 比較表（Markdownテーブル）の最後の列には「詳細・公式サイト」列を追加し、各サービス・商品の公式サイトや購入ページへのMarkdownリンク `[詳細はこちら](URL)` を記載すること。URLが不明な場合は代表的な検索URLを入れる
- 知名度の低いサービスを紹介する場合は、同ジャンルの比較・まとめ記事を先に作り、その内部リンク先として個別記事を設置する構成にする
- **クレジットカード申込リンクは記事本文に絶対に含めない**（楽天カード・三井住友カード等のカード申込アフィリエイトリンク未提携のため）。ただし**エポスカードはA8.net提携済みのため申込リンク掲載可**。クレジットカードを話題として言及することは可能だが、未提携カードの申込ページへのURLは記載しない
- FAQセクションは `<details><summary>Q. 質問文</summary>A. 回答文</details>` のHTML形式で出力する（GoogleのAIオーバービュー・AIサマリーに引用されやすい構造化マークアップのため）。FAQは5問以上を目標にする
- アフィリエイトリンクへのCTAボタンコピーは「今すぐ申し込む」「絶対おすすめ」のような高圧力表現を避け、「詳細・無料体験はこちら」「まずはチェックしてみてください」「公式サイトで確認する」のような低圧力・自然な誘導にする（クッキー期間90日を活かし、クリックしてもらうことが収益につながる）
- 「無料で登録」「無料で資料請求」「無料で体験・相談」できるサービスは、その点を記事冒頭・比較表・CTAで積極的に強調する（読者の心理ハードルが最も低い成約条件であり、成果発生につながりやすいため）

【AIっぽい文体を避けるための7ルール（必須）】
1. 文末の多様化：「〜です」「〜ます」「〜と思います」が3文以上連続しないようにする。体言止め・問いかけ・短文・「〜でしょうか」など語尾を積極的に混ぜる
2. 具体性の強化：「〜と言われています」「〜と感じる方も多い」などの曖昧表現を避け、数字・状況・場面・感情を使って読者がイメージできる表現にする
3. 反復の禁止：同じ内容を少し言い換えて繰り返すことをしない。「〜で悩む方が多い」→「〜は多くの人が悩むポイントだ」のような言い換え反復は削除する
4. テンポの変化：長い文（60文字超）の後には短い文（20文字以下）を置き、箇条書き→文章→問いかけのようにリズムを変える。均一な文の長さが5文以上続かないようにする
5. 根拠・理由の付加：「おすすめです」「効果があります」で終わらず、必ず「なぜなら〜」「〜だから」「たとえば〜」を添える
6. 主体の明確化：「〜と感じます」→「筆者が実際に試したところ〜」のように誰の体験・意見かを明示し、「〜することが大切です」→「特に〇〇の場合は〜が効いてきます」のように対象を絞る
7. キーワードの分散：同じ単語・表現が3文以内に2回以上出てきたら類語・代名詞・省略で分散する。タイトルのキーワードを本文内で連発しない"""

_TITLE_TECHNIQUES = """\
- **タイトルは全角32文字以内**に収める（超えると検索結果・カード表示が切れる。32文字を超えたらキーワードを削って短くする）
- 複合キーワード（2〜3語）を使い、ニッチな検索ニーズに応えるタイトルにする（例：「副業 初心者 30代」「NISA 積立 少額 始め方」）
- 「購入前キーワード」（おすすめ・比較・選び方・違い・メリット）を優先し、「購入後キーワード」（使い方・設定・トラブル）は避ける
- 数字を使う（例：「5つの方法」「月3万円」「3ステップで」）
- 読者の悩みに直接刺さる言葉（例：「なぜ〜できないのか」「〜で失敗しない」）
- 具体的なベネフィット（例：「〜するだけで」「〜が変わる」）
- 疑問形・驚き（例：「知らないと損する」「実は〜だった」）
- 対象読者を明確に（例：「初心者でも」「忙しい人でも」「30代から始める」）
- 競合が少ないニッチな切り口でタイトルを付ける（例：「副業」×「スマホのみ」×「30代」など複数条件を組み合わせる）"""


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
            "投資・資産運用の記事では以下を厳守してください。\n"
            "【絶対禁止表現】「元本保証」「安全確実」「高利回り」「予想利回り」「必ず儲かる」「絶対儲かる」"
            "「稼げる」「勝てる」「今が買い時」「上昇確実」「失敗させない」「任せて安心」\n"
            "【必須記載】「投資には元本割れのリスクがあります」「投資判断はご自身の責任で行ってください」\n"
            "【必須記載】「最新の税制・制度情報は金融機関・税務署・公式サイトでご確認ください」\n"
            "リスク面の説明はメリットと同等以上の分量で記載し、初心者でも容易に利益が得られる印象を与えないこと。\n"
            "相場の断定的予測（「上がる」「下がる」「今が仕込み時」）は一切書かないこと。",
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
    "gadget": {
        "system": _sys(
            "ガジェット・テックジャンル",
            "ガジェット・テックの記事では、公式情報・スペック・ユーザー口コミをもとに客観的に比較・整理してください。\n"
            "個人の使用感・体験談は書かず、「比較・まとめ・情報記事」として執筆してください。\n"
            "「〜といわれています」「〜という口コミがあります」など情報源を明示した表現を使い、"
            "断定的なレビュー表現（「使ってみた」「買って損した」等）は使わないでください。\n"
            "価格は変動する旨を明記し、最新情報は公式サイトや各販売店でご確認くださいと添えてください。",
        ),
        "default_tags": ["ガジェット", "テック", "比較"],
        "article_type": "gadget",
    },
}

_BODY_SECTIONS = {
    "business": """\
1. **導入**（200字以上）
   - 書き出し冒頭100字：読者が「自分のことだ」と感じる具体的な悩み・状況描写から始める（「〜で悩んでいませんか？」形式）
   - 記事を読むと何がわかるかを明示・具体的な数字でベネフィットを示す

2. **なぜ重要か・背景**（300字以上）
   - 読者がこの情報を必要とする理由・知らないと損する背景

3. **選択肢・方法の比較表**（必須）
   - 主要な副業・サービス・方法を **必ずMarkdownの比較表** で整理すること
   - 比較軸：難易度・収入目安・必要スキル・向いている人・デメリット
   - 表の後に各選択肢の詳細解説（600字以上）

4. **実践のポイントと落とし穴**（300字以上）
   - 初心者がつまずくポイント・デメリット・向いていない人の特徴も正直に

5. **まとめ・次のアクション**（200字以上）
   - 読者タイプ別おすすめ選択肢の結論・最初の一歩を具体的に提示

6. **FAQ**（5問以上・`<details><summary>Q. 質問文</summary>回答文</details>` 形式・各100字以上）
   - 読者のリアルな疑問を「Q. ～ですか？」形式で設定し、詳しく回答する""",

    "investment": """\
※記事冒頭に「※本記事はPRを含みます」「（○○年○○月時点の情報です）」を必ず記載する

1. **導入**（200字以上）
   - 書き出し冒頭100字：読者が「自分のことだ」と感じる具体的な悩みから始める（「〜で迷っていませんか？」形式）
   - 「投資には元本割れのリスクがあります」を冒頭付近に記載

2. **しくみの解説**（300字以上）
   - 仕組みをわかりやすく解説・メリットと同等以上の分量でデメリット・リスクを説明

3. **選択肢・商品の比較表**（必須）
   - 主要な金融商品・サービス・口座を **必ずMarkdownの比較表** で整理すること
   - 比較軸：利回り目安・リスク水準・最低投資額・向いている人・手数料
   - 表の後に各選択肢の詳細解説（600字以上）

4. **具体的な始め方・手順**（400字以上）
   - 口座開設から運用開始まで再現性のあるステップ

5. **リスクと注意事項**（400字以上・必須）
   - 元本割れリスク等を正直に説明
   - 「投資にはリスクがあります。投資判断はご自身の責任で行ってください」を明記

6. **まとめ・読者タイプ別結論**（200字以上）
   - どんな人に向いているかを明示・専門家への相談を推奨
   - 「最新情報は各金融機関・税務署の公式サイトでご確認ください」を記載

7. **FAQ**（5問以上・`<details><summary>Q. 質問文</summary>回答文</details>` 形式・各100字以上）
   - 読者のリアルな疑問を「Q. ～ですか？」形式で設定し、詳しく回答する""",

    "travel": """\
1. **導入**（200字以上）
   - 書き出し冒頭100字：読者が「自分のことだ」と感じる旅の悩み・計画の困りごとから始める（「〜で迷っていませんか？」形式）
   - この記事を読むとわかることを明示する

2. **見どころ・選択肢の比較表**（必須）
   - 旅先・宿・交通手段・プランなど主要な選択肢を **必ずMarkdownの比較表** で整理すること
   - 比較軸：費用目安・特徴・向いている旅行者・所要時間
   - 表の後に各選択肢の詳細解説（300字以上）

3. **アクセス・料金・営業時間**（400字以上・必須）
   - 交通手段と所要時間・費用の目安（宿泊・飲食・入場料）
   - 「〜年〜月時点の情報です。最新情報は公式サイトでご確認ください」を必ず記載

4. **具体的なモデルプラン・楽しみ方**（400字以上）
   - 日程例・おすすめスポットの巡り方・穴場情報

5. **注意点・持ち物・混雑対策**（200字以上）
   - 季節・天候の注意・混雑しやすい時期と避け方

6. **まとめ・読者タイプ別結論**（200字以上）
   - 旅行者タイプ別（ファミリー・カップル・一人旅）のおすすめを明示・背中を押す言葉

7. **FAQ**（5問以上・`<details><summary>Q. 質問文</summary>回答文</details>` 形式・各100字以上）
   - 読者のリアルな疑問を「Q. ～ですか？」形式で設定し、詳しく回答する""",

    "gourmet": """\
1. **導入**（200字以上）
   - 書き出し冒頭100字：読者が「自分のことだ」と感じる食の悩み・選択の困りごとから始める（「〜で迷っていませんか？」形式）
   - この記事でわかることを明示する

2. **商品・サービス・選択肢の比較表**（必須）
   - 紹介する食品・サービス・商品・お店を **必ずMarkdownの比較表** で整理すること
   - 比較軸：価格・特徴・おすすめポイント・向いている人・デメリット
   - 表の後に各選択肢の詳細解説（300字以上）

3. **詳細情報・レシピ・購入方法**（400字以上・必須）
   - 食材の選び方・具体的な手順・お店情報・購入場所
   - 「〜年〜月時点の情報です。価格・営業時間は変動する場合があります」を必ず記載

4. **コスパ・実際の評価・注意点**（300字以上）
   - 正直なレビュー・デメリット・向いていない人の特徴も記載
   - アレルギー情報・保存方法など実用情報

5. **まとめ・読者タイプ別結論**（200字以上）
   - 読者の目的・予算別おすすめを明示・次のアクションを提案

6. **FAQ**（5問以上・`<details><summary>Q. 質問文</summary>回答文</details>` 形式・各100字以上）
   - 読者のリアルな疑問を「Q. ～ですか？」形式で設定し、詳しく回答する""",

    "gadget": """\
1. **導入**（200字以上）
   - 書き出し冒頭100字：「どれを選べばいいかわからない」「失敗したくない」という読者の具体的な悩みから始める（「〜で迷っていませんか？」形式）
   - 記事で何がわかるかを明示（比較ポイント・選び方の基準）

2. **製品カテゴリの概要**（200字以上）
   - カテゴリの特徴・価格帯の目安
   - 「価格は変動します。最新情報は各販売サイトでご確認ください」を明記

3. **主要製品の比較表**（必須）
   - 代表的な製品のスペック・機能・価格帯を **必ずMarkdownの比較表** で整理すること
   - 比較軸：価格・主要機能・向いている人・デメリット・総合評価
   - 公式情報・スペックシートをもとに客観的に記載
   - 表の後に各製品の詳細解説（500字以上）

4. **選び方のポイント・注意点**（300字以上・必須）
   - 用途別の選択基準・よくある失敗例・向いていない人の特徴

5. **予算別・用途別結論**（200字以上）
   - 「コスパ重視」「高機能派」「初心者向け」など読者タイプ別のおすすめを明示した結論

6. **購入方法・価格比較のコツ**（200字以上）
   - Amazon・楽天・ヨドバシ等での価格比較のコツ・セール時期の傾向

7. **まとめ**（200字以上）
   - 選び方の要点整理・読者が次のアクションに移りやすいまとめ

8. **FAQ**（5問以上・`<details><summary>Q. 質問文</summary>回答文</details>` 形式・各100字以上）
   - 読者のリアルな疑問を「Q. ～ですか？」形式で設定し、詳しく回答する""",
}


# ── トピック読み込み ──────────────────────────────────────────

CONTENT_DIR = Path("src/content/blog")

def load_topics() -> list:
    with open(TOPICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_recent_article_titles(genre: str, n: int = 30) -> list[str]:
    """src/content/blog/ から最近の記事タイトルを取得（カニバリ検知用）"""
    titles = []
    if not CONTENT_DIR.exists():
        return titles
    pattern = f"{genre}_*.md"
    files = sorted(CONTENT_DIR.glob(pattern), reverse=True)[:n]
    title_re = re.compile(r'^title:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")[:500]
            m = title_re.search(text)
            if m:
                titles.append(m.group(1).strip())
        except Exception:
            pass
    return titles


def _topic_overlaps_recent(title: str, recent_titles: list[str]) -> bool:
    """トピックタイトルが既存記事と重複するか判定（日本語対応）

    戦略:
    1. タイトルから4文字以上の固有名詞候補を抽出
    2. その語が既存タイトル本文に部分文字列として含まれるか確認
    3. 1語でも一致すれば「重複あり」と判定
    """
    # 汎用語（SEO的には重複カウントしない語）
    generic = {"おすすめ", "比較", "選び方", "解説", "完全", "ガイド", "まとめ", "初心者",
               "向け", "方法", "コツ", "ランキング", "人気", "最新", "2026", "2025",
               "10選", "5選", "7選", "3選", "15選", "20選", "一覧", "入門", "基本"}

    def extract_nouns(t: str) -> list[str]:
        """記号除去後に4文字以上の語句を抽出（スペース区切り＋連続日本語塊）"""
        t = re.sub(r'[【】「」『』（）\[\]・｜—\-：:?？!！、。,.【】]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        chunks = re.split(r'\s+', t)
        nouns = []
        for chunk in chunks:
            if len(chunk) >= 4 and chunk not in generic:
                nouns.append(chunk)
            # 長いチャンクから部分文字列を追加（4〜6文字）
            if len(chunk) >= 6:
                for start in range(0, min(len(chunk) - 3, 8)):
                    sub = chunk[start:start+4]
                    if sub not in generic and not re.match(r'[\d年月]', sub):
                        nouns.append(sub)
        return list(set(nouns))

    cand_nouns = extract_nouns(title)
    for rt in recent_titles:
        for noun in cand_nouns:
            if noun in rt:
                return True
    return False


def load_and_consume_suggestion(genre: str, gh_token: str) -> dict | None:
    """
    keyword_suggestions.json からジャンル一致の提案を1件取り出す。
    取り出した提案はファイルから削除し、GitHub に上書き保存する。
    提案がなければ None を返す。
    """
    path = Path(SUGGESTIONS_PATH)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[keyword_suggest] ファイル読み込み失敗: {e}")
        return None

    theme = None
    for block in data.get("suggestions", []):
        if block.get("genre") == genre and block.get("themes"):
            theme = block["themes"].pop(0)   # 先頭を取り出して削除
            break

    if theme is None:
        return None

    # 使用済みを反映して GitHub に保存
    try:
        push_file(gh_token, SUGGESTIONS_PATH,
                  json.dumps(data, ensure_ascii=False, indent=2),
                  f"chore: consume keyword suggestion [{genre}] [skip ci]")
        print(f"[keyword_suggest] 使用済み提案を削除: {theme.get('title')}")
    except Exception as e:
        print(f"[keyword_suggest] ファイル更新失敗（スキップ）: {e}")

    config = GENRE_CONFIG[genre]
    return {
        "genre":        genre,
        "title":        theme.get("title", ""),
        "tags":         config["default_tags"],
        "summary":      theme.get("reason", ""),
        "key_points":   [],
        "keyword_main": theme.get("target_keyword", ""),
        "keyword_sub":  [],
        "target_reader": "",
        "_source":      "keyword_suggest",
    }


def select_topic(topics: list, date_str: str, genre: str, gh_token: str = "") -> dict:
    # ① キーワード提案を優先（最新のGSCデータに基づくテーマ）
    if gh_token:
        suggestion = load_and_consume_suggestion(genre, gh_token)
        if suggestion:
            recent_titles = _get_recent_article_titles(genre, n=30)
            if recent_titles and _topic_overlaps_recent(suggestion["title"], recent_titles):
                print(f"[anti-cannibalize] キーワード提案が既存記事と重複 → スキップ: {suggestion['title'][:40]}")
            else:
                print(f"[keyword_suggest] テーマ採用: {suggestion['title']}")
                return suggestion

    # ② フォールバック: topics.json（カニバリ検知付き）
    if not topics:
        raise ValueError(f"{TOPICS_PATH} が空です")
    filtered = [t for t in topics if t.get("genre", "business") == genre]
    if not filtered:
        filtered = topics

    recent_titles = _get_recent_article_titles(genre, n=30)
    base_idx = int(date_str) % len(filtered)

    # カニバリ回避: 最大 len(filtered) 回シフトして重複しないトピックを探す
    for offset in range(len(filtered)):
        idx = (base_idx + offset) % len(filtered)
        t = filtered[idx]
        title = t if isinstance(t, str) else t.get("title", "")
        if recent_titles and _topic_overlaps_recent(title, recent_titles):
            print(f"[anti-cannibalize] 類似記事あり・スキップ: {title[:40]}")
            continue
        if isinstance(t, str):
            return {"title": t, "genre": genre, "tags": GENRE_CONFIG[genre]["default_tags"]}
        return t

    # 全トピックが重複 → 最初の候補をそのまま返す（フォールバック）
    print("[anti-cannibalize] 全トピックが重複判定 → 先頭候補で続行")
    t = filtered[base_idx]
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

# ── ジャンル別会話キャラクター ─────────────────────────────────────
# (質問役, 回答役) — 読者が感情移入しやすい具体的なペルソナ
_DIALOGUE_CHARS: dict[str, tuple[str, str]] = {
    "business":   ("まさと（副業を始めたい30代の会社員）",      "ひろ（副業歴5年・本業と掛け持ちで月10万達成）"),
    "investment": ("ゆい（投資デビューしたての専業主婦）",       "けん（個人投資家・運用歴10年・配当生活目標）"),
    "gadget":     ("たける（デジモノ疎いがほしいサラリーマン）", "そら（ガジェットマニアのフリーエンジニア）"),
    "travel":     ("あき（初の国内旅行を計画中のパパ）",        "りえ（年10回以上旅する旅行ブロガー）"),
    "gourmet":    ("のぞみ（食べ歩きが趣味のアラサーOL）",      "しょうた（地元の隠れ名店を知り尽くす常連客）"),
}


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
    char_a, char_b = _DIALOGUE_CHARS.get(genre, _DIALOGUE_CHARS["business"])

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
title: "（上記技法を使った、読者が思わずクリックしたくなる具体的なタイトル。全角32文字以内厳守）"
description: "（150字以内・記事で得られる価値を具体的に説明）"
pubDate: {today}
tags: {tags_str}
---
```

### 本文構成（合計{MIN_CHARS}字以上・日本語）

{body_sections}

## 会話シーンの挿入（必須）
記事中の自然な箇所に、以下の形式で **1〜2箇所** 会話を挿入してください。

```
> 💬 **{char_a}**：「○○って実際どうなんですか？難しそうで…」
>
> 💬 **{char_b}**：「確かに最初はとっつきにくいですよね。でも実は○○のコツさえ押さえれば大丈夫です！」
```

- 会話は記事テーマに関連した自然な内容にする
- {char_a.split('（')[0]}は読者が感じる素直な疑問・不安を代弁する
- {char_b.split('（')[0]}は共感しつつ具体的なヒントを答える（断定的すぎない）
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

## 最重要：この記事の目的と執筆の姿勢
- **記事の目的**: 読者が「どれを選べばいいか迷っている」状態から「自信を持って次のアクションに踏み出せる」状態にする。比較情報・向いている人の明示・具体的な結論が必須
- **比較表は全記事に必須**: 選択肢が複数あるテーマでは、必ずMarkdownの比較表（|列1|列2|形式）を本文に1つ以上入れること
- **誠実さを最優先**: PVや収益より読者の利益を優先する
- **デメリットも正直に書く**: 良い点だけを誇張しない。向いていない人・デメリットを必ず明記
- **確認できない数値は柔らかい表現に**: 「〜といわれています」「〜とされています」
- **誇張表現禁止**: 「絶対」「必ず」「100%」「最高」は根拠なく使わない
- **一人の読者に語りかける**: 「あなた」に向けて書く。大勢に向けた説明文調にしない
- frontmatterから末尾まで完全に出力すること（省略・要約禁止）
"""


def sanitize_article(text: str) -> str:
    """Claude APIが返す記事のfrontmatterを修正する。
    プロンプトのサンプルを真似て ```...``` でfrontmatterを囲んで出力することがあるため除去する。
    例: ```\n---\ntitle: ...\n---\n``` → ---\ntitle: ...\n---
    """
    import re
    # ` ```markdown ` または ` ``` ` でfrontmatterが囲まれている場合を除去
    text = re.sub(r'^```(?:markdown)?\n(---\n)', r'\1', text.strip())
    # frontmatterの閉じ --- の直後にある ``` を除去
    text = re.sub(r'(---\n)```\n', r'\1', text)
    return text


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
            return sanitize_article(response.content[0].text)
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
    "business": "business workspace office professional",
    "investment": "finance money investment growth",
    "travel": "travel landscape nature scenic",
    "gourmet": "food delicious restaurant cooking",
    "gadget": "technology gadget electronics modern",
}


def fetch_pixabay_image_urls(query: str, api_key: str, n: int = 3) -> list:
    """Unsplash API から n 枚の画像情報（url, alt）を取得して返す
    ※ 関数名はPixabayのままだが内部はUnsplashを使用（後方互換性のため）
    Unsplash の画像URLは永続URLのため期限切れなし。
    """
    params = {
        "query": query,
        "per_page": max(n, 3),
        "orientation": "landscape",
        "content_filter": "high",
    }
    endpoint = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(
            endpoint,
            headers={
                "Authorization": f"Client-ID {api_key}",
                "Accept-Version": "v1",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for photo in data.get("results", [])[:n]:
            # Unsplashの永続URL（サイズ指定付き・期限なし）
            url = photo.get("urls", {}).get("regular", "")
            alt = photo.get("alt_description") or photo.get("description") or query
            if url:
                results.append({
                    "url": url,
                    "alt": alt[:50],
                    "page": photo.get("links", {}).get("html", ""),
                })
        logger.info("Unsplash: %d件取得 (query=%s)", len(results), query[:30])
        return results
    except Exception as e:
        logger.warning("Unsplash画像取得失敗 (query=%s): %s", query, e)
        return []


def insert_pr_notice(article: str, date_str: str) -> str:
    """h1直後にPR表記バナーを自動挿入する（冒頭に既にある場合はスキップ）"""
    fm_match = re.match(r'^---\n[\s\S]*?\n---\n', article)
    if fm_match:
        frontmatter = article[:fm_match.end()]
        body = article[fm_match.end():]
    else:
        frontmatter = ""
        body = article

    if 'PR・広告を含みます' in body[:400] or '本記事はPRを含みます' in body[:400]:
        return article

    dt = datetime.strptime(date_str, "%Y%m%d")
    year_month = f"{dt.year}年{dt.month}月"
    pr_block = (
        '\n<div style="background:#fff8e1;border-left:4px solid #f59e0b;'
        'padding:10px 16px;margin:1rem 0;border-radius:0 6px 6px 0;font-size:0.9em;color:#555;">'
        '📢 <strong style="color:#333;">本記事はPR・広告を含みます。</strong>'
        f'（{year_month}時点の情報です）'
        '</div>\n'
    )

    lines = body.split('\n')
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith('# ')), -1)
    if h1_idx >= 0:
        lines.insert(h1_idx + 1, pr_block)
    else:
        # h1がない場合は最初のh2の前に挿入
        h2_idx = next((i for i, l in enumerate(lines) if l.startswith('## ')), -1)
        if h2_idx >= 0:
            lines.insert(h2_idx, pr_block)
        else:
            lines.insert(0, pr_block)

    return frontmatter + '\n'.join(lines)


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
_GF = "https://www.google.com/s2/favicons?domain={}&sz=64"  # Google Favicon helper

# ValueCommerce Yahoo!ショッピング アフィリエイト
_VC_BASE = "https://ck.jp.ap.valuecommerce.com/servlet/referral?sid=3769965&pid=892608337"

def _vc_url(yahoo_url: str) -> str:
    """ValueCommerce MyLink形式でYahoo!ショッピングURLにトラッキングを付与"""
    return _VC_BASE + "&vc_url=" + urllib.parse.quote(yahoo_url, safe="")

_VC_SID = "3769965"

def _vc_prog(pid: str) -> str:
    """ValueCommerce 通常プログラム用トラッキングURL（PID指定）"""
    return f"https://ck.jp.ap.valuecommerce.com/servlet/referral?sid={_VC_SID}&pid={pid}"

_MOSHIMO_AID = "5579374"

def _moshimo(p_id: str) -> str:
    """もしもアフィリエイト トラッキングURL（promotion_id指定）"""
    return f"https://af.moshimo.com/af/c/click?a_id={_MOSHIMO_AID}&p_id={p_id}"

_TRAVEL_LINKS = [
    {"name": "じゃらんnet",         "url": "https://px.a8.net/svt/ejp?a8mat=4B3HQI+DYHVCI+14CS+6C9LD",    "desc": "全国の宿・ホテルをお得に予約",          "logo": _GF.format("jalan.net"),    "a8net": True},
    {"name": "エアトリプラス（航空券＋ホテル）", "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+7FX302+AD2+2NBA8H", "desc": "国内航空券＋ホテルをセットでお得に予約", "logo": _GF.format("airtrip.jp"), "a8net": True},
    {"name": "楽天トラベル",        "url": "https://travel.rakuten.co.jp",                                  "desc": "楽天ポイントで宿・航空券をお得に",      "rakuten": True, "logo": _GF.format("travel.rakuten.co.jp")},
    {"name": "一休.com",            "url": "https://px.a8.net/svt/ejp?a8mat=4B3HQJ+A2L06Q+1OK+6LHDU",    "desc": "高級旅館・ホテルのタイムセールプラン",  "logo": _GF.format("ikyu.com"),     "a8net": True},
    {"name": "agoda",               "url": "https://px.a8.net/svt/ejp?a8mat=4B3HQJ+A36FSI+4X1W+5YRHE",   "desc": "国内・海外ホテルを最大85%OFFで予約",    "logo": _GF.format("agoda.com"),    "a8net": True},
    {"name": "エポスカード",        "url": "https://px.a8.net/svt/ejp?a8mat=4B3GYK+5DHWDU+38L8+BXYE9",   "desc": "年会費永年無料・海外旅行保険が自動付帯", "logo": _GF.format("eposcard.co.jp"), "a8net": True},
    {"name": "Yahoo!ショッピング（旅行グッズ）", "url": _vc_url("https://shopping.yahoo.co.jp/search?p=%E6%97%85%E8%A1%8C+%E3%82%B0%E3%83%83%E3%82%BA"), "desc": "旅行グッズ・スーツケースをお得に",  "logo": _GF.format("shopping.yahoo.co.jp"), "a8net": True},
    {"name": "NAVITIME Travel（新幹線）", "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+7B5M5U+4R8G+BWVTE",  "desc": "新幹線・特急チケットを窓口不要・自宅にお届け", "logo": _GF.format("navitime.co.jp"),   "a8net": True},
    {"name": "スカイレンタカー",       "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+7CXWZ6+2AIA+626XU",  "desc": "沖縄・九州・北海道の格安レンタカー予約",      "logo": _GF.format("skyrentacar.jp"),   "a8net": True},
    {"name": "VELTRA（海外・国内ツアー）", "url": "https://h.accesstrade.net/sp/cc?rk=0100py4y00os2v",        "desc": "世界200都市以上の現地ツアー・体験を予約",      "logo": _GF.format("veltra.com"),       "accesstrade": True},
    {"name": "IHG ホテルズ & リゾーツ",  "url": "https://h.accesstrade.net/sp/cc?rk=0100mmn400os2v",        "desc": "インターコンチネンタル等の高級ホテルを公式最安値で", "logo": _GF.format("ihg.com"),     "accesstrade": True},
    {"name": "アールワイレンタル",        "url": _vc_prog("892618881"),                                       "desc": "リモワ・サムソナビ等の高級スーツケースをレンタル", "logo": _GF.format("ry-rental.com"),   "valuecommerce": True},
    {"name": "ヤフートラベル（JALパック）","url": _vc_prog("892618887"),                                       "desc": "JAL航空券＋宿泊をセットでお得に予約",           "logo": _GF.format("travel.yahoo.co.jp"), "valuecommerce": True},
    {"name": "オリオンツアー",            "url": _vc_prog("892618889"),                                       "desc": "JALで行く格安国内旅行・承認率96%の信頼性",      "logo": _GF.format("orion-tour.co.jp"), "valuecommerce": True},
    {"name": "skyticket",              "url": "https://skyticket.jp",                                         "desc": "格安航空券・新幹線・ホテル比較",               "logo": _GF.format("skyticket.jp")},
]

_GOURMET_LINKS = [
    {"name": "ふるなび（ふるさと納税）",       "url": "https://h.accesstrade.net/sp/cc?rk=0100ob7n00os2v",                                          "desc": "実質負担2,000円で海鮮・肉・果物の返礼品がもらえる", "logo": _GF.format("furunavi.jp"),          "accesstrade": True},
    {"name": "出前館",                        "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+893BN6+5W08+5YRHE",                                   "desc": "日本最大級の加盟店数。今すぐ頼めるフードデリバリー", "logo": _GF.format("demae-can.com"),        "a8net": True},
    {"name": "ホットペッパーグルメ",          "url": "https://www.hotpepper.jp",                                                                    "desc": "お得なクーポンでレストラン予約",                   "logo": _GF.format("hotpepper.jp")},
    {"name": "一休.comレストラン",            "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+81COS2+1OK+NTRMQ",                                    "desc": "最大53%OFF！高級レストランのタイムセール",          "logo": _GF.format("restaurant.ikyu.com"),  "a8net": True},
    {"name": "ヨシケイ（お試しミールキット）", "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+8C2HO2+1QM6+HZAGY",                                   "desc": "栄養士の献立で簡単バランスごはん・5日間お試し",    "logo": _GF.format("yoshikei.co.jp"),       "a8net": True},
    {"name": "宅麺.com",                      "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+82JJZM+2CYM+60OXE",                                   "desc": "有名ラーメン店の味をそのままご自宅にお取り寄せ",   "logo": _GF.format("takumen.com"),          "a8net": True},
    {"name": "ベルーナグルメ",                "url": "https://h.accesstrade.net/sp/cc?rk=0100pm2x00os2v",                                              "desc": "魚介・肉・スイーツなど本格派のお取り寄せグルメ",   "logo": _GF.format("belluna-gourmet.com"), "accesstrade": True},
    {"name": "楽天市場（食品・グルメ）",      "url": "https://search.rakuten.co.jp/search/mall/%E9%A3%9F%E5%93%81+%E3%82%B0%E3%83%AB%E3%83%A1/",   "desc": "楽天ポイントでお得に食品・グルメを購入",           "logo": _GF.format("rakuten.co.jp"),        "rakuten": True},
    {"name": "Yahoo!ショッピング（お取り寄せ）", "url": _vc_url("https://shopping.yahoo.co.jp/search?p=%E3%81%8A%E5%8F%96%E3%82%8A%E5%AF%84%E3%81%9B+%E3%82%B0%E3%83%AB%E3%83%A1"), "desc": "お取り寄せグルメをYahoo!ショッピングで", "logo": _GF.format("shopping.yahoo.co.jp"), "a8net": True},
    {"name": "JTBショッピング（旅のお土産）",  "url": _vc_prog("892618886"),                                   "desc": "全国の旅行お土産・ご当地グルメをお取り寄せ",      "logo": _GF.format("jtbshoppingshop.jp"), "valuecommerce": True},
    {"name": "坂ノ途中（有機野菜定期宅配）",  "url": _vc_prog("892618890"),                                   "desc": "農薬・化学肥料不使用の有機野菜を毎週お届け",      "logo": _GF.format("on-the-slope.com"),  "valuecommerce": True},
    {"name": "Oisix（オイシックス）",         "url": "https://www.oisix.com",                                 "desc": "有機野菜・安心食材のお試しセット",                "logo": _GF.format("oisix.com")},
    {"name": "山内鮮魚店",                    "url": _moshimo("1397"),                                         "desc": "創業60年・リピート率70%以上の海鮮グルメ通販",     "logo": _GF.format("yamauchi-seafood.co.jp"), "moshimo": True},
    {"name": "ローストビーフたわら屋",         "url": _moshimo("785"),                                          "desc": "ギフト・家庭用の絶品ローストビーフ専門店",        "logo": _GF.format("tawara-ya.co.jp"),     "moshimo": True},
    {"name": "saketaku（日本酒定期便）",       "url": _moshimo("1279"),                                         "desc": "プロ厳選の希少な日本酒が毎月届く定期サービス",    "logo": _GF.format("saketaku.com"),        "moshimo": True},
]

_BUSINESS_LINKS = [
    {"name": "Amazon（副業・ビジネス書）",       "url": "https://www.amazon.co.jp/s?k=%E5%89%AF%E6%A5%AD+%E3%83%93%E3%82%B8%E3%83%8D%E3%82%B9&tag=nexigen22-22", "desc": "副業・ビジネス関連書籍をAmazonで",  "logo": _GF.format("amazon.co.jp")},
    {"name": "楽天市場（ビジネス書）",           "url": "https://search.rakuten.co.jp/search/mall/%E3%83%93%E3%82%B8%E3%83%8D%E3%82%B9%E6%9C%AC+%E5%89%AF%E6%A5%AD/", "desc": "楽天ポイントでビジネス書をお得に", "rakuten": True, "logo": _GF.format("rakuten.co.jp")},
    {"name": "ここなら（スキル売買）",           "url": "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+95U5WY+2PEO+OECDE", "desc": "TVCMで話題！スキルを副業で売り買いするなら", "logo": _GF.format("coconala.com"), "a8net": True},
    {"name": "税理士ドットコム",                "url": "https://h.accesstrade.net/sp/cc?rk=0100nplx00os2v", "desc": "全国の税理士を無料で探せる・初回相談無料", "logo": _GF.format("zeiri4.com"), "accesstrade": True},
    {"name": "クラウドワークス",                "url": "https://crowdworks.jp",           "desc": "副業・フリーランス案件を探す",            "logo": _GF.format("crowdworks.jp")},
    {"name": "ランサーズ",                      "url": "https://www.lancers.jp",          "desc": "スキルを活かした副業マッチング",          "logo": _GF.format("lancers.jp")},
    {"name": "ストアカ",                        "url": "https://www.street-academy.com",  "desc": "ビジネス・副業スキルを学ぶ",              "logo": _GF.format("street-academy.com")},
    {"name": "Udemy",                           "url": "https://www.udemy.com/ja/",       "desc": "オンライン講座でスキルアップ",             "logo": _GF.format("udemy.com")},
    {"name": "マネーフォワード クラウド会計",   "url": "https://px.a8.net/svt/ejp?a8mat=4B3HQJ+5YCTU+4JGQ+614CY", "desc": "会計事務所オススメNo.1の会計ソフト",  "logo": _GF.format("moneyforward.com")},
    {"name": "マネーフォワード クラウド確定申告", "url": "https://px.a8.net/svt/ejp?a8mat=4B3HQJ+4620I+4JGQ+BXB8Z", "desc": "確定申告を自動化・ラクに完了",        "logo": _GF.format("moneyforward.com")},
    {"name": "ConoHa WING",                     "url": _moshimo("2312"),                                             "desc": "国内最速・初期費用無料のレンタルサーバー。WordPressも簡単設定", "logo": _GF.format("conoha.jp"),            "moshimo": True},
    {"name": "フジ子さん",                       "url": _moshimo("1472"),                                             "desc": "必要なときだけ頼めるオンラインアシスタント・月額不要",       "logo": _GF.format("fujikoSan.com"),        "moshimo": True},
    {"name": "お名前.com レンタルサーバー",       "url": _moshimo("110"),                                              "desc": "ドメイン取得と一緒に使える定番レンタルサーバー",            "logo": _GF.format("onamae.com"),           "moshimo": True},
    {"name": "ロリポップ!レンタルサーバー",       "url": _moshimo("16"),                                               "desc": "月額99円〜の格安高性能サーバー・WordPressも対応",          "logo": _GF.format("lolipop.jp"),           "moshimo": True},
    {"name": "弥生シリーズ（会計・申告）",        "url": _moshimo("914"),                                              "desc": "青色申告・会計・給与ソフト。1年間無料体験あり",           "logo": _GF.format("yayoi-kk.co.jp"),       "moshimo": True},
]

# 松井証券 iDeCo アフィリエイト（A8.net）
_MATSUI_IDECO_TEXT_URL = "https://px.a8.net/svt/ejp?a8mat=4B3HQF+EFRFW2+3XCC+BXIYQ"
_MATSUI_IDECO_BANNER_HTML = (
    '<div style="text-align:center;margin:1.5rem 0;">'
    '<p style="font-size:0.9rem;font-weight:bold;color:#1a1a1a;margin-bottom:10px;">'
    '💰 iDeCoで節税しながら老後資金を積み立てよう</p>'
    '<a href="https://px.a8.net/svt/ejp?a8mat=4B3HQF+EFRFW2+3XCC+BYT9D" '
    'rel="nofollow sponsored" target="_blank">'
    '<img border="0" width="300" height="250" '
    'alt="松井証券ではじめるiDeCo" loading="lazy" '
    'src="https://www24.a8.net/svt/bgt?aid=260503431873&wid=001&eno=01'
    '&mid=s00000018318002010000&mc=1" style="border-radius:8px;max-width:100%;">'
    '</a>'
    '<img border="0" width="1" height="1" '
    'src="https://www19.a8.net/0.gif?a8mat=4B3HQF+EFRFW2+3XCC+BYT9D" alt="">'
    '</div>'
)

_INVESTMENT_LINKS = [
    {"name": "松井証券 iDeCo",            "url": _MATSUI_IDECO_TEXT_URL,           "desc": "節税しながら老後資金を積み立て。手数料無料のiDeCo",  "logo": _GF.format("matsui.co.jp"),       "a8net": True},
    {"name": "DMM株",                     "url": "https://h.accesstrade.net/sp/cc?rk=0100mkk200os2v", "desc": "国内手数料最安水準・米国株も取引手数料0円のネット証券", "logo": _GF.format("kabu.dmm.com"), "accesstrade": True},
    {"name": "松井証券（株式）",          "url": "https://h.accesstrade.net/sp/cc?rk=01000t2p00os2v", "desc": "1日50万円まで手数料無料・使いやすいスマホアプリ",  "logo": _GF.format("matsui.co.jp"), "accesstrade": True},
    {"name": "マネックス証券",            "url": "https://h.accesstrade.net/sp/cc?rk=0100q1bu00os2v", "desc": "米国株・日本株・NISA対応。業界最低水準の手数料",  "logo": _GF.format("monex.co.jp"),  "accesstrade": True},
    {"name": "Amazon（投資・資産運用書）", "url": "https://www.amazon.co.jp/s?k=%E6%8A%95%E8%B3%87+%E8%B3%87%E7%94%A3%E9%81%8B%E7%94%A8&tag=nexigen22-22", "desc": "投資・お金の本をAmazonで",    "logo": _GF.format("amazon.co.jp")},
    {"name": "SBI証券",                   "url": "https://www.sbisec.co.jp",       "desc": "新NISA・つみたて投資ならSBI証券",           "logo": _GF.format("sbisec.co.jp")},
    {"name": "楽天証券",                  "url": "https://www.rakuten-sec.co.jp",  "desc": "楽天ポイントで投資デビュー",  "rakuten": True, "logo": _GF.format("rakuten-sec.co.jp")},
    {"name": "マネーフォワード ME",       "url": "https://moneyforward.com",       "desc": "資産・家計を一括管理",                       "logo": _GF.format("moneyforward.com")},
    {"name": "ウェルスナビ",              "url": "https://www.wealthnavi.com",     "desc": "おまかせロボアドバイザー投資",               "logo": _GF.format("wealthnavi.com")},
    {"name": "IOSマネーセミナー",         "url": _moshimo("1715"),                 "desc": "初心者向け無料資産形成セミナー・参加報酬あり",  "logo": _GF.format("ios-co.jp"),           "moshimo": True},
]

_GADGET_LINKS = [
    {"name": "Amazon",                        "url": "https://www.amazon.co.jp/?tag=nexigen22-22",   "desc": "最新ガジェットをお得に購入",              "logo": _GF.format("amazon.co.jp")},
    {"name": "Lenovo（レノボ）公式",          "url": _vc_prog("892618885"),                          "desc": "ThinkPad・IdeaPadをカスタマイズして購入", "logo": _GF.format("lenovo.com"),          "valuecommerce": True},
    {"name": "GOM Lab（動画・録画ソフト）",   "url": _vc_prog("892618888"),                          "desc": "GOM Player/GOM Cam等の定番動画ソフト",   "logo": _GF.format("gomlab.com"),          "valuecommerce": True},
    {"name": "Yahoo!ショッピング（ガジェット）", "url": _vc_url("https://shopping.yahoo.co.jp/search?p=%E3%82%AC%E3%82%B8%E3%82%A7%E3%83%83%E3%83%88+%E5%AE%B6%E9%9B%BB"), "desc": "PayPayポイントでお得にガジェット購入", "logo": _GF.format("shopping.yahoo.co.jp"), "a8net": True},
    {"name": "楽天市場（家電・ガジェット）",  "url": "https://search.rakuten.co.jp/search/mall/%E3%82%AC%E3%82%B8%E3%82%A7%E3%83%83%E3%83%88+%E5%AE%B6%E9%9B%BB/", "desc": "楽天ポイントでお得にガジェット購入", "rakuten": True, "logo": _GF.format("rakuten.co.jp")},
    {"name": "ヨドバシカメラ",               "url": "https://www.yodobashi.com",                    "desc": "家電・ガジェットをポイント還元で",        "logo": _GF.format("yodobashi.com")},
    {"name": "価格.com",                     "url": "https://kakaku.com",                           "desc": "最安値・スペック比較で賢く購入",          "logo": _GF.format("kakaku.com")},
    {"name": "ソースネクスト",               "url": _moshimo("1105"),                               "desc": "ZERO・翻訳ソフト等の定番PCソフトが10%以上還元", "logo": _GF.format("sourcenext.com"),      "moshimo": True},
    {"name": "DXRacer（ゲーミングチェア）",  "url": _moshimo("2338"),                               "desc": "プロゲーマー愛用のゲーミングチェア専門ブランド",  "logo": _GF.format("dxracer.com"),         "moshimo": True},
]


def make_rakuten_affiliate_url(url: str, affiliate_id: str, a8mat: str = "") -> str:
    """楽天URLにアフィリエイトトラッキングURLを付与する（A8.net経由）"""
    if not affiliate_id or not url or url.startswith("#"):
        return url
    encoded_url = urllib.parse.quote(url, safe="")
    rakuten_url = f"http://hb.afl.rakuten.co.jp/hgc/{affiliate_id}/?pc={encoded_url}&m={encoded_url}"
    if a8mat:
        encoded_rakuten_url = urllib.parse.quote(rakuten_url, safe="")
        return f"https://rpx.a8.net/svt/ejp?a8mat={urllib.parse.quote(a8mat, safe='')}&rakuten=y&a8ejpredirect={encoded_rakuten_url}"
    return rakuten_url


def generate_rakuten_products(client: anthropic.Anthropic, article_title: str, keyword: str, genre: str, affiliate_id: str, a8mat: str = "") -> list:
    """Claude APIでジャンル関連の楽天商品候補を生成し、アフィリエイトリンクを返す（API不要）"""
    if not affiliate_id:
        return []
    _GENRE_LABEL = {
        "gadget": "ガジェット・家電", "travel": "旅行グッズ・旅行用品",
        "gourmet": "食品・グルメ・調理器具", "business": "ビジネス書・副業ツール",
        "investment": "投資・資産運用の書籍・ツール",
    }
    genre_label = _GENRE_LABEL.get(genre, "関連商品")
    prompt = f"""次のブログ記事に関連する、楽天市場で購入できる具体的な商品を3〜4点提案してください。

記事タイトル: {article_title}
キーワード: {keyword}
ジャンル: {genre_label}

条件:
- 実際に楽天市場で販売されている可能性が高い具体的な商品名
- 記事の内容に直接関連する商品を選ぶ
- 各商品: name（商品名・30文字以内）とdesc（20文字以内の説明）をJSON配列で出力

出力形式（JSONのみ、余分なテキスト不要）:
[
  {{"name": "商品名", "desc": "一言説明"}},
  {{"name": "商品名", "desc": "一言説明"}}
]"""
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        json_match = re.search(r'\[[\s\S]*?\]', text)
        if not json_match:
            return []
        products = json.loads(json_match.group(0))
        results = []
        for p in products[:4]:
            if isinstance(p, dict) and p.get("name"):
                kw_encoded = urllib.parse.quote(str(p["name"]))
                search_url = f"https://search.rakuten.co.jp/search/mall/{kw_encoded}/"
                results.append({
                    "name": str(p["name"]),
                    "url": make_rakuten_affiliate_url(search_url, affiliate_id, a8mat),
                    "desc": str(p.get("desc", "")),
                })
        logger.info("楽天商品候補生成: %d件 (genre=%s)", len(results), genre)
        return results
    except Exception as e:
        logger.warning("楽天商品候補生成失敗（スキップ）: %s", e)
        return []


def generate_amazon_gadget_products(client: anthropic.Anthropic, article_title: str, keyword: str) -> list:
    """Claude APIでガジェット記事に関連するAmazon商品候補を生成し、アフィリエイトリンクを返す"""
    prompt = f"""次のガジェット・テック記事に関連する、Amazonで購入できる具体的な商品を3〜4点提案してください。

記事タイトル: {article_title}
キーワード: {keyword}

条件:
- 実際にAmazonで販売されている可能性が高い具体的な商品名（ブランド名+商品名 or カテゴリ）
- 記事の内容に直接関連する商品を選ぶ
- 各商品: name（商品名）とdesc（30文字以内の一言説明）をJSON配列で出力

出力形式（JSONのみ、余分なテキスト不要）:
[
  {{"name": "商品名", "desc": "一言説明"}},
  {{"name": "商品名", "desc": "一言説明"}}
]"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        json_match = re.search(r'\[[\s\S]*?\]', text)
        if not json_match:
            logger.warning("Amazon商品候補: JSON未検出")
            return []
        products = json.loads(json_match.group(0))
        results = []
        for p in products[:4]:
            if isinstance(p, dict) and p.get("name"):
                kw_encoded = urllib.parse.quote(str(p["name"]))
                results.append({
                    "name": str(p["name"]),
                    "url": f"https://www.amazon.co.jp/s?k={kw_encoded}&tag=nexigen22-22",
                    "desc": str(p.get("desc", "")),
                })
        logger.info("Amazon商品候補生成: %d件", len(results))
        return results
    except Exception as e:
        logger.warning("Amazon商品候補生成失敗（スキップ）: %s", e)
        return []


def fetch_rakuten_products(keyword: str, app_id: str, affiliate_id: str, n: int = 3) -> list:
    """楽天市場商品検索 API でキーワード検索し上位 n 件を返す"""
    # デバッグ: app_idの形式確認（先頭8文字・末尾4文字・長さのみ表示）
    app_id = app_id.strip()  # UUID形式のままハイフン維持
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


def enrich_products_with_images(products: list, app_id: str, affiliate_id: str) -> list:
    """Claude生成商品リストに楽天APIで画像URL・実商品URLを付加する"""
    if not app_id or not products:
        return products
    enriched = []
    for p in products:
        try:
            results = fetch_rakuten_products(p["name"], app_id, affiliate_id, n=1)
            p_copy = dict(p)
            if results:
                r = results[0]
                if r.get("image"):
                    p_copy["image"] = r["image"]
                # 実際の商品URLがあれば置き換える（アフィリエイトID付き）
                if r.get("url") and r["url"] != "#":
                    p_copy["url"] = r["url"]
            enriched.append(p_copy)
        except Exception:
            enriched.append(p)
    return enriched


def build_affiliate_section(genre: str, keyword: str, products: list, amazon_products: list = None, rakuten_aff_id: str = "", rakuten_products: list = None, a8mat: str = "") -> str:
    """記事末尾に追加するアフィリエイトリンクセクションのMarkdownを生成"""
    lines = ['\n\n<div id="affiliate-section"></div>\n\n---\n\n## おすすめ商品・サービス\n']

    # 楽天市場 Claude生成商品リンク（全ジャンル共通）
    if rakuten_products:
        lines.append("### 楽天市場で探す\n")
        lines.append(
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:1rem 0;">\n'
        )
        for p in rakuten_products:
            img_html = (
                f'<img src="{p["image"]}" alt="{p["name"]}" '
                f'style="width:100%;height:130px;object-fit:contain;border-radius:4px;'
                f'margin-bottom:8px;background:#f9f9f9;">'
                if p.get("image") else
                '<div style="width:100%;height:80px;background:#fff1f1;border-radius:4px;'
                'margin-bottom:8px;display:flex;align-items:center;justify-content:center;'
                'font-size:2rem;">🛍️</div>'
            )
            lines.append(
                f'<a href="{p["url"]}" target="_blank" rel="noopener sponsored" '
                f'style="display:block;border:2px solid #bf0000;border-radius:8px;padding:12px;'
                f'text-decoration:none;color:inherit;transition:box-shadow 0.2s;" '
                f'onmouseenter="this.style.boxShadow=\'0 4px 12px rgba(191,0,0,0.2)\'" '
                f'onmouseleave="this.style.boxShadow=\'\'">'
                f'{img_html}'
                f'<strong style="color:#bf0000;font-size:0.9em;">{p["name"]}</strong><br>'
                f'<span style="font-size:0.8em;color:#555;">{p["desc"]}</span>'
                f'</a>\n'
            )
        lines.append("</div>\n")

    # Amazon個別商品リンク（ガジェットジャンル用）
    if amazon_products:
        lines.append("### Amazonで探す\n")
        lines.append(
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:1rem 0;">\n'
        )
        for p in amazon_products:
            lines.append(
                f'<a href="{p["url"]}" target="_blank" rel="noopener sponsored" '
                f'style="display:block;border:2px solid #FF9900;border-radius:8px;padding:14px;'
                f'text-decoration:none;color:inherit;transition:box-shadow 0.2s;" '
                f'onmouseenter="this.style.boxShadow=\'0 4px 12px rgba(255,153,0,0.3)\'" '
                f'onmouseleave="this.style.boxShadow=\'\'">'
                f'<strong style="color:#FF9900;">🛒 {p["name"]}</strong><br>'
                f'<span style="font-size:0.85em;color:#555;">{p["desc"]}</span>'
                f'</a>\n'
            )
        lines.append("</div>\n")

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
            url = link["url"]
            if link.get("rakuten") and rakuten_aff_id:
                url = make_rakuten_affiliate_url(url, rakuten_aff_id, a8mat)
            # rel="sponsored" は実際にアフィリエイト提携済みのリンクのみに付与
            is_affiliate = link.get("rakuten") or link.get("a8net") or link.get("accesstrade") or link.get("valuecommerce") or link.get("moshimo") or "tag=nexigen22-22" in url or "px.a8.net" in url or "h.accesstrade.net" in url or "valuecommerce.com" in url or "af.moshimo.com" in url
            rel = "noopener sponsored" if is_affiliate else "noopener"
            logo = link.get("logo", "")
            logo_html = (
                f'<img src="{logo}" width="28" height="28" alt="" loading="lazy" '
                f'style="object-fit:contain;border-radius:4px;flex-shrink:0;" '
                f'onerror="this.style.display=\'none\'">'
            ) if logo else ""
            lines.append(
                f'<a href="{url}" target="_blank" rel="{rel}" '
                f'style="display:block;border:1px solid #e5e7eb;border-radius:8px;padding:14px;'
                f'text-decoration:none;color:inherit;transition:box-shadow 0.2s;" '
                f'onmouseenter="this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.1)\'" '
                f'onmouseleave="this.style.boxShadow=\'\'">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                f'{logo_html}'
                f'<strong style="color:#bf0000;font-size:0.95em;">{link["name"]}</strong>'
                f'</div>'
                f'<span style="font-size:0.82em;color:#666;line-height:1.4;">{link["desc"]}</span>'
                f'</a>\n'
            )
        lines.append("</div>\n")

    # 投資記事：松井証券iDeCoバナー
    if genre == "investment":
        lines.append(_MATSUI_IDECO_BANNER_HTML + "\n")

    # アフィリエイトセクション先頭にアンカーIDを追加済み（上部で設定）
    # 直接遷移CTAボタン（2ボタン構成）
    lines.append(
        f'\n<div style="text-align:center;margin:2rem 0 1rem;">'
        f'<a href="#affiliate-section" '
        f'style="display:inline-block;background:linear-gradient(135deg,#FF9900,#e68000);color:#fff;padding:12px 28px;'
        f'border-radius:8px;text-decoration:none;font-weight:bold;font-size:1rem;'
        f'box-shadow:0 2px 8px rgba(255,153,0,0.3);margin:4px;">'
        f'🛒 この記事で紹介した商品を見る →</a>'
        f'<a href="{RAKUTEN_ROOM_URL}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background:#bf0000;color:#fff;padding:12px 24px;'
        f'border-radius:8px;text-decoration:none;font-weight:bold;font-size:0.9rem;'
        f'box-shadow:0 2px 8px rgba(191,0,0,0.25);margin:4px;">'
        f'📱 楽天ROOMでもチェック</a>'
        f'</div>\n'
    )

    lines.append(
        '\n<p style="font-size:0.8em;color:#999;">'
        "※本記事にはアフィリエイト広告が含まれます。</p>\n"
    )
    return "".join(lines)


# ジャンル別の記事中盤Amazon検索URL
_MIDPOINT_AMAZON_URLS = {
    "gadget":     "https://www.amazon.co.jp/?tag=nexigen22-22",
    "business":   "https://www.amazon.co.jp/s?k=%E5%89%AF%E6%A5%AD+%E3%83%93%E3%82%B8%E3%83%8D%E3%82%B9%E6%9C%AC&tag=nexigen22-22",
    "investment": "https://www.amazon.co.jp/s?k=%E6%8A%95%E8%B3%87+%E8%B3%87%E7%94%A3%E9%81%8B%E7%94%A8&tag=nexigen22-22",
    "travel":     "https://www.amazon.co.jp/s?k=%E6%97%85%E8%A1%8C+%E3%82%B0%E3%83%83%E3%82%BA&tag=nexigen22-22",
    "gourmet":    "https://www.amazon.co.jp/s?k=%E3%82%B0%E3%83%AB%E3%83%A1+%E9%A3%9F%E5%93%81&tag=nexigen22-22",
}

# ジャンル別の記事中盤楽天検索URL（エンコード済み）
_MIDPOINT_RAKUTEN_URLS = {
    "gadget":     "https://search.rakuten.co.jp/search/mall/%E3%82%AC%E3%82%B8%E3%82%A7%E3%83%83%E3%83%88+%E5%AE%B6%E9%9B%BB/",
    "business":   "https://search.rakuten.co.jp/search/mall/%E3%83%93%E3%82%B8%E3%83%8D%E3%82%B9%E6%9C%AC+%E5%89%AF%E6%A5%AD/",
    "investment": "https://search.rakuten.co.jp/search/mall/%E6%8A%95%E8%B3%87+%E8%B3%87%E7%94%A3%E9%81%8B%E7%94%A8/",
    "travel":     "https://search.rakuten.co.jp/search/mall/%E6%97%85%E8%A1%8C%E3%82%B0%E3%83%83%E3%82%BA/",
    "gourmet":    "https://search.rakuten.co.jp/search/mall/%E9%A3%9F%E5%93%81+%E3%82%B0%E3%83%AB%E3%83%A1/",
}

# ジャンル別の記事中盤CTAラベル
_MIDPOINT_LABELS = {
    "gadget":     "この記事で紹介したガジェットをチェック",
    "business":   "副業・スキルアップに役立つ本・サービスをチェック",
    "investment": "投資・資産運用の参考書・ツールをチェック",
    "travel":     "旅行グッズ・旅行サービスをチェック",
    "gourmet":    "グルメ・食品をチェック",
}


# タグからAmazon/楽天の商品検索キーワードを取り出す際に無視する汎用語
_MIDPOINT_GENERIC_TAGS = {
    "ガジェット", "家電", "テック", "テクノロジー", "比較", "グルメ", "食べ物", "食品",
    "グルメスポット", "健康", "フィットネス", "ダイエット", "女性", "男性", "在宅ワーク",
    "腰痛対策", "防水", "アウトドア", "キャンプ", "東京グルメ", "記念日ディナー",
    "高級レストラン", "レストラン", "旅行", "観光", "旅", "国内旅行", "旅行先", "投資",
    "資産運用", "NISA", "ビジネス", "副業", "会社員", "フリーランス", "住民税", "確定申告",
    "スキルアップ", "お金", "節約", "テレワーク", "料理", "レシピ", "贈り物", "ギフト",
}


def _midpoint_product_keyword(genre: str, tags: list | None) -> str | None:
    """gadget/gourmet記事で、タグから具体的な商品検索キーワードを返す（無ければNone）"""
    if genre not in ("gadget", "gourmet") or not tags:
        return None
    for t in tags:
        t = (t or "").strip()
        if t and t not in _MIDPOINT_GENERIC_TAGS:
            return t
    return None


def build_midpoint_cta(genre: str, rakuten_aff_id: str = "", a8mat: str = "", tags: list | None = None) -> str:
    """記事中盤（H2見出し後）に挿入するAmazon+楽天の両リンクCTAブロックを生成。
    gadget/gourmetはタグから商品名を抽出し、テーマ一致の検索リンクにする（成約率向上）。"""
    pkw = _midpoint_product_keyword(genre, tags)
    if pkw:
        enc = urllib.parse.quote(pkw)
        amazon_url = f"https://www.amazon.co.jp/s?k={enc}&tag=nexigen22-22"
        rakuten_raw_url = f"https://search.rakuten.co.jp/search/mall/{enc}/"
        label = f"「{pkw}」をAmazon・楽天でチェック"
    else:
        amazon_url = _MIDPOINT_AMAZON_URLS.get(genre, "https://www.amazon.co.jp/?tag=nexigen22-22")
        rakuten_raw_url = _MIDPOINT_RAKUTEN_URLS.get(genre, "https://www.rakuten.co.jp/")
        label = _MIDPOINT_LABELS.get(genre, "この記事で紹介した商品をチェック")

    # 楽天URLにアフィリエイトトラッキングを付与
    rakuten_url = make_rakuten_affiliate_url(rakuten_raw_url, rakuten_aff_id, a8mat) if rakuten_aff_id else rakuten_raw_url

    return (
        f'\n<div style="background:linear-gradient(135deg,#fffbeb,#fff8f0);'
        f'border:2px solid #FF9900;border-radius:12px;padding:18px 20px;'
        f'margin:1.5rem 0;text-align:center;">\n'
        f'<p style="font-size:0.88rem;font-weight:bold;color:#555;margin:0 0 12px;">📦 {label}</p>\n'
        f'<div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">\n'
        f'<a href="{amazon_url}" target="_blank" rel="noopener sponsored" '
        f'style="display:inline-flex;align-items:center;gap:6px;background:#FF9900;color:#fff;'
        f'padding:11px 22px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:0.9rem;'
        f'box-shadow:0 2px 8px rgba(255,153,0,0.3);">'
        f'🛒 Amazonで見る</a>\n'
        f'<a href="{rakuten_url}" target="_blank" rel="noopener sponsored" '
        f'style="display:inline-flex;align-items:center;gap:6px;background:#bf0000;color:#fff;'
        f'padding:11px 22px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:0.9rem;'
        f'box-shadow:0 2px 8px rgba(191,0,0,0.3);">'
        f'🛍️ 楽天市場で見る</a>\n'
        f'</div>\n'
        f'</div>\n'
    )


# ── 検索意図マッチCTA（ジャンル×タイトル文脈で高単価サービスへ誘導）──────
# トラフィック上位記事の手動改善（2026-06）で効果検証中の型を新記事に自動適用する。
# 文脈に合わない記事には入れない（ミスマッチCTAは信頼を損なうため空文字を返す）。

def _intent_cta_box(headline: str, sub: str, btn_text: str, btn_url: str,
                    color: str, sub_link: str = "") -> str:
    return (
        f'\n<div style="background:linear-gradient(135deg,#fdf9f4,#fefcf9);'
        f'border:2px solid {color};border-radius:12px;padding:20px 22px;'
        f'margin:1.8rem 0;text-align:center;">\n'
        f'<p style="font-size:1rem;font-weight:bold;color:#444;margin:0 0 6px;">{headline}</p>\n'
        f'<p style="font-size:0.85rem;color:#666;margin:0 0 14px;">{sub}</p>\n'
        f'<a href="{btn_url}" target="_blank" rel="noopener sponsored" '
        f'style="display:inline-block;background:{color};color:#fff;padding:13px 30px;'
        f'border-radius:8px;text-decoration:none;font-weight:bold;font-size:0.95rem;'
        f'box-shadow:0 2px 10px rgba(0,0,0,0.18);">{btn_text}</a>\n'
        + (f'<p style="font-size:0.78rem;color:#888;margin:12px 0 0;">{sub_link}</p>\n' if sub_link else '')
        + '</div>\n'
    )


def build_intent_cta(genre: str, title: str) -> str:
    """記事タイトルの文脈に合う高単価サービスCTAを返す。合うものが無ければ空文字。"""
    t = title or ""

    if genre == "travel":
        # 旅行記事はほぼ全てが「宿予約」に接続できる
        return _intent_cta_box(
            "🏨 行き先が決まったら、宿の相場だけ先にチェック",
            "人気シーズンの宿は2〜3ヶ月前から埋まり始めます。じゃらんなら「エリア×日付」で空室と料金を一覧比較でき、クーポン配布も頻繁です。",
            "じゃらんで宿の空きを見てみる →",
            "https://px.a8.net/svt/ejp?a8mat=4B3HQI+DYHVCI+14CS+6C9LD",
            "#ff8c00",
            sub_link='記念日や高級旅館狙いなら <a href="https://px.a8.net/svt/ejp?a8mat=4B3HQJ+A2L06Q+1OK+6LHDU" target="_blank" rel="noopener sponsored" style="color:#2e7d52;text-decoration:underline;">一休.com（タイムセールで最大半額）</a> も比較を',
        )

    if genre == "gourmet" and re.search(r"レストラン|ディナー|ランチ|グルメスポット|外食|名店|記念日|デート", t):
        return _intent_cta_box(
            "🍽️ お店選びは「総額が分かるコース予約」が安心です",
            "一休.comレストランなら席料・サービス料込みの総額表示でコースを比較できます。タイムセールで最大53%OFFになることも。",
            "一休.comレストランでコースを見てみる →",
            "https://px.a8.net/svt/ejp?a8mat=4B3UZ9+81COS2+1OK+NTRMQ",
            "#b08d57",
        )

    if genre == "business" and re.search(r"確定申告|税金|住民税|経費|インボイス|青色|白色|フリーランス|開業", t):
        return _intent_cta_box(
            "📝 申告ミスが不安なら、ソフトに任せるのが確実です",
            "マネーフォワード クラウド確定申告なら、質問に答えるだけで申告書が完成。経費集計もレシート撮影でラクになります。<strong>無料で試せます。</strong>",
            "マネーフォワード確定申告を無料で試す →",
            "https://px.a8.net/svt/ejp?a8mat=4B3HQJ+4620I+4JGQ+BXB8Z",
            "#2c7be5",
            sub_link='複雑なケースは <a href="https://h.accesstrade.net/sp/cc?rk=0100nplx00os2v" target="_blank" rel="noopener sponsored" style="color:#2c5f8a;text-decoration:underline;">税理士ドットコム（無料で税理士を紹介）</a> への相談も',
        )

    if genre == "business" and re.search(r"ブログ|WordPress|サーバー|アフィリエイト", t):
        return _intent_cta_box(
            "🚀 ブログを始めるならサーバー選びが最初の一歩",
            "ConoHa WINGは国内最速クラス・初期費用無料。WordPressのインストールも管理画面から数クリックで完了します。",
            "ConoHa WINGの料金を見てみる →",
            "https://af.moshimo.com/af/c/click?a_id=5579374&p_id=2312",
            "#26a69a",
        )

    return ""


def insert_intent_cta(article: str, cta_block: str) -> str:
    """「まとめ」見出しの直前に検索意図CTAを挿入。まとめが無ければFAQの直前。"""
    if not cta_block:
        return article
    m = re.search(r'\n## (?:まとめ|FAQ)', article)
    if not m:
        return article
    pos = m.start()
    return article[:pos] + '\n' + cta_block + article[pos:]


def insert_midpoint_cta(article: str, cta_block: str) -> str:
    """記事本文の2番目のH2見出しの後にCTAブロックを挿入する"""
    # frontmatterの終端を探す（--- で囲まれた部分）
    fm_match = re.search(r'^---\n[\s\S]*?\n---\n', article)
    if not fm_match:
        return article
    body_start = fm_match.end()
    body = article[body_start:]

    # H2見出しの位置を全て取得
    h2_positions = [m.start() for m in re.finditer(r'\n## ', body)]

    if len(h2_positions) < 2:
        # H2が2つ未満なら挿入しない
        return article

    # 3番目のH2の直前（なければ末尾の20%地点）に挿入
    if len(h2_positions) >= 3:
        insert_pos = h2_positions[2]
    else:
        insert_pos = h2_positions[-1]

    # CTAブロック挿入
    body = body[:insert_pos] + '\n' + cta_block + body[insert_pos:]
    return article[:body_start] + body


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


def push_binary_file(token: str, repo_path: str, data: bytes, commit_message: str) -> str | None:
    """バイナリファイル（画像等）を GitHub にプッシュする"""
    encoded = base64.b64encode(data).decode("ascii")
    try:
        existing = gh("GET", f"contents/{repo_path}?ref={BRANCH}", token)
        sha = existing.get("sha")
    except RuntimeError as e:
        if "404" in str(e):
            sha = None
        else:
            raise

    body: dict = {"message": commit_message, "content": encoded, "branch": BRANCH}
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


# ── 内部リンク ────────────────────────────────────────────────

# ジャンル別のファイル名パターン（generate.pyと同定義）
_INTERNAL_LINK_GENRE_PATTERNS = {
    "travel":     ["travel"],
    "gourmet":    ["gourmet"],
    "investment": ["investment"],
    "business":   ["business"],
    "gadget":     ["gadget", "product"],
}

INTERNAL_LINK_MARKER = "## あわせて読みたい"


def has_internal_links(content: str) -> bool:
    return INTERNAL_LINK_MARKER in content


def find_related_articles(genre: str, current_slug: str, n: int = 5) -> list:
    """同ジャンルの記事から関連記事を返す（新しい順）。(slug, title) のリスト。
    同ジャンルで不足する場合は他ジャンルの記事も補完する。"""
    blog_dir = Path("src/content/blog")
    patterns = _INTERNAL_LINK_GENRE_PATTERNS.get(genre, [genre])
    related = []
    seen_slugs = set()

    # まず同ジャンルを探す
    for md_file in sorted(blog_dir.glob("*.md"), reverse=True):
        slug = md_file.stem
        if slug == current_slug or slug in seen_slugs:
            continue
        if not re.search(r'_20\d{6}\.md$', md_file.name):
            continue
        name_lower = md_file.name.lower()
        if not any(p in name_lower for p in patterns):
            continue
        try:
            title = extract_title(md_file.read_text(encoding="utf-8"))
            if title:
                related.append((slug, title))
                seen_slugs.add(slug)
        except Exception:
            continue
        if len(related) >= n:
            break

    # 同ジャンルで不足する場合は他ジャンルで補完
    if len(related) < n:
        for md_file in sorted(blog_dir.glob("*.md"), reverse=True):
            slug = md_file.stem
            if slug == current_slug or slug in seen_slugs:
                continue
            if not re.search(r'_20\d{6}\.md$', md_file.name):
                continue
            try:
                title = extract_title(md_file.read_text(encoding="utf-8"))
                if title:
                    related.append((slug, title))
                    seen_slugs.add(slug)
            except Exception:
                continue
            if len(related) >= n:
                break

    return related


def build_internal_links_section(related: list) -> str:
    """内部リンクセクションのMarkdownを生成"""
    if not related:
        return ""
    lines = ["\n\n## あわせて読みたい\n"]
    for slug, title in related:
        url = f"{BLOG_URL}/blog/{slug}/"
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines)


def strip_internal_links_section(content: str) -> str:
    """既存の内部リンクセクションを除去（force更新用）"""
    marker = "\n\n## あわせて読みたい"
    idx = content.find(marker)
    if idx == -1:
        return content
    # アフィリエイトセクションの手前まで除去
    aff_marker = "\n\n---\n\n## おすすめ商品・サービス"
    aff_idx = content.find(aff_marker, idx)
    if aff_idx != -1:
        return content[:idx] + content[aff_idx:]
    return content[:idx]


# ── 編集者コメント ────────────────────────────────────────────

_EDITOR_NOTE_PROMPT = """\
次のブログ記事を書いた「Nori（のり）」のひとこと感想を生成してください。

【条件】
- 50〜100文字の1〜2文
- 一人称は「私」
- 記事テーマに関連した具体的な気づきや体験談を1つ含める（化学系会社員・妻と子供3人の5人家族という背景でOK）
- 親しみやすい「です・ます」調
- 宣伝・まとめではなく、素直な感想や共感
- 出力は感想文の本文のみ（記号・見出し不要）

【記事タイトル】
{title}

【ジャンル】
{genre_label}
"""

_GENRE_LABELS = {
    "business":   "副業・ビジネス",
    "investment": "投資・資産運用",
    "travel":     "旅行・観光",
    "gourmet":    "グルメ・食",
    "gadget":     "ガジェット・テック",
}


def build_editor_note(note_text: str) -> str:
    """Noriのひとことセクションのmarkdownを生成"""
    return (
        "\n\n---\n\n"
        "> 📝 **Noriのひとこと**  \n"
        f"> {note_text}  \n"
        ">  \n"
        "> — Nori（Novlify 編集者）\n"
    )


def generate_editor_note(client, title: str, genre: str) -> str:
    """Claude APIでNoriのひとこと感想を生成する"""
    genre_label = _GENRE_LABELS.get(genre, genre)
    prompt = _EDITOR_NOTE_PROMPT.format(title=title, genre_label=genre_label)
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        note_text = resp.content[0].text.strip()
        logger.info("編集者コメント生成完了: %s...", note_text[:30])
        return note_text
    except Exception as e:
        logger.warning("編集者コメント生成失敗（スキップ）: %s", e)
        return ""


def has_editor_note(content: str) -> bool:
    """記事に編集者コメントが既に含まれているか確認"""
    return "Noriのひとこと" in content


# ── 楽天ROOM 投稿ドラフト生成 ─────────────────────────────────

_ROOM_GENRE_LABELS = {
    "gadget":     "ガジェット",
    "travel":     "旅行",
    "gourmet":    "グルメ",
    "business":   "副業・ビジネス",
    "investment": "投資",
}

_ROOM_GENRE_HASHTAGS = {
    "gadget":     ["#楽天ROOM", "#楽天市場", "#ガジェット", "#家電", "#テック"],
    "travel":     ["#楽天ROOM", "#楽天市場", "#旅行", "#旅行グッズ", "#国内旅行"],
    "gourmet":    ["#楽天ROOM", "#楽天市場", "#グルメ", "#食品", "#おすすめ食品"],
    "business":   ["#楽天ROOM", "#楽天市場", "#副業", "#ビジネス書", "#スキルアップ"],
    "investment": ["#楽天ROOM", "#楽天市場", "#投資", "#資産運用", "#お金の勉強"],
}


def generate_room_posts_content(
    client: anthropic.Anthropic,
    article_title: str,
    article_url: str,
    keyword: str,
    genre: str,
    rakuten_aff_id: str = "",   # 省略可（ドラフト生成自体には不要）
    n: int = 3,
) -> list:
    """Claude APIで楽天ROOM投稿ドラフトを生成する（公式APIなし・手動投稿補助用）
    ※ RAKUTEN_AFFILIATE_ID は不要。Claude API のみで生成します。
    """

    genre_label = _ROOM_GENRE_LABELS.get(genre, genre)
    default_tags = " ".join(_ROOM_GENRE_HASHTAGS.get(genre, ["#楽天ROOM", "#楽天市場"]))

    prompt = f"""次のブログ記事に合わせた「楽天ROOM」への投稿ドラフトを{n}件生成してください。

記事タイトル: {article_title}
ブログURL: {article_url}
キーワード: {keyword}
ジャンル: {genre_label}

楽天ROOMとは「楽天市場の商品をSNS感覚で紹介するサービス」です。
投稿するには「楽天市場の商品URL + コメント」が必要です。

各投稿ドラフトに含める情報:
1. product_keyword: 楽天市場で検索する商品のキーワード（15文字以内・具体的な商品名）
2. comment: 投稿コメント（60〜120文字。親しみやすいSNS口調。末尾に「詳しくはブログで→ {article_url}」を含める）
3. hashtags: ハッシュタグ4〜5個（{default_tags} を含め、記事に合うものを追加）

条件:
- {n}件すべて異なる商品・角度でアプローチ
- 宣伝くさくなく、自然なおすすめ文にする
- コメントは体験・メリット・おすすめポイントを1つ盛り込む

出力形式（JSONのみ、余分なテキスト不要）:
[
  {{
    "product_keyword": "商品キーワード",
    "comment": "コメント本文（末尾にブログURL）",
    "hashtags": ["#楽天ROOM", "#楽天市場", "#{genre_label}"]
  }}
]"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # コードブロックマーカーを除去（```json ... ``` 形式に対応）
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text.strip())
        # 貪欲マッチで外側の配列全体を取得（非貪欲だと最初の]で止まり壊れたJSONになる）
        json_match = re.search(r'\[[\s\S]*\]', text)
        if not json_match:
            logger.warning("楽天ROOM: JSON未検出 (response=%s)", text[:200])
            return []
        try:
            posts = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.warning("楽天ROOM: JSONパース失敗: %s (text=%s)", e, json_match.group(0)[:200])
            return []
        results = []
        for p in posts[:n]:
            if not isinstance(p, dict) or not p.get("comment"):
                continue
            kw = p.get("product_keyword", keyword)[:20]
            kw_encoded = urllib.parse.quote(str(kw))
            rakuten_url = make_rakuten_affiliate_url(
                f"https://search.rakuten.co.jp/search/mall/{kw_encoded}/",
                rakuten_aff_id,
            )
            results.append({
                "product_keyword": kw,
                "rakuten_search_url": rakuten_url,
                "comment": p.get("comment", ""),
                "hashtags": p.get("hashtags", _ROOM_GENRE_HASHTAGS.get(genre, [])),
            })
        logger.info("楽天ROOM投稿ドラフト生成: %d件 (genre=%s)", len(results), genre)
        return results
    except Exception as e:
        logger.warning("楽天ROOM投稿ドラフト生成失敗（スキップ）: %s", e)
        return []


def build_room_draft_markdown(
    posts: list,
    article_title: str,
    article_url: str,
    genre: str,
    date_str: str,
) -> str:
    """楽天ROOM投稿ドラフトのMarkdownを生成（コピペ用）"""
    genre_label = _ROOM_GENRE_LABELS.get(genre, genre)
    pub_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    lines = [
        f"# 楽天ROOM 投稿ドラフト",
        f"## 記事：{article_title}（{genre}_{date_str}）",
        f"## 【投稿コンセプト】{genre_label}に関心がある読者へのリアルなおすすめ",
        "",
        "---",
        "",
    ]

    for i, post in enumerate(posts, 1):
        hashtags_str = "  " + " ".join(post.get("hashtags", []))
        lines += [
            f"## 投稿 {i} — {post['product_keyword']}",
            "",
            "🔍 検索キーワード",
            f"  {post['product_keyword']}",
            "",
            "💬 コメント",
            f"  {post['comment']}",
            "",
            "#️⃣ ハッシュタグ",
            hashtags_str,
            "",
            "---",
            "",
        ]

    return "\n".join(lines)


# ── メイン ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--genre",
        choices=["business", "investment", "travel", "gourmet", "gadget"],
        default="business",
    )
    args = parser.parse_args()
    genre = args.genre
    config = GENRE_CONFIG[genre]

    # ── ジャンルによるモデル切り替え ──
    # 投資記事は正確性が特に重要なため Opus を使用（他は Sonnet でコスト削減）
    global MODEL
    if genre == "investment":
        MODEL = "claude-opus-4-7"
        logger.info("investmentジャンル → claude-opus-4-7 を使用")
    else:
        logger.info("ジャンル %s → claude-sonnet-4-6 を使用", genre)

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
    topic  = select_topic(topics, date_str, genre, gh_token=gh_token)

    client = anthropic.Anthropic(api_key=api_key)

    prompt  = build_prompt(topic, date_str, genre)
    article = generate_article(client, prompt, genre)
    article = ensure_min_chars(client, article, prompt)

    # ── Pixabay 画像を記事に挿入 ─────────────────────────────
    pixabay_key = os.environ.get("UNSPLASH_API_KEY") or os.environ.get("PIXABAY_API_KEY")
    hero_image_url = ""
    if pixabay_key:
        title_hint = _get(topic, "title", "topic", "keyword")
        # Unsplashは英語タグで検索するためジャンル別英語クエリのみ使用
        img_query = _GENRE_IMAGE_QUERIES.get(genre, "nature landscape")
        images = fetch_pixabay_image_urls(img_query, pixabay_key, n=3)
        article = insert_images_into_article(article, images)
        if images:
            hero_image_url = images[0]["url"]
        logger.info("画像挿入完了: %d枚", len(images))
    else:
        logger.info("PIXABAY_API_KEY 未設定のため画像挿入スキップ")

    # ── PR表記バナーをh1直後に自動挿入 ──────────────────────
    article = insert_pr_notice(article, date_str)

    # ── サムネイル自動生成 ────────────────────────────────────
    slug = f"{genre}_{date_str}"
    thumbnail_web_path = f"/thumbnails/{slug}.png"
    try:
        import tempfile
        from generate_thumbnail import create_thumbnail
        with tempfile.TemporaryDirectory() as tmp_dir:
            thumb_local = create_thumbnail(
                title=extract_title(article) or slug,
                genre=genre,
                slug=slug,
                output_dir=Path(tmp_dir),
                bg_image_url=hero_image_url or None,  # Unsplash画像を背景に流用
            )
            thumb_bytes = thumb_local.read_bytes()
        thumb_repo_path = f"public/thumbnails/{slug}.png"
        push_binary_file(
            gh_token, thumb_repo_path, thumb_bytes,
            f"auto: add thumbnail {slug}",
        )
        logger.info("サムネイル生成・プッシュ完了: %s", thumb_repo_path)
    except Exception as e:
        logger.warning("サムネイル生成スキップ（エラー）: %s", e)
        thumbnail_web_path = hero_image_url  # フォールバック: Unsplash

    # ── heroImage を frontmatter に追加（サムネイル優先、なければ Unsplash）──
    final_hero = thumbnail_web_path or hero_image_url
    if final_hero:
        article = re.sub(
            r'^(---\n[\s\S]*?)(---\n)',
            lambda m: m.group(1) + f'heroImage: "{final_hero}"\n' + m.group(2),
            article, count=1
        )

    from factcheck import factcheck_article
    fc_result = factcheck_article(article, config["article_type"])
    if not fc_result["is_safe"]:
        print("ERROR: ファクトチェック失敗 - 投稿中止", file=sys.stderr)
        sys.exit(1)
    article = fc_result["verified_content"]

    # ── 編集者コメント（Noriのひとこと）を追加 ───────────────
    editor_note_text = generate_editor_note(client, extract_title(article), genre)
    if editor_note_text:
        article = article.rstrip() + build_editor_note(editor_note_text)

    # ── アフィリエイトリンクセクションを追加 ─────────────────
    rakuten_app_id    = os.environ.get("RAKUTEN_APP_ID", "")
    rakuten_aff_id    = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    a8_rakuten_mat    = os.environ.get("A8_RAKUTEN_MAT", "")
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

    # ガジェット記事: Claude APIでAmazon個別商品リンクを生成
    amazon_products = []
    if genre == "gadget":
        amazon_products = generate_amazon_gadget_products(client, extract_title(article), title_hint)

    # 全ジャンル: Claude APIで楽天商品候補を生成（RAKUTEN_AFFILIATE_IDがあれば）
    rakuten_claude_products = []
    if rakuten_aff_id:
        rakuten_claude_products = generate_rakuten_products(
            client, extract_title(article), title_hint, genre, rakuten_aff_id, a8_rakuten_mat
        )
        # 楽天APIで実商品画像・URLを補完（RAKUTEN_APP_IDがあれば）
        if rakuten_app_id and rakuten_claude_products:
            rakuten_claude_products = enrich_products_with_images(
                rakuten_claude_products, rakuten_app_id, rakuten_aff_id
            )
            logger.info("楽天商品画像補完完了: %d件", len(rakuten_claude_products))

    # ── 記事中盤にAmazon+楽天CTAを挿入（タグからテーマ一致リンクを生成）──
    _tag_m = re.search(r'^tags:\s*\[(.*?)\]', article, re.MULTILINE)
    _tags = [x.strip().strip('"').strip("'") for x in _tag_m.group(1).split(",")] if _tag_m else None
    midpoint_cta = build_midpoint_cta(genre, rakuten_aff_id, a8_rakuten_mat, tags=_tags)
    article = insert_midpoint_cta(article, midpoint_cta)
    logger.info("記事中盤CTAブロック挿入完了")

    # ── 検索意図マッチCTA（まとめ直前・文脈が合う記事のみ）──────
    intent_cta = build_intent_cta(genre, extract_title(article))
    if intent_cta:
        article = insert_intent_cta(article, intent_cta)
        logger.info("検索意図CTA挿入完了 (genre=%s)", genre)
    else:
        logger.info("検索意図CTA: 該当文脈なし（スキップ）")

    # ── 内部リンクセクションを追加（アフィリエイトの直前）────────
    current_slug = f"{genre}_{date_str}"
    related_articles = find_related_articles(genre, current_slug, n=5)
    if related_articles:
        article = article.rstrip() + build_internal_links_section(related_articles)
        logger.info("内部リンク追加: %d件", len(related_articles))
    else:
        logger.info("内部リンク: 同ジャンルの過去記事なし（スキップ）")

    affiliate_section = build_affiliate_section(
        genre, title_hint, rakuten_products, amazon_products, rakuten_aff_id, rakuten_claude_products, a8_rakuten_mat
    )
    article = article.rstrip() + "\n" + affiliate_section

    repo_path      = f"src/content/blog/{genre}_{date_str}.md"
    commit_message = f"auto: add {genre} article {date_str}"
    commit_sha     = push_file(gh_token, repo_path, article, commit_message)

    if commit_sha is None:
        print(f"スキップ: {repo_path} は既に存在します")
        return

    commit_url = f"https://github.com/{REPO}/commit/{commit_sha}"
    print(commit_url)

    article_url = f"{BLOG_URL}/blog/{genre}_{date_str}/"
    from notify import post_to_x
    post_to_x(
        article_type=config["article_type"],
        title=extract_title(article),
        blog_url=article_url,
        article_body=article,
    )
    # Pinterest は毎日 20:00 JST に pinterest_schedule.py が一括投稿するため
    # ここでは即時投稿しない（generate.py の役割はコンテンツ生成のみ）

    # ── 楽天ROOM 投稿ドラフト生成 ────────────────────────────
    # RAKUTEN_AFFILIATE_ID の有無に関わらず常に生成（Claude API のみで生成）
    room_posts = generate_room_posts_content(
        client,
        article_title=extract_title(article),
        article_url=article_url,
        keyword=title_hint,
        genre=genre,
        n=3,
    )
    if room_posts:
        room_md = build_room_draft_markdown(
            room_posts,
            article_title=extract_title(article),
            article_url=article_url,
            genre=genre,
            date_str=date_str,
        )
        room_path = f"data/room_drafts/{genre}_{date_str}.md"
        draft_name = f"{genre}_{date_str}"
        try:
            push_file(gh_token, room_path, room_md, f"auto: room drafts {genre} {date_str}")
            logger.info("楽天ROOM投稿ドラフト保存: %s", room_path)
            print(f"楽天ROOMドラフト: https://github.com/{REPO}/blob/main/{room_path}")
            # ── 新規ドラフトは posted.json に追加しない ──────────────────────────
            # Claude が次回セッション開始時に未投稿として検出・自動投稿する
            # （CLAUDE.md の指示に従い、セッション開始時に posted.json と照合）
            logger.info("楽天ROOMドラフト未投稿: %s (次回Claude起動時に自動投稿)", draft_name)
            print(f"⚠️  楽天ROOM未投稿: {draft_name} → 次回Claude起動時に自動投稿されます")
        except Exception as e:
            logger.warning("楽天ROOMドラフト保存失敗（スキップ）: %s", e)


if __name__ == "__main__":
    main()

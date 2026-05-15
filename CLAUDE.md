# affiliate-blog プロジェクト — Claudeへの自動指示

## 楽天ROOM 自動投稿ルール（最優先）

**このプロジェクトで作業するたびに、セッション開始時に必ず以下を実行してください。**

---

## ① 未投稿ドラフトの確認

```bash
cat data/room_drafts/posted.json
ls data/room_drafts/*.md
```

`posted.json` の `posted` 配列に**含まれていない `.md` ファイル**が投稿対象です。  
未投稿が1件以上あれば、② → ③ → ④ の手順を即座に実行してください。

---

## ② 商品選択ルール（過去の学習から）

楽天市場で商品を検索したあと、以下の**優先順位**で1商品を選ぶこと。

### 必須条件（これを満たさない商品は選ばない）
| 条件 | 基準 |
|------|------|
| レビュー評価 | ★ **4.0 以上** |
| レビュー件数 | **20件以上**（件数が多いほど優先） |
| ROOMに投稿ボタン | 商品ページに存在すること |

### 優先条件（高いほど良い商品）
1. **送料無料** の商品を優先
2. **有名ブランド** を優先（後述のジャンル別ブランドリスト参照）
3. **検索キーワードが商品タイトルに含まれている**
4. **まとめ買い・セット商品** より単品商品を優先（コメントが書きやすい）
5. レビュー件数が **100件以上** あれば最優先

### ジャンル別 優先ブランドリスト

| ジャンル | 優先ブランド例 |
|---------|--------------|
| gourmet（食・健康） | 森永、明治ザバス、マイプロテイン、X-PLOSION、NICHIGA、大塚製薬 |
| gadget（ガジェット） | Anker、Logicool、エレコム、バッファロー、サンワサプライ、UGREEN |
| travel（旅行・アウトドア） | モンベル、コールマン、スノーピーク、ロゴス、キャプテンスタッグ |
| investment（投資） | ダイヤモンド社、日経BP、東洋経済など出版社商品（書籍・雑誌） |
| business（仕事効率） | コクヨ、プラス、キングジム、ブラザー、カシオ |

### 避けるべき商品
- レビュー件数が **5件未満**
- ショップ名が怪しい（中国語・英語のみ・記号だらけ）
- 商品画像が粗い・テキストだらけ
- 同一ページに複数の全く異なる商品が混在

---

## ③ 楽天ROOM投稿手順（Chrome MCP）

### 重要な技術的注意点（過去の学習から）
> ❌ `javascript_tool` は楽天市場商品ページでブロックされる（Cookie/query string data エラー）  
> ✅ 代わりに `find` + `read_page` でリンクのhrefを取得する

### 手順詳細

#### Step 1: 商品ページを開く
```
navigate( url="https://search.rakuten.co.jp/search/mall/{検索キーワード}/" )
```
- 検索結果から ② の条件に合う商品をクリック
- 商品ページが読み込まれるまで `wait(2秒)` してから次へ

#### Step 2: ROOMに投稿のURLを取得
```
find( query="ROOMに投稿", tabId=XXX )
→ ref_XXX が返ってくる
read_page( tabId=XXX, ref_id="ref_XXX" )
→ href="https://room.rakuten.co.jp/mix?itemcode=...&scid=we_room_upc60" が取得できる
```

#### Step 3: ROOMフォームを開く
```
navigate( url="https://room.rakuten.co.jp/mix?itemcode=...&scid=we_room_upc60", tabId=XXX )
wait(2秒)
```

#### Step 4: コメントを入力する
```
find( query="コメントテキストエリア", tabId=XXX )
→ ref_YYY が返ってくる

form_input( ref="ref_YYY", tabId=XXX, value="コメント本文\n\n#ハッシュタグ1 #ハッシュタグ2 ..." )
```

#### Step 5: 投稿する（完了ボタン）
```
find( query="完了ボタン", tabId=XXX )
→ ref_ZZZ が返ってくる（テキストが "完了" のボタン）

left_click( ref="ref_ZZZ", tabId=XXX )
wait(3秒)
screenshot()
```
→ 「コレ！完了!」画面が表示されれば成功 ✅

### コメントの書き方ガイド（過去の学習から）

| 項目 | ルール |
|------|--------|
| 文字数 | **160〜180文字**（500文字上限に対して余裕を持つ） |
| 行数 | **4〜5行**（改行で読みやすく） |
| 文体 | 一人称・体験談調（「〜してみたら」「〜だったんですが」） |
| 締め | `◎` で終わる（例：「〜が変わった気がします◎」） |
| ハッシュタグ | コメントの最後に空行を挟んで記載 |
| ハッシュタグ数 | **5〜7個**（`#楽天ROOM #楽天市場` は必ず含める） |

### 良いコメント例（gourmet_20260514 投稿1より）
```
ホエイ・ソイ・カゼインの違いを調べてみたら
「筋トレ後30分以内に飲むならホエイが一番」って知ってから
種類を変えました。
前は「なんとなく有名なやつ」を選んでたけど
目的に合わせて選ぶようになってから実感が変わった気がします◎

#楽天ROOM #楽天市場 #ホエイプロテイン #筋トレ #タンパク質 #運動後 #ガジェット
```

---

## ④ 投稿完了後に posted.json を更新

```bash
# posted.json の "posted" 配列に追加してコミット・プッシュ
git add data/room_drafts/posted.json
git commit -m "auto: mark room draft {ドラフト名} as posted"
git push
```

`posted.json` 更新時は `posted` 配列に `"{genre}_{date}"` 形式の文字列を追記する。

---

## generate.py 実行後のフロー

```
generate.py 実行 → data/room_drafts/{genre}_{date}.md 作成
  ↓
（次回Claudeセッション起動時）
① 未投稿ドラフトを自動検出
  ↓
② 各ドラフトの検索キーワードで楽天市場を検索 → 条件に合う商品を選択
  ↓
③ Chrome MCP で楽天ROOMに投稿（投稿1〜3件）
  ↓
④ posted.json を更新してプッシュ
```

---

## Chrome MCP 接続が切れている場合

```javascript
tabs_context_mcp( createIfEmpty=True )
```
→ 新しいタブIDが返ってきたら接続成功。そのタブIDで作業を続ける。

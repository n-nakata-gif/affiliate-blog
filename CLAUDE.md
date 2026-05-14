# affiliate-blog プロジェクト — Claudeへの自動指示

## 楽天ROOM 自動投稿ルール（最優先）

**このプロジェクトで作業するたびに、セッション開始時に必ず以下を実行してください。**

### ① 未投稿ドラフトの確認

```bash
# 投稿済みリストと存在するドラフトを比較して未投稿を検出
cat data/room_drafts/posted.json
ls data/room_drafts/*.md
```

`data/room_drafts/posted.json` の `posted` 配列に**含まれていない `.md` ファイル**が未投稿ドラフトです。

未投稿ドラフトが1件以上あれば、② の手順でそのまま楽天ROOMへ投稿してください。

---

### ② 楽天ROOMへの投稿手順（Chrome MCP使用）

各ドラフトファイルの「投稿」ごとに以下を繰り返す：

#### 2-1. 商品ページを開く

```
navigate( url="https://search.rakuten.co.jp/search/mall/{検索キーワード}/" )
→ 上位商品をクリック
→ find("ROOMに投稿") → read_page(ref_id) でhref取得
→ navigate( url=取得したhref )
```

#### 2-2. コメントを入力する

```
find("コメントテキストエリア") → ref取得
form_input( ref=ref_XX, tabId=..., value="コメント本文\n\n#ハッシュタグ ..." )
```

#### 2-3. 投稿する

```
find("完了ボタン") または left_click( ref=ref_XX )
→ 「コレ！完了!」画面が出たら成功
```

---

### ③ 投稿完了後に posted.json を更新

全ドラフトの投稿が終わったら `data/room_drafts/posted.json` の `posted` 配列にドラフト名（例: `gourmet_20260514`）を追加してコミット・プッシュする。

```bash
# 例：gourmet_20260520 を追加してプッシュ
git add data/room_drafts/posted.json
git commit -m "auto: mark room draft gourmet_20260520 as posted"
git push
```

---

### 注意事項

- Chrome MCP が未接続の場合: `tabs_context_mcp(createIfEmpty=True)` で接続する
- JS は楽天市場商品ページでブロックされる → `find` / `read_page` で代替する
- コメントは `form_input` で入力（改行・ハッシュタグを含めて一括設定）
- 1件投稿するたびにスクリーンショットで「コレ！完了!」を確認する

---

## generate.py 実行後のフロー

`generate.py` が実行されると新しい ROOM ドラフトが `data/room_drafts/` に作成されます。
Claude はその後、上記の① → ② → ③ を自動的に実行して楽天ROOMへ投稿してください。

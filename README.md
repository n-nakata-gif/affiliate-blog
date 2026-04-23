# My Affiliate Blog

Astro + Tailwind CSS で構築したアフィリエイトブログです。

## ローカル開発

```bash
npm install
npm run dev
```

## 環境変数の設定

`.env.example` をコピーして `.env` ファイルを作成し、AdSense IDを設定します。

```bash
cp .env.example .env
```

`.env` を編集して自分のAdSense IDを入力してください。

---

## Cloudflare Pages へのデプロイ手順

### 1. GitHubリポジトリを用意する

このプロジェクトをGitHubにpushしておきます（すでに完了している場合はスキップ）。

### 2. Cloudflare Pagesのプロジェクトを作成する

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/) にログインします
2. 左メニューから「Workers & Pages」→「Pages」を選択します
3. 「プロジェクトを作成」ボタンをクリックします
4. 「Gitに接続」を選択し、GitHubアカウントと連携します
5. `affiliate-blog` リポジトリを選択します

### 3. ビルド設定を行う

以下の設定を入力します。

| 項目 | 値 |
|------|----|
| フレームワーク プリセット | Astro |
| ビルドコマンド | `npm run build` |
| ビルド出力ディレクトリ | `dist` |

### 4. 環境変数を設定する

「設定」→「環境変数」から以下を追加します。

| 変数名 | 値 |
|--------|----|
| `PUBLIC_ADSENSE_ID` | `ca-pub-xxxxxxxxxxxxxxxxx`（自分のIDに変更） |

> **注意：** AdSenseのIDは Google AdSense の管理画面で確認できます。
> AdSenseを使わない場合はこの変数を設定しなくてもOKです（広告枠が非表示になります）。

### 5. デプロイを実行する

「保存してデプロイ」をクリックすると自動でビルドが始まります。
完了後、`https://affiliate-blog-xxx.pages.dev` のようなURLでサイトが公開されます。

### 6. 以降の更新

`main` ブランチにpushするたびに自動でデプロイされます。

---

## ブログ記事の追加方法

`src/content/blog/` フォルダに Markdown ファイルを追加します。

```markdown
---
title: "記事タイトル"
description: "記事の説明（一覧・SEOに使用）"
pubDate: 2024-12-01
tags: ["タグ1", "タグ2"]
---

ここに記事本文を書きます。
```

ファイルを追加してGitHubにpushすると、自動でデプロイされて記事が公開されます。

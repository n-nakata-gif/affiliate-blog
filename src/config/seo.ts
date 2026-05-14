/**
 * SEO設定の一元管理ファイル
 *
 * ■ NOINDEX_PATHS: noindex にするページのパスを追加するだけで
 *   - Layout.astro が自動で <meta name="robots" content="noindex"> を挿入
 *   - サイトマップからも自動除外
 *   （二箇所に書く必要がなくなります）
 *
 * ■ REDIRECTS: 記事を削除・URLを変更したら必ずここに追加してください
 *   { '旧パス': '新パス' } の形式で記載します
 *   ※ 追加しないと CI チェックでデプロイが自動的に止まります
 */

/** noindex にするページのパス一覧（サイトマップからも自動除外） */
export const NOINDEX_PATHS: string[] = [
  '/disclaimer',
];

/** リダイレクト設定: { '旧パス': '新パス（絶対URL または パス）' } */
export const REDIRECTS: Record<string, string> = {
  // 2026-05-12: 重複コンテンツのため削除 → 最新版にリダイレクト
  '/blog/protein-supplement-guide': '/blog/gourmet_20260511/',
};

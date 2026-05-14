#!/bin/bash
# =============================================================
# check-redirects.sh
# 記事削除時にリダイレクト設定漏れがないかを自動チェックします
# GitHub Actions の deploy.yml から呼び出されます
# =============================================================
set -e

SEO_CONFIG="src/config/seo.ts"

# 直前のコミットと比較して削除されたブログ記事 MD ファイルを取得
DELETED=$(git diff HEAD~1 --name-only --diff-filter=D 2>/dev/null \
  | grep "^src/content/blog/.*\.md$" \
  | sed 's|src/content/blog/||' \
  | sed 's|\.md$||' \
  || true)

if [ -z "$DELETED" ]; then
  echo "✅ 削除された記事なし。リダイレクトチェックをスキップします。"
  exit 0
fi

echo "🗑️  削除された記事が見つかりました:"
echo "$DELETED" | sed 's/^/   - /'
echo ""

FAILED=0
for slug in $DELETED; do
  # seo.ts の REDIRECTS セクションにスラグが含まれているか確認
  if grep -q "\"\/blog\/${slug}\"" "$SEO_CONFIG" || grep -q "'\/blog\/${slug}'" "$SEO_CONFIG"; then
    echo "  ✅ /blog/${slug} のリダイレクトが設定されています"
  else
    echo "  ❌ /blog/${slug} のリダイレクトが設定されていません！"
    echo ""
    echo "     【対処方法】 ${SEO_CONFIG} の REDIRECTS に以下を追加してください:"
    echo "     '/blog/${slug}': '/blog/新しいURL/',"
    echo ""
    FAILED=1
  fi
done

if [ "$FAILED" -eq 1 ]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ リダイレクト設定が不足しているためデプロイを中断しました。"
  echo "   記事を削除した場合は必ず src/config/seo.ts の REDIRECTS に"
  echo "   リダイレクト先を追加してからコミットしてください。"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi

echo "✅ すべてのリダイレクトが確認済みです。"

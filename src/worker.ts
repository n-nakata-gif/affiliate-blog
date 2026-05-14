import { REDIRECTS } from './config/seo.ts';

interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.hostname === "nexigen-blog.com" || url.hostname === "www.nexigen-blog.com") {
      return Response.redirect(`https://novlify.jp${url.pathname}${url.search}`, 301);
    }

    // リダイレクト設定（src/config/seo.ts の REDIRECTS を参照）
    // 記事を削除・URLを変更した場合は seo.ts に追記するだけでここに自動反映されます
    const pathWithoutTrailingSlash = url.pathname.replace(/\/$/, '');
    const redirectTo = REDIRECTS[url.pathname] ?? REDIRECTS[pathWithoutTrailingSlash];
    if (redirectTo) {
      const dest = redirectTo.startsWith('http') ? redirectTo : `https://novlify.jp${redirectTo}`;
      return Response.redirect(dest, 301);
    }

    return env.ASSETS.fetch(request);
  },
};

interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.hostname === "nexigen-blog.com" || url.hostname === "www.nexigen-blog.com") {
      return Response.redirect(`https://novlify.jp${url.pathname}${url.search}`, 301);
    }

    // 削除ページのリダイレクト（旧記事 → 内容が近い新記事）
    if (url.pathname === "/blog/protein-supplement-guide" || url.pathname === "/blog/protein-supplement-guide/") {
      return Response.redirect("https://novlify.jp/blog/gourmet_20260511/", 301);
    }

    return env.ASSETS.fetch(request);
  },
};

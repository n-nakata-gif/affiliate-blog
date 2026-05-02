interface Env {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.hostname === "nexigen-blog.com" || url.hostname === "www.nexigen-blog.com") {
      return Response.redirect(`https://novlify.jp${url.pathname}${url.search}`, 301);
    }

    return env.ASSETS.fetch(request);
  },
};

// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import { NOINDEX_PATHS } from './src/config/seo.ts';

export default defineConfig({
  site: 'https://novlify.jp',
  integrations: [
    sitemap({
      // NOINDEX_PATHS に含まれるページはサイトマップから自動除外
      // noindex ページを追加したい場合は src/config/seo.ts を編集してください
      filter: (page) => {
        const pathname = new URL(page).pathname;
        return !NOINDEX_PATHS.some(
          (p) => pathname === p || pathname === `${p}/`
        );
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()]
  }
});

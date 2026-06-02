import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const blog = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/blog' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.date(),
    tags: z.array(z.string()).optional(),
    heroImage: z.string().optional(),
    // カニバリ解消用：別記事を正規URLに指定したい場合に設定
    canonicalUrl: z.string().optional(),
    // 文体リライト済みフラグ（rewrite_human.py 用）
    rewritten: z.boolean().optional(),
    human_rewritten: z.boolean().optional(),
  }),
});

export const collections = { blog };

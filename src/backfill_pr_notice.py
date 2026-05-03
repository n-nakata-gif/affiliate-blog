"""
既存記事の冒頭（h1直後）にPR表記バナーを追加するバックフィルスクリプト
"""
from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

CONTENT_DIR = Path(__file__).parent / "content" / "blog"

PR_PATTERN = re.compile(r'PR・広告を含みます|本記事はPRを含みます|本記事にはアフィリエイト広告')


def get_pub_date(content: str) -> str:
    """frontmatterからpubDateを取得してYYYYMMDD形式に変換"""
    m = re.search(r'^pubDate:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if m:
        return m.group(1).replace("-", "")
    return datetime.now().strftime("%Y%m%d")


def insert_pr_notice(article: str, date_str: str) -> str:
    fm_match = re.match(r'^---\n[\s\S]*?\n---\n', article)
    if fm_match:
        frontmatter = article[:fm_match.end()]
        body = article[fm_match.end():]
    else:
        frontmatter = ""
        body = article

    # 冒頭400字以内にすでにPR表記があればスキップ
    if PR_PATTERN.search(body[:400]):
        return article

    dt = datetime.strptime(date_str, "%Y%m%d")
    year_month = f"{dt.year}年{dt.month}月"
    pr_block = (
        '\n<div style="background:#fff8e1;border-left:4px solid #f59e0b;'
        'padding:10px 16px;margin:1rem 0;border-radius:0 6px 6px 0;font-size:0.9em;color:#555;">'
        '📢 <strong style="color:#333;">本記事はPR・広告を含みます。</strong>'
        f'（{year_month}時点の情報です）'
        '</div>\n'
    )

    lines = body.split('\n')
    h1_idx = next((i for i, l in enumerate(lines) if l.startswith('# ')), -1)
    if h1_idx >= 0:
        lines.insert(h1_idx + 1, pr_block)
    else:
        h2_idx = next((i for i, l in enumerate(lines) if l.startswith('## ')), -1)
        if h2_idx >= 0:
            lines.insert(h2_idx, pr_block)
        else:
            lines.insert(0, pr_block)

    return frontmatter + '\n'.join(lines)


def fix_sponsored_rel(content: str) -> str:
    """提携していないリンクのrel='sponsored'をrel=''に修正"""
    # Amazon tag付きリンクと楽天アフィリエイトURLはsponsoredのまま維持
    # それ以外の一般URLのsponsoredを除去
    def replace_rel(m: re.Match) -> str:
        href = m.group(1)
        # Amazon affiliate または 楽天アフィリエイトURLはそのまま
        if 'tag=nexigen22-22' in href or 'hb.afl.rakuten.co.jp' in href or 'rpx.a8.net' in href:
            return m.group(0)
        # それ以外は sponsored を除去
        return m.group(0).replace('rel="noopener sponsored"', 'rel="noopener"')

    pattern = re.compile(r'href="([^"]*)"[^>]*rel="noopener sponsored"')
    return pattern.sub(replace_rel, content)


def main():
    md_files = sorted(CONTENT_DIR.glob("*.md"))
    pr_added = 0
    rel_fixed = 0

    for path in md_files:
        content = path.read_text(encoding="utf-8")
        original = content

        date_str = get_pub_date(content)
        content = insert_pr_notice(content, date_str)
        content = fix_sponsored_rel(content)

        if content != original:
            path.write_text(content, encoding="utf-8")
            changes = []
            if 'PR・広告を含みます' in content[:500] and 'PR・広告を含みます' not in original[:500]:
                changes.append("PR表記追加")
                pr_added += 1
            if content != insert_pr_notice(original, date_str):
                changes.append("rel修正")
                rel_fixed += 1
            print(f"  修正: {path.name} ({', '.join(changes) if changes else '変更あり'})")
        else:
            print(f"  スキップ: {path.name}")

    print(f"\n完了: PR表記追加={pr_added}記事, rel修正済み={rel_fixed}記事")


if __name__ == "__main__":
    main()

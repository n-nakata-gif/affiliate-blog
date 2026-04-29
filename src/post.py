import os
import sys
import re
import base64
from datetime import datetime
import urllib.request
import urllib.error
import json

BLOG_URL = "https://nexigen-blog.com"
REPO = "n-nakata-gif/affiliate-blog"
BRANCH = "main"
ARTICLE_SRC = "output/article.md"


def github_request(method, path, token, body=None):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _extract_title(content):
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_tags(content):
    m = re.search(r'^tags:\s*\[(.+?)\]', content, re.MULTILINE)
    if not m:
        return []
    return [t.strip().strip("\"'") for t in m.group(1).split(',')]


def _count_chars(content):
    text = re.sub(r'^---[\s\S]*?---\n', '', content, count=1)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'[#*`|]', '', text)
    return len(re.sub(r'\n+', '\n', text).strip())


def get_existing_sha(token, dest_path):
    try:
        result = github_request("GET", f"contents/{dest_path}?ref={BRANCH}", token)
        return result.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN is not set", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(ARTICLE_SRC):
        print(f"ERROR: {ARTICLE_SRC} not found", file=sys.stderr)
        sys.exit(1)

    with open(ARTICLE_SRC, "r", encoding="utf-8") as f:
        content = f.read()

    date_str = datetime.utcnow().strftime("%Y%m%d")
    dest_path = f"src/content/blog/article_{date_str}.md"
    commit_message = f"auto: add article {date_str}"

    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sha = get_existing_sha(token, dest_path)

    body = {
        "message": commit_message,
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha

    result = github_request("PUT", f"contents/{dest_path}", token, body)

    commit_sha = result["commit"]["sha"]
    url = f"https://github.com/{REPO}/commit/{commit_sha}"
    print(url)

    from notify import send_notification, post_to_x
    send_notification(
        article_type="business",
        title=_extract_title(content),
        article_url=url,
        blog_url=BLOG_URL,
        tags=_extract_tags(content),
        word_count=_count_chars(content),
    )
    post_to_x(
        article_type="business",
        title=_extract_title(content),
        blog_url=BLOG_URL,
    )


if __name__ == "__main__":
    main()

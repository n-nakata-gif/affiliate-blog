"""
Google Search Console OAuth2 リフレッシュトークン取得スクリプト
（一度だけローカルで実行してリフレッシュトークンを取得するためのスクリプト）

使い方:
  python src/get_gsc_token.py

実行するとブラウザが開くので、Search Consoleの所有者アカウントでログインしてください。
完了すると GSC_OAUTH_CREDENTIALS という JSON が表示されるので、
GitHub Secretsに登録してください。
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# OAuth2クライアント情報（環境変数から取得）
# 実行前に以下を設定してください:
#   export GSC_CLIENT_ID="your-client-id"
#   export GSC_CLIENT_SECRET="your-client-secret"
import os as _os
CLIENT_CONFIG = {
    "installed": {
        "client_id": _os.environ["GSC_CLIENT_ID"],
        "client_secret": _os.environ["GSC_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


def main():
    print("Google Search Console 認証を開始します...")
    print("ブラウザが開くので、Search Consoleの所有者アカウント (nori.nakata1004@gmail.com) でログインしてください。\n")

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    creds = flow.run_local_server(port=0)

    result = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    print("\n" + "=" * 60)
    print("✅ 認証成功！以下の内容を GitHub Secret に登録してください。")
    print("Secret名: GSC_OAUTH_CREDENTIALS")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 60)

    # ローカルにも保存（.gitignore対象）
    out_path = Path(__file__).parent / "gsc_oauth_credentials.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n📄 ローカルにも保存しました: {out_path}")
    print("⚠  このファイルはGitにコミットしないでください。")


if __name__ == "__main__":
    main()

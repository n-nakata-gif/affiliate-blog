"""
GA4 自動分析レポート
毎週月曜に先週のPV・流入・記事別データを取得してGmailで送信する。

必要なSecrets:
  GA4_PROPERTY_ID  : GA4プロパティID (数字のみ, 例: 123456789)
  GA4_SERVICE_ACCOUNT_JSON : サービスアカウントJSON (文字列全体)
  GMAIL_USER / GMAIL_APP_PASSWORD
"""

from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

JST = timezone(timedelta(hours=9))

# ────────────────────────────────────────────────
# GA4 Data API (google-analytics-data)
# ────────────────────────────────────────────────

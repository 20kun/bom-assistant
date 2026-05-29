"""Feishu (Lark) bot integration — push BOM extraction notifications."""

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import date

import requests


class FeishuBot:
    """Send BOM extraction notifications via Feishu webhook."""

    def __init__(self, webhook_url: str | None = None, secret: str | None = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self.secret = secret or os.getenv("FEISHU_WEBHOOK_SECRET", "")

    def _sign(self) -> tuple[str, str]:
        """Generate Feishu signature for webhook verification."""
        timestamp = str(int(time.time()))
        if not self.secret:
            return timestamp, ""
        sign_str = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            sign_str.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        sign_b64 = base64.b64encode(hmac_code.digest()).decode("utf-8")
        return timestamp, sign_b64

    def send_bom_notification(
        self,
        project_name: str,
        item_count: int,
        validation_status: str,
        validation_score: float,
        time_saved_minutes: float,
        error_count: int = 0,
        warning_count: int = 0,
    ) -> bool:
        """Send BOM extraction result notification to Feishu group."""
        if not self.webhook_url:
            return False

        status_emoji = {"通过": "🟢", "有警告": "🟡", "有错误": "🔴"}
        emoji = status_emoji.get(validation_status, "📋")

        timestamp, sign = self._sign()

        card = {
            "timestamp": timestamp,
            "sign": sign,
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🔧 BOM提取完成 — {project_name}"},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**项目**：{project_name}\n"
                                f"**零件数**：{item_count} 项\n"
                                f"**数据校验**：{emoji} {validation_status}（{validation_score:.0f}分）\n"
                                f"**问题数**：错误 {error_count} / 警告 {warning_count}\n"
                                f"**节省时间**：约 {time_saved_minutes:.0f} 分钟\n"
                                f"**处理时间**：{date.today().isoformat()}"
                            ),
                        },
                    },
                    {
                        "tag": "hr",
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": "🤖 由BOM智能提取助手自动生成 | 多Agent协作校验",
                            }
                        ],
                    },
                ],
            },
        }

        try:
            resp = requests.post(self.webhook_url, json=card, timeout=10)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except requests.RequestException:
            return False

    def send_simple_message(self, title: str, content: str) -> bool:
        """Send a simple text card to Feishu group."""
        if not self.webhook_url:
            return False

        timestamp, sign = self._sign()

        payload = {
            "timestamp": timestamp,
            "sign": sign,
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content},
                    }
                ],
            },
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except requests.RequestException:
            return False

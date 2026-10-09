"""钉钉告警推送（异步 + 限流）。

⚠️ 必须 async：采集循环是事件循环，同步 requests.post 会阻塞所有 PLC。
⚠️ 限流：钉钉官方 20 条/分钟，超了会被拒（可能封机器人）。
"""
import asyncio
import collections
import json
import time

import requests


class DingTalkNotifier:
    def __init__(self, webhook_url, timeout=5, min_severity="critical",
                 rate_limit_per_min=20):
        self.url = webhook_url
        self.timeout = timeout
        self.levels = {"critical": 3, "warning": 2, "info": 1}
        self.min_level = self.levels.get(min_severity, 3)

        self.rate_limit = rate_limit_per_min
        self._sent = collections.deque()   # monotonic 时间戳滑动窗口
        self._lock = asyncio.Lock()

    def _should_send(self, severity):
        return self.levels.get(severity, 0) >= self.min_level

    async def _acquire_slot(self):
        """滑动窗口限流：60 秒内不超过 rate_limit 条。"""
        async with self._lock:
            now = time.monotonic()
            while self._sent and now - self._sent[0] > 60:
                self._sent.popleft()
            if len(self._sent) >= self.rate_limit:
                return False
            self._sent.append(now)
            return True

    async def send_alarm(self, alarm):
        if not self._should_send(alarm.get("severity", "")):
            return False

        if not await self._acquire_slot():
            print(f"[!] 钉钉限流：{self.rate_limit}条/分钟已满，丢弃 {alarm.get('code')}")
            return False

        text = self._format(alarm)
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "报警", "text": text},
        }

        try:
            # 放到线程池，不阻塞事件循环
            r = await asyncio.to_thread(
                requests.post,
                self.url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            ok = (r.status_code == 200 and r.json().get("errcode") == 0)
            if not ok:
                print(f"[!] 钉钉推送失败: {r.status_code} {r.text[:200]}")
            return ok
        except Exception as e:
            print(f"[!] 钉钉推送异常: {e}")
            return False

    def _format(self, a):
        ts = a.get("timestamp", int(time.time() * 1000)) // 1000
        t_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        kind_zh = "故障" if a.get("kind") == "fault" else "报警"
        return (
            f"### 报警通知 · {kind_zh}\n\n"
            f"- **PLC**: {a.get('plc', '?')}\n"
            f"- **变频器**: {a.get('drive', '?')}\n"
            f"- **代码**: `{a.get('code', '?')}`\n"
            f"- **内容**: {a.get('text', '?')}\n"
            f"- **级别**: {a.get('severity', '?')}\n"
            f"- **时间**: {t_str}\n"
        )


def load_notifier(config):
    cfg = config.get("dingtalk", {})
    if not cfg.get("enabled"):
        return None
    url = cfg.get("webhook", "").strip()
    if not url:
        print("[!] dingtalk.enabled=true 但没配 webhook URL")
        return None
    return DingTalkNotifier(
        url,
        min_severity=cfg.get("min_severity", "critical"),
        rate_limit_per_min=cfg.get("rate_limit_per_min", 20),
    )

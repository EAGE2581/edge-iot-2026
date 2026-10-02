"""钉钉告警推送。"""
import json
import time

import requests


class DingTalkNotifier:
    def __init__(self, webhook_url, timeout=5, min_severity="critical"):
        self.url = webhook_url
        self.timeout = timeout
        self.levels = {"critical": 3, "warning": 2, "info": 1}
        self.min_level = self.levels.get(min_severity, 3)

    def _should_send(self, severity):
        return self.levels.get(severity, 0) >= self.min_level

    def send_alarm(self, alarm):
        if not self._should_send(alarm.get("severity", "")):
            return False

        text = self._format(alarm)
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "报警", "text": text},
        }

        try:
            r = requests.post(
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
    return DingTalkNotifier(url, min_severity=cfg.get("min_severity", "critical"))

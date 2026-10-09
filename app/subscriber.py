"""OPC UA 订阅管理器（带新鲜度判定）。

⚠️ 价值永不过期是危险的：OPC UA 会话假死时不会抛异常，
   程序会一直拿旧值配新时间戳往外发，看板看起来全绿，实际已经断了几小时。
"""
import time


class OpcUaSubscriber:
    def __init__(self, period_ms=100, interval_s=5, freshness_factor=3):
        self.period_ms = period_ms
        # 超过 3 × 采集周期就视为过期（默认 15s）
        self.freshness_s = freshness_factor * interval_s

        self.latest = {}          # key -> (val, monotonic_ts)
        self.node_to_key = {}
        self.sub = None
        self.handles = []
        self.change_count = 0

    async def start(self, client, subscribe_nodes):
        for key, meta in subscribe_nodes.items():
            self.node_to_key[meta["node_id"]] = key

        self.sub = await client.create_subscription(self.period_ms, self)

        for key, meta in subscribe_nodes.items():
            node = client.get_node(meta["node_id"])
            handle = await self.sub.subscribe_data_change(node)
            self.handles.append(handle)

    def datachange_notification(self, node, val, data):
        node_id_str = node.nodeid.to_string()
        key = self.node_to_key.get(node_id_str)
        if key is None:
            return
        self.latest[key] = (val, time.monotonic())
        self.change_count += 1

    def snapshot(self, now=None):
        """返回未过期的值。超时 key 不包含。"""
        now = now if now is not None else time.monotonic()
        return {
            k: v for k, (v, ts) in self.latest.items()
            if now - ts <= self.freshness_s
        }

    def stale_keys(self, now=None):
        """返回已过期的 key 列表，用于告警。"""
        now = now if now is not None else time.monotonic()
        return [k for k, (_, ts) in self.latest.items()
                if now - ts > self.freshness_s]

    def value_age(self, key, now=None):
        """返回某个 key 的值多久没更新（秒），没值返回 None。"""
        if key not in self.latest:
            return None
        now = now if now is not None else time.monotonic()
        return now - self.latest[key][1]

    async def stop(self):
        if self.sub is not None:
            try:
                await self.sub.delete()
            except Exception:
                pass
            self.sub = None
            self.handles = []
        self.node_to_key = {}

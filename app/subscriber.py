"""OPC UA 订阅管理器。

职责：
    1. 为一组"快变 + 事件型"节点建立 OPC UA 订阅
    2. 回调收到数据变化时，更新内存里的"最新值"字典
    3. 主循环随时可以取"当前最新值"，作为这一帧的订阅部分

设计要点：
    - 一个 PLC 一个 Subscription（不是每个字段一个）
    - 回调只做"写入内存"，不做耗时操作（避免阻塞）
    - 内存字典无需加锁（asyncua 回调与主循环在同一事件循环线程）
"""


class OpcUaSubscriber:
    """订阅管理器。一个实例管理一个 PLC 的所有订阅节点。"""

    def __init__(self, period_ms=100):
        # 订阅检查周期（毫秒）。100ms 足够捕捉启停瞬态
        self.period_ms = period_ms

        # 最新值缓存：{字段 key: 最新值}
        self.latest = {}

        # node_id 字符串 → 字段 key 的映射（回调里反查用）
        self.node_to_key = {}

        # subscription 对象和句柄，用于清理
        self.sub = None
        self.handles = []

        # 统计
        self.change_count = 0

    async def start(self, client, subscribe_nodes):
        """建立订阅。

        参数：
            client            asyncua 的 Client 对象（已连接）
            subscribe_nodes   {key: meta} 字典，meta 里要有 node_id

        例：
            subscribe_nodes = {
                "drive_1_iatst_glatt": {"node_id": "ns=4;i=21", ...},
                "drive_1_nist_a":      {"node_id": "ns=4;i=20", ...},
            }
        """
        # 建立映射，方便回调反查
        for key, meta in subscribe_nodes.items():
            self.node_to_key[meta["node_id"]] = key

        # 创建一个订阅（100ms 检查一次）
        self.sub = await client.create_subscription(self.period_ms, self)

        # 逐个绑定节点
        for key, meta in subscribe_nodes.items():
            node = client.get_node(meta["node_id"])
            handle = await self.sub.subscribe_data_change(node)
            self.handles.append(handle)

    def datachange_notification(self, node, val, data):
        """asyncua 回调。数据变化时被调用。

        注意：
            这个函数运行在 asyncua 的事件循环线程里，
            只做"更新内存"这一件事——绝不写数据库、不调 HTTP。
        """
        node_id_str = node.nodeid.to_string()
        key = self.node_to_key.get(node_id_str)
        if key is None:
            return
        self.latest[key] = val
        self.change_count += 1

    def snapshot(self):
        """取当前最新值的快照。返回 {key: value}。

        主循环每次读值时调用一次。
        """
        return dict(self.latest)

    async def stop(self):
        """清理订阅。断线或退出时调用。"""
        if self.sub is not None:
            try:
                await self.sub.delete()
            except Exception:
                pass
            self.sub = None
            self.handles = []
        self.node_to_key = {}

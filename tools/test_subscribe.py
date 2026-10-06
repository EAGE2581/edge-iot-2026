"""独立验证 OPC UA 订阅能不能工作。

用法：
    python3 tools/test_subscribe.py 192.168.14.1

前置：
    1. 只有能连到 PLC 时才跑
    2. 订阅周期 100ms，跑 30 秒后自动退出
"""
import asyncio
import sys
import time

from asyncua import Client


class SubHandler:
    """订阅回调。每次数据变化被调用。"""

    def __init__(self):
        self.count = 0
        self.start = time.time()

    def datachange_notification(self, node, val, data):
        self.count += 1
        elapsed = time.time() - self.start
        print(f"[{elapsed:6.2f}s] #{self.count:4d} {node} = {val}")


async def main(url):
    handler = SubHandler()

    async with Client(url) as c:
        print(f"[*] 已连接 {url}")

        # 创建订阅：100ms 检查一次变化
        sub = await c.create_subscription(100, handler)
        print("[*] 订阅已创建，周期 100ms")

        # 订阅 3 个节点（快变字段）
        nodes_to_watch = [
            "ns=4;i=20",   # drive_1_nist_a（转速）
            "ns=4;i=21",   # drive_1_iatst_glatt（电流）
            "ns=4;i=22",   # drive_1_mist_glatt（扭矩）
        ]
        for nid in nodes_to_watch:
            node = c.get_node(nid)
            handle = await sub.subscribe_data_change(node)
            print(f"[*] 已订阅 {nid} (handle={handle})")

        print("[*] 等 30 秒，看数据变化...")
        await asyncio.sleep(30)

        print(f"[*] 30 秒内共收到 {handler.count} 次数据变化")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 tools/test_subscribe.py <PLC_IP>")
        print("例:   python3 tools/test_subscribe.py 192.168.14.1")
        sys.exit(1)
    url = f"opc.tcp://{sys.argv[1]}:4840"
    try:
        asyncio.run(main(url))
    except KeyboardInterrupt:
        print("\n[*] 已停止")

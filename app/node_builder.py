"""根据单个 PLC 配置生成 NodeId 映射表。

每个字段带 mode 标记：
    subscribe → 用 OPC UA 订阅（快变 + 事件型）
    poll      → 用主循环轮询（缓变量）
"""


def build_node_ids(plc_cfg):
    """返回 {字段名 → {node_id, type, name, mode}} 映射。"""
    node_ids = {}
    for idx, start in enumerate(plc_cfg["udt_starts"]):
        drive = f"drive_{idx+1}"
        for field in plc_cfg["fields"]:
            key = f"{drive}_{field['name']}"
            node_ids[key] = {
                "node_id": f"ns=4;i={start + field['offset']}",
                "type": field["type"],
                "name": field["name"],
                "mode": field.get("mode", "poll"),  # 未指定默认 poll
            }
    return node_ids


def split_by_mode(node_ids):
    """把节点按 mode 分成两组。

    返回 (subscribe_nodes, poll_nodes)，都是 {key: meta} 的形式。
    """
    subscribe_nodes = {}
    poll_nodes = {}
    for key, meta in node_ids.items():
        if meta.get("mode") == "subscribe":
            subscribe_nodes[key] = meta
        else:
            poll_nodes[key] = meta
    return subscribe_nodes, poll_nodes

"""根据单个 PLC 配置生成 NodeId 映射表。"""


def build_node_ids(plc_cfg):
    node_ids = {}
    for idx, start in enumerate(plc_cfg["udt_starts"]):
        drive = f"drive_{idx+1}"
        for field in plc_cfg["fields"]:
            key = f"{drive}_{field['name']}"
            node_ids[key] = {
                "node_id": f"ns=4;i={start + field['offset']}",
                "type": field["type"],
                "name": field["name"],
            }
    return node_ids

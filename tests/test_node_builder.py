"""测试 NodeId 生成。"""
from app.node_builder import build_node_ids


def test_basic():
    plc_cfg = {
        "udt_starts": [16, 25],
        "fields": [
            {"name": "zsw1", "offset": 2, "type": "raw"},
            {"name": "iatst_glatt", "offset": 5, "type": "current"},
        ],
    }
    nodes = build_node_ids(plc_cfg)
    assert len(nodes) == 4
    assert nodes["drive_1_zsw1"]["node_id"] == "ns=4;i=18"
    assert nodes["drive_1_iatst_glatt"]["node_id"] == "ns=4;i=21"
    assert nodes["drive_2_zsw1"]["node_id"] == "ns=4;i=27"


def test_type_and_name():
    plc_cfg = {
        "udt_starts": [16],
        "fields": [{"name": "iatst_glatt", "offset": 5, "type": "current"}],
    }
    nodes = build_node_ids(plc_cfg)
    assert nodes["drive_1_iatst_glatt"]["type"] == "current"
    assert nodes["drive_1_iatst_glatt"]["name"] == "iatst_glatt"

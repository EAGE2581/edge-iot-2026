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


def test_mode_included():
    plc_cfg = {
        "udt_starts": [16],
        "fields": [
            {"name": "iatst_glatt", "offset": 5, "type": "current", "mode": "subscribe"},
            {"name": "motor_temp", "offset": 9, "type": "temp", "mode": "poll"},
        ],
    }
    nodes = build_node_ids(plc_cfg)
    assert nodes["drive_1_iatst_glatt"]["mode"] == "subscribe"
    assert nodes["drive_1_motor_temp"]["mode"] == "poll"


def test_mode_default_poll():
    plc_cfg = {
        "udt_starts": [16],
        "fields": [{"name": "zsw1", "offset": 2, "type": "raw"}],
    }
    nodes = build_node_ids(plc_cfg)
    assert nodes["drive_1_zsw1"]["mode"] == "poll"


def test_split_by_mode():
    from app.node_builder import split_by_mode
    node_ids = {
        "a": {"node_id": "x", "mode": "subscribe"},
        "b": {"node_id": "y", "mode": "poll"},
        "c": {"node_id": "z", "mode": "subscribe"},
    }
    sub, poll = split_by_mode(node_ids)
    assert set(sub.keys()) == {"a", "c"}
    assert set(poll.keys()) == {"b"}

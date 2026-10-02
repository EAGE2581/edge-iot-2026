"""读取 config.yaml，展开 profile。"""
import yaml


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def expand_plc(entry, profiles):
    cfg = dict(entry)
    profile_name = cfg.pop("profile", None)
    if profile_name:
        profile = profiles.get(profile_name)
        if not profile:
            raise ValueError(f"找不到 profile: {profile_name}")
        merged = dict(profile)
        merged.update(cfg)
        cfg = merged

    if cfg.get("mode") == "udt_array" and "udt_starts" not in cfg:
        count = cfg["drive_count"]
        base = cfg["udt_start_base"]
        step = cfg["udt_start_step"]
        cfg["udt_starts"] = [base + i * step for i in range(count)]

    return cfg


def load_plcs(config_path, plc_names=None):
    cfg = load_config(config_path)
    profiles = cfg.get("profiles", {})
    all_plcs = [expand_plc(p, profiles) for p in cfg["plcs"]]
    if plc_names:
        selected = [p for p in all_plcs if p["name"] in plc_names]
    else:
        selected = [p for p in all_plcs if p.get("enabled", True)]
    return cfg, selected

import yaml


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError("config.yaml must be a mapping at the top level")

    if "silence_rules" not in cfg or not isinstance(cfg["silence_rules"], list):
        raise ValueError("config.yaml missing required key: silence_rules (list)")

    cfg.setdefault("never_silence", {})
    cfg["never_silence"].setdefault("title_contains", [])
    cfg["never_silence"].setdefault("calendar_ids", [])
    cfg.setdefault("scan", {})
    cfg["scan"].setdefault("days_ahead", 30)
    cfg["scan"].setdefault("include_past", False)

    return cfg


def save_config(cfg, path):
    """Write config dict back to YAML. Loses comments (config.yaml is machine-manageable)."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

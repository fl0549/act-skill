"""The user's preferences for act-skill, one JSON file per machine.

Path: $ACT_CONFIG, else ~/.config/act-skill/config.json. Missing keys take the defaults below; an
environment variable overrides the file for one run. The unlock code is never stored here: it
stays in the user's own shell as ACT_PIN.
"""
import json
import os

PATH = os.environ.get("ACT_CONFIG") or os.path.expanduser("~/.config/act-skill/config.json")

DEFAULTS = {
    # Name shown to the other testers when joining a Google Group. No default: asked at setup.
    "display_name": None,
    # Your apps as ACT shows them on a request card ("→ <app>"); `accept` takes only those. None = ask.
    "accept_for": None,
    # Apps whose Play Store download is bigger than this are not installed (MB). 0 = no limit.
    "max_app_size_mb": 100,
    # Seconds spent inside each app of the Today list.
    "seconds_per_app": 25,
}

ENV = {"display_name": "ACT_DISPLAY_NAME", "accept_for": "ACT_ACCEPT_FOR",
       "max_app_size_mb": "ACT_MAX_MB", "seconds_per_app": "ACT_SECONDS"}


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(PATH):
        with open(PATH) as f:
            cfg.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    for key, var in ENV.items():
        if os.environ.get(var):
            v = os.environ[var]
            cfg[key] = int(v) if isinstance(DEFAULTS[key], int) else v
    cfg["accept_for"] = apps(cfg["accept_for"])
    return cfg


def apps(value):
    """accept_for as a list: accepts a list, or one string with names separated by commas."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [x.strip() for x in items if x and x.strip()]


def save(**values):
    cfg = {}
    if os.path.exists(PATH):
        with open(PATH) as f:
            cfg = json.load(f)
    if values.get("accept_for") is not None:
        values["accept_for"] = apps(values["accept_for"])
    cfg.update({k: v for k, v in values.items() if k in DEFAULTS and v is not None})
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return load()

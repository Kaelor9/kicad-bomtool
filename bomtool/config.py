"""User settings (API keys etc.) stored in the user's home folder, never in the project."""
import json
import os

DEFAULTS = {
    "digikey_client_id": "", "digikey_client_secret": "", "digikey_customer_id": "",
    "mouser_key": "", "mouser_cart_key": "",
    "nexar_client_id": "", "nexar_client_secret": "",
    "currency": "DKK", "country": "DK", "check_updates": "1", "language": "en",
    # What the order really costs (Denmark, 2026): 25 % VAT; DigiKey kr. 185 below kr. 550, Mouser free from kr. 550.
    "vat_pct": "25", "freight_digikey": "185", "free_digikey": "550", "freight_mouser": "150", "free_mouser": "550",
}
SECRET_KEYS = ("digikey_client_secret", "mouser_key", "mouser_cart_key", "nexar_client_secret")


def app_dir():
    d = os.environ.get("BOMTOOL_HOME") or os.path.join(os.path.expanduser("~"), ".kicad_bomtool")
    os.makedirs(d, exist_ok=True)
    return d


def cache_dir():
    d = os.path.join(app_dir(), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(app_dir(), "config.json"), encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except (OSError, ValueError):
        pass
    return cfg


def save(update):
    cfg = load()
    for k, v in update.items():
        if k not in DEFAULTS:
            continue
        if k in SECRET_KEYS and isinstance(v, str) and v.startswith("••••"):
            continue  # masked value sent back unchanged
        cfg[k] = (v or "").strip()
    path = os.path.join(app_dir(), "config.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return cfg


def masked(cfg):
    out = dict(cfg)
    for k in SECRET_KEYS:
        if out.get(k):
            out[k] = "••••" + out[k][-4:]
    return out

"""Updates from GitHub Releases.

A release carries KiCadBOM.exe and KiCadBOM.exe.sha256. The running .exe can't
be overwritten on Windows, but it can be renamed: the old file becomes
KiCadBOM.old, the verified download takes its name, the new version is started
and the old file is deleted on the next start.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .net import urlopen
from . import __version__
from .config import app_dir

REPO = "Kaelor9/kicad-bomtool"
ASSET = "KiCadBOM.exe"
CHECK_EVERY = 6 * 3600
_cache = {"time": 0, "info": None}


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or "")[:3]) or (0,)


def frozen():
    return bool(getattr(sys, "frozen", False))


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"kicad-bomtool/{__version__}"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def check(force=False):
    """Latest release info: {current, latest, newer, notes, page, exe_url, sha_url, can_install, error}."""
    if not force and _cache["info"] and time.time() - _cache["time"] < CHECK_EVERY:
        return _cache["info"]
    info = {"current": __version__, "latest": None, "newer": False, "notes": "", "page": "",
            "can_install": frozen(), "error": ""}
    try:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        info["latest"] = rel.get("tag_name", "").lstrip("v")
        info["notes"] = (rel.get("body") or "")[:4000]
        info["page"] = rel.get("html_url", "")
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets") or []}
        info["exe_url"], info["sha_url"] = assets.get(ASSET), assets.get(ASSET + ".sha256")
        info["newer"] = _ver(info["latest"]) > _ver(__version__)
        if not (info["exe_url"] and info["sha_url"]):
            info["can_install"] = False
    except urllib.error.HTTPError as e:
        info["error"] = "Ingen udgivelser fundet endnu." if e.code == 404 else f"GitHub svarede {e.code}."
    except (urllib.error.URLError, OSError, ValueError) as e:
        info["error"] = f"Kunne ikke tjekke for opdateringer ({getattr(e, 'reason', e)})."
    _cache.update(time=time.time(), info=info)
    return info


def install():
    """Download, verify and swap in the new .exe, then start it. Returns a message; the caller exits."""
    info = check(force=True)
    if not info["newer"]:
        raise ValueError("Du har allerede den nyeste version.")
    if not frozen():
        raise ValueError("Programmet kører fra kildekoden – opdatér med 'git pull'.")
    if not info["can_install"]:
        raise ValueError("Udgivelsen mangler programfilen – hent den manuelt fra GitHub.")
    data = _get(info["exe_url"], "application/octet-stream")
    want = _get(info["sha_url"], "application/octet-stream").decode("ascii", "replace").split()[0].lower()
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise ValueError("Den hentede fil er beskadiget (checksum passer ikke) – intet er ændret.")
    exe = sys.executable
    new, old = exe + ".new", os.path.splitext(exe)[0] + ".old"
    with open(new, "wb") as fh:
        fh.write(data)
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)          # allowed while running
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)      # put the old one back
        raise
    # Without this the new .exe inherits PyInstaller's variables and tries to run
    # from the old version's (soon deleted) unpack folder instead of starting fresh.
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen([exe] + sys.argv[1:], close_fds=True, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return f"Opdateret til {info['latest']} – starter igen."


def cleanup():
    """Remove the previous version left behind by an update."""
    if frozen():
        old = os.path.splitext(sys.executable)[0] + ".old"
        for _ in range(10):
            try:
                if os.path.exists(old):
                    os.remove(old)
                break
            except OSError:
                time.sleep(0.5)   # the old process may still be closing


__all__ = ["check", "install", "cleanup", "app_dir", "REPO"]

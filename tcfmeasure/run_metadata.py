"""Records everything needed to reproduce a crawl (Demir et al.): date, location, versions,
configuration, Tranco list and Git commit. Written to run_metadata.json in the output directory."""
import importlib.metadata
import json
import platform
import subprocess
import urllib.request
from datetime import datetime, timezone

from tcfmeasure import config

IP_COUNTRY_URL = "https://ipinfo.io/country"


def git_commit():
    """Current commit and whether the working tree has uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=config.REPO_DIR, capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def ip_country():
    """Two-letter country code of the public IP of this machine, or None if the lookup fails."""
    try:
        with urllib.request.urlopen(IP_COUNTRY_URL, timeout=10) as response:
            return response.read().decode().strip() or None
    except Exception:
        return None


def openwpm_version():
    return (config.REPO_DIR / "VERSION").read_text().strip()


def package_version(name):
    """Version of an installed package (selenium's own __version__ is wrong in 4.16.0)."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def settings_from_config():
    return {name: (str(value) if not isinstance(value, (int, float, bool)) else value)
            for name, value in vars(config).items() if name.isupper()}


def new_metadata(script_name, **extra):
    return {
        "script": script_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ip_country": ip_country(),
        "git": git_commit(),
        "openwpm_version": openwpm_version(),
        "python_version": platform.python_version(),
        "packages": {name: package_version(name) for name in ("selenium", "protego", "tldextract")},
        "platform": platform.platform(),
        "config": settings_from_config(),
        **extra,
    }


def write_metadata(metadata, output_dir):
    path = output_dir / "run_metadata.json"
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return path

#!/usr/bin/env python3
"""
setup.py — Interactive setup for the Ghost skill.
Run this after installing the skill to configure credentials and behavior.

Usage: python3 scripts/setup.py
"""

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

# No subprocess usage in this file — pip installs must be done manually.

SKILL_DIR   = Path(__file__).resolve().parent.parent
CONFIG_FILE = SKILL_DIR / "config.json"
CREDS_FILE  = Path.home() / ".openclaw" / "secrets" / "ghost_creds"

# ─── Dependency check ─────────────────────────────────────────────────────────

def _ensure_requests():
    try:
        import requests  # noqa: F401
    except ImportError:
        print("✗ Missing dependency: 'requests' is not installed.")
        print("  Install it with:  pip install requests")
        print("  Then re-run:      python3 scripts/setup.py")
        sys.exit(1)

_ensure_requests()

_DEFAULT_CONFIG = {
    "allow_publish":       True,
    "allow_delete":        False,
    "allow_member_access": False,
    "default_status":      "draft",
    "default_tags":        [],
    "readonly_mode":       False,
}


def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    display = f"[{'***' if secret else default}] " if default else ""
    try:
        if secret:
            import getpass
            val = getpass.getpass(f"  {prompt} {display}: ")
        else:
            val = input(f"  {prompt} {display}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)
    return val if val else default


def _ask_bool(prompt: str, default: bool, hint: str = "") -> bool:
    default_str = "Y/n" if default else "y/N"
    hint_str    = f"  ({hint})" if hint else ""
    try:
        val = input(f"  {prompt}{hint_str} [{default_str}]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)
    return (val.startswith("y") if val else default)


def _load_existing_creds() -> dict:
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds


def _load_existing_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg


def _write_creds(ghost_url: str, admin_key: str):
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDS_FILE.write_text(f"GHOST_URL={ghost_url}\nGHOST_ADMIN_KEY={admin_key}\n")
    CREDS_FILE.chmod(0o600)


def _write_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_jwt(key_id: str, secret_hex: str) -> str:
    now = int(time.time())
    header  = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": now, "exp": now + 300, "aud": "/admin/"}
    h = _b64url(json.dumps(header,  separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(bytes.fromhex(secret_hex), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def _test_connection(ghost_url: str, admin_key: str) -> tuple:
    """Returns (success: bool, info: str)."""
    try:
        import requests
        parts = admin_key.split(":")
        if len(parts) != 2:
            return False, "Invalid key format (expected id:secret_hex)"
        try:
            bytes.fromhex(parts[1])
        except ValueError:
            return False, "Invalid key: secret part is not valid hex"
        token = _make_jwt(parts[0], parts[1])
        r = requests.get(
            f"{ghost_url.rstrip('/')}/ghost/api/admin/site",
            headers={"Authorization": f"Ghost {token}", "Accept-Version": "v5.0"},
            timeout=10,
        )
        if r.status_code == 200:
            title = r.json().get("site", {}).get("title", "Ghost")
            return True, title
        return False, f"HTTP {r.status_code}: {r.text[:120]}"
    except Exception as e:
        return False, str(e)


def main():
    print("┌─────────────────────────────────────────┐")
    print("│   Ghost Skill — Setup                   │")
    print("└─────────────────────────────────────────┘")

    # ── Step 1: Credentials ────────────────────────────────────────────────────
    print("\n● Step 1/2 — Credentials\n")

    existing = _load_existing_creds()
    ghost_url = admin_key = ""

    if existing:
        print(f"  Existing credentials found in {CREDS_FILE}")
        if not _ask_bool("Update credentials?", default=False):
            ghost_url = existing.get("GHOST_URL",       "")
            admin_key = existing.get("GHOST_ADMIN_KEY", "")
            print("  → Keeping existing credentials.")
        else:
            existing = {}

    if not existing:
        print(f"  Credentials will be saved to {CREDS_FILE} (chmod 600)\n")
        print("  To get your Admin API Key:")
        print("  → Ghost Admin → Settings → Integrations")
        print("  → Add custom integration (or select existing)")
        print("  → Copy the Admin API Key  (format: id:secret_hex)\n")

        ghost_url = _ask("Ghost URL", default="https://your-ghost.example.com").rstrip("/")
        admin_key = _ask("Admin API Key (id:secret_hex)", secret=True)

        print("\n  Testing connection...", end=" ", flush=True)
        ok, info = _test_connection(ghost_url, admin_key)
        if ok:
            print(f"✓ Connected — site: \"{info}\"")
        else:
            print(f"✗ Failed — {info}")
            if not _ask_bool("  Save credentials anyway?", default=False):
                print("  Aborted — no files written.")
                sys.exit(1)

        _write_creds(ghost_url, admin_key)
        print(f"  ✓ Saved to {CREDS_FILE}")

    # ── Step 2: Permissions ────────────────────────────────────────────────────
    print("\n● Step 2/2 — Permissions\n")
    print("  Configure what operations the agent is allowed to perform.\n")

    cfg = _load_existing_config()

    print("  ── Content creation & editing ──")
    cfg["allow_publish"] = _ask_bool(
        "Allow publishing posts and pages?",
        default=cfg.get("allow_publish", True),
        hint="false = drafts only, agent cannot publish",
    )
    cfg["allow_delete"] = _ask_bool(
        "Allow deleting posts, pages, and tags?",
        default=cfg.get("allow_delete", False),
        hint="recommended: false unless you trust the agent fully",
    )

    print("\n  ── Default behavior ──")
    status_input = _ask(
        "Default status for new posts/pages",
        default=cfg.get("default_status", "draft"),
    ).lower()
    cfg["default_status"] = status_input if status_input in ("draft", "published", "scheduled") else "draft"

    tags_raw = _ask(
        "Default tags always added to new posts (comma-separated, leave empty = none)",
        default=",".join(
            t if isinstance(t, str) else t.get("name", "")
            for t in cfg.get("default_tags", [])
        ),
    )
    cfg["default_tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw.strip() else []

    print("\n  ── Optional access ──")
    cfg["allow_member_access"] = _ask_bool(
        "Allow reading and writing member data?",
        default=cfg.get("allow_member_access", False),
        hint="required for member list, creation, update",
    )

    print("\n  ── Safety ──")
    cfg["readonly_mode"] = _ask_bool(
        "Enable readonly mode? (overrides all above — no writes at all)",
        default=cfg.get("readonly_mode", False),
    )

    _write_config(cfg)
    print(f"\n  ✓ Config saved to {CONFIG_FILE}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n┌─────────────────────────────────────────┐")
    print("│   Setup complete ✓                      │")
    print("└─────────────────────────────────────────┘")
    print(f"\n  Instance       : {ghost_url}")
    ro = cfg['readonly_mode']
    print(f"  Publish        : {'✓' if cfg['allow_publish']       and not ro else '✗'}")
    print(f"  Delete         : {'✓' if cfg['allow_delete']        and not ro else '✗'}")
    print(f"  Member access  : {'✓' if cfg['allow_member_access'] and not ro else '✗'}")
    print(f"  Default status : {cfg['default_status']}")
    tags_display = ", ".join(
        t if isinstance(t, str) else t.get("name", "") for t in cfg["default_tags"]
    ) or "(none)"
    print(f"  Default tags   : {tags_display}")
    print(f"  Readonly       : {'⚠ ON — all writes blocked' if ro else '✗ off'}")
    print()
    print("  Run init.py to validate that all permissions work:")
    print("    python3 scripts/init.py")
    print()


if __name__ == "__main__":
    main()

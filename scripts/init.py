#!/usr/bin/env python3
"""
init.py — Validate the Ghost skill configuration.
Tests the connection and each configured permission against the real instance.
All test artifacts are cleaned up automatically.

Usage: python3 scripts/init.py
"""

import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ghost import GhostClient, GhostError, PermissionDeniedError, _make_jwt

SKILL_DIR   = Path(__file__).resolve().parent.parent
CONFIG_FILE = SKILL_DIR / "config.json"
CREDS_FILE  = Path.home() / ".openclaw" / "secrets" / "ghost_creds"
LOG_DIR     = SKILL_DIR / ".skill-logs"

TEST_TITLE = "[skill-init-test] DELETE ME"
TEST_TAG   = "__skill-init-test__"


class Results:
    def __init__(self):
        self.passed  = []
        self.failed  = []
        self.skipped = []
        self._entries = []

    def _record(self, status: str, label: str, detail: str = ""):
        self._entries.append({
            "ts":     datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": status,
            "check":  label,
            "detail": detail,
        })

    def ok(self, label: str, detail: str = ""):
        self.passed.append(label)
        self._record("pass", label, detail)
        suffix = f"  {detail}" if detail else ""
        print(f"  ✓  {label}{suffix}")

    def fail(self, label: str, reason: str = ""):
        self.failed.append(label)
        self._record("fail", label, reason)
        suffix = f"  → {reason}" if reason else ""
        print(f"  ✗  {label}{suffix}")

    def skip(self, label: str, reason: str = ""):
        self.skipped.append(label)
        self._record("skip", label, reason)
        print(f"  ~  {label}  (skipped: {reason})")

    def summary(self):
        total   = len(self.passed) + len(self.failed)
        skipped = len(self.skipped)
        print(f"\n  {len(self.passed)}/{total} checks passed", end="")
        if skipped:
            print(f", {skipped} skipped (disabled in config)", end="")
        print()
        if self.failed:
            print("\n  Failed checks:")
            for f in self.failed:
                print(f"    ✗  {f}")

    def write_log(self):
        """Append structured results to .skill-logs/init.jsonl"""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_file = LOG_DIR / "init.jsonl"
            run_entry = {
                "ts":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "skill":   "ghost",
                "passed":  len(self.passed),
                "failed":  len(self.failed),
                "skipped": len(self.skipped),
                "checks":  self._entries,
            }
            with log_file.open("a") as f:
                f.write(json.dumps(run_entry) + "\n")
            print(f"\n  Log written → {log_file}")
        except Exception as e:
            print(f"\n  (Log write failed: {e})")


def main():
    print("┌─────────────────────────────────────────┐")
    print("│   Ghost Skill — Init Check              │")
    print("└─────────────────────────────────────────┘")

    # ── Pre-flight ─────────────────────────────────────────────────────────────
    if not CREDS_FILE.exists():
        print(f"\n✗ Credentials not found: {CREDS_FILE}")
        print("  Run setup.py first:  python3 scripts/setup.py")
        sys.exit(1)

    try:
        gc = GhostClient()
    except GhostError as e:
        print(f"\n✗ {e}")
        sys.exit(1)

    cfg = gc.cfg
    ro  = cfg.get("readonly_mode", False)
    r   = Results()

    test_post_id = None
    test_tag_id  = None

    # ── 1. Connection + site info ──────────────────────────────────────────────
    print("\n● Connection\n")
    try:
        site = gc.get_site()
        r.ok("Connect", f"site=\"{site.get('title','?')}\"  version={site.get('version','?')}")
    except Exception as e:
        r.fail("Connect", str(e))
        print("\n  Cannot proceed without a valid connection. Check credentials.")
        r.summary()
        sys.exit(1)

    # ── 2. Read ────────────────────────────────────────────────────────────────
    print("\n● Read permissions\n")
    try:
        result = gc.list_posts(limit=1, status="all", fields="id,title,status")
        posts  = result.get("posts", [])
        total  = result.get("meta", {}).get("pagination", {}).get("total", "?")
        r.ok("Read posts", f"{total} post(s) on this instance")
    except Exception as e:
        r.fail("Read posts", str(e))

    try:
        result = gc.list_tags(limit=1)
        total  = result.get("meta", {}).get("pagination", {}).get("total", "?")
        r.ok("Read tags", f"{total} tag(s) on this instance")
    except Exception as e:
        r.fail("Read tags", str(e))

    # ── 3. Write: create draft post ────────────────────────────────────────────
    print("\n● Write permissions\n")

    if ro:
        r.skip("Write (create draft)", "readonly_mode=true")
    else:
        try:
            post = gc.create_post(
                title=TEST_TITLE,
                html="<p>Automated skill init check — safe to delete.</p>",
                status="draft",
            )
            test_post_id = post.get("id")
            r.ok("Write (create draft)", f"id={test_post_id}")
        except Exception as e:
            r.fail("Write (create draft)", str(e))

    # ── 4. Update ──────────────────────────────────────────────────────────────
    if test_post_id and not ro:
        try:
            gc.update_post(test_post_id, custom_excerpt="init check excerpt")
            r.ok("Write (update post)")
        except Exception as e:
            r.fail("Write (update post)", str(e))

    # ── 5. Publish ─────────────────────────────────────────────────────────────
    if not cfg.get("allow_publish", True):
        r.skip("Publish / Unpublish", "allow_publish=false")
    elif ro:
        r.skip("Publish / Unpublish", "readonly_mode=true")
    elif test_post_id:
        try:
            gc.publish_post(test_post_id)
            r.ok("Publish post")
        except Exception as e:
            r.fail("Publish post", str(e))

        try:
            gc.unpublish_post(test_post_id)
            r.ok("Unpublish post (→ draft)")
        except Exception as e:
            r.fail("Unpublish post", str(e))
    else:
        r.skip("Publish / Unpublish", "no test post created (write check failed)")

    # ── 6. Tags ────────────────────────────────────────────────────────────────
    if ro:
        r.skip("Write (create tag)", "readonly_mode=true")
    else:
        try:
            tag = gc.create_tag(TEST_TAG, description="skill init test — safe to delete")
            test_tag_id = tag.get("id")
            r.ok("Write (create tag)", f"id={test_tag_id}")
        except Exception as e:
            r.fail("Write (create tag)", str(e))

    # ── 7. Delete ──────────────────────────────────────────────────────────────
    print("\n● Delete permissions\n")

    if not cfg.get("allow_delete", False):
        r.skip("Delete (post)", "allow_delete=false")
        r.skip("Delete (tag)",  "allow_delete=false")
        # Clean up via direct API call (bypassing config check) since this is
        # an init script, not normal agent usage
        if test_post_id:
            try:
                import requests
                token = _make_jwt(gc._key_id, gc._secret_hex)
                requests.delete(
                    f"{gc.api_url}/posts/{test_post_id}",
                    headers={"Authorization": f"Ghost {token}", "Accept-Version": "v5.0"},
                )
            except Exception:
                print(f"  ⚠  Test post {test_post_id} could not be cleaned up. Delete manually.")
        if test_tag_id:
            try:
                import requests
                token = _make_jwt(gc._key_id, gc._secret_hex)
                requests.delete(
                    f"{gc.api_url}/tags/{test_tag_id}",
                    headers={"Authorization": f"Ghost {token}", "Accept-Version": "v5.0"},
                )
            except Exception:
                print(f"  ⚠  Test tag {test_tag_id} could not be cleaned up. Delete manually.")
    elif ro:
        r.skip("Delete (post)", "readonly_mode=true")
        r.skip("Delete (tag)",  "readonly_mode=true")
    else:
        if test_post_id:
            try:
                gc.delete_post(test_post_id)
                test_post_id = None
                r.ok("Delete (post)")
            except Exception as e:
                r.fail("Delete (post)", str(e))
        else:
            r.skip("Delete (post)", "no test post to delete")

        if test_tag_id:
            try:
                gc.delete_tag(test_tag_id)
                test_tag_id = None
                r.ok("Delete (tag)")
            except Exception as e:
                r.fail("Delete (tag)", str(e))
        else:
            r.skip("Delete (tag)", "no test tag to delete")

    # ── 8. Members ─────────────────────────────────────────────────────────────
    print("\n● Optional permissions\n")

    if not cfg.get("allow_member_access", False):
        r.skip("Members (list)", "allow_member_access=false")
    else:
        try:
            result = gc.list_members(limit=1)
            total  = result.get("meta", {}).get("pagination", {}).get("total", "?")
            r.ok("Members (list)", f"{total} member(s)")
        except Exception as e:
            r.fail("Members (list)", str(e))

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n┌─────────────────────────────────────────┐")
    print("│   Init check complete                   │")
    print("└─────────────────────────────────────────┘")
    r.summary()

    r.write_log()

    if r.failed:
        print("\n  Review config.json and ghost_creds, then re-run setup.py.\n")
        sys.exit(1)
    else:
        print("\n  Skill is ready to use. ✓\n")


if __name__ == "__main__":
    main()

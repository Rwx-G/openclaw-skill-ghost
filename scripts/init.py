#!/usr/bin/env python3
"""
init.py — Validate the Ghost skill configuration.
Tests the connection and each configured permission against the real instance.
All test artifacts are cleaned up automatically.

Usage: python3 scripts/init.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ghost import GhostClient, GhostError, PermissionDeniedError

SKILL_DIR   = Path(__file__).resolve().parent.parent
CONFIG_FILE = SKILL_DIR / "config.json"
CREDS_FILE  = Path.home() / ".openclaw" / "secrets" / "ghost_creds"


TEST_TITLE = "[skill-init-test] DELETE ME"
TEST_TAG   = "__skill-init-test__"


class Results:
    def __init__(self):
        self.passed  = []
        self.failed  = []
        self.skipped = []

    def ok(self, label: str, detail: str = ""):
        self.passed.append(label)
        suffix = f"  {detail}" if detail else ""
        print(f"  ✓  {label}{suffix}")

    def fail(self, label: str, reason: str = ""):
        self.failed.append(label)
        suffix = f"  → {reason}" if reason else ""
        print(f"  ✗  {label}{suffix}")

    def skip(self, label: str, reason: str = ""):
        self.skipped.append(label)
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

    # ── 7. Delete permissions (user content) ──────────────────────────────────
    print("\n● Delete permissions\n")

    if not cfg.get("allow_delete", False):
        r.skip("Delete (post)", "allow_delete=false")
        r.skip("Delete (tag)",  "allow_delete=false")
    elif ro:
        r.skip("Delete (post)", "readonly_mode=true")
        r.skip("Delete (tag)",  "readonly_mode=true")
    else:
        r.ok("Delete enabled", "allow_delete=true")

    # ── 7b. Cleanup — always remove test artifacts ─────────────────────────────
    print("\n● Cleanup (test artifacts)\n")

    if ro:
        if test_post_id or test_tag_id:
            print(f"  ℹ  readonly_mode=true — test artifacts not created, no cleanup needed.")
    else:
        if test_post_id:
            try:
                gc._force_delete(f"posts/{test_post_id}")
                test_post_id = None
                r.ok("Cleanup (delete test post)")
            except Exception as e:
                r.fail("Cleanup (delete test post)", str(e))
                print(f"     ⚠  Manual cleanup needed: Ghost Admin > Posts > delete \"{TEST_TITLE}\"")
        else:
            r.skip("Cleanup (delete test post)", "no test post created")

        if test_tag_id:
            try:
                gc._force_delete(f"tags/{test_tag_id}")
                test_tag_id = None
                r.ok("Cleanup (delete test tag)")
            except Exception as e:
                r.fail("Cleanup (delete test tag)", str(e))
                print(f"     ⚠  Manual cleanup needed: Ghost Admin > Tags > delete \"{TEST_TAG}\"")
        else:
            r.skip("Cleanup (delete test tag)", "no test tag created")

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

    if r.failed:
        print("\n  Review config.json and ghost_creds, then re-run setup.py.\n")
        sys.exit(1)
    else:
        print("\n  Skill is ready to use. ✓\n")


if __name__ == "__main__":
    main()

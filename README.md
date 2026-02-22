# 👻 openclaw-skill-ghost

> OpenClaw skill — Ghost CMS content management via Admin API v5

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenClaw](https://img.shields.io/badge/OpenClaw-skill-blue)](https://openclaw.ai)
[![ClawHub](https://img.shields.io/badge/ClawHub-ghost-green)](https://clawhub.ai/rwx-g/ghost)

Full Ghost Admin API v5 client for OpenClaw agents. Covers posts, pages, tags, images, members, and newsletters. JWT auth generated from stdlib — no external dependencies beyond `requests`. Includes interactive setup wizard, connection + permission validation, and a behavior restriction system via `config.json`.

## Install

```bash
clawhub install ghost
```

Or manually:

```bash
git clone https://github.com/rwx-g/openclaw-skill-ghost \
  ~/.openclaw/workspace/skills/ghost
```

## Setup

```bash
python3 scripts/setup.py   # credentials + permissions + connection test
python3 scripts/init.py    # validate all configured permissions
```

You'll need a Ghost **Admin API Key**: Ghost Admin → Settings → Integrations → Add custom integration.

## What it can do

| Category | Operations |
|----------|-----------|
| Posts | create, read, update, publish, unpublish, list |
| Pages | create, read, update, publish, unpublish, list |
| Tags | create, read, update, delete, list |
| Images | upload (jpg, png, gif, svg, webp) |
| Members | list, create, update, delete (opt-in) |
| Newsletters | list, read |
| Tiers | list |
| Site | read settings, version |

## Configuration

Credentials → `~/.openclaw/secrets/ghost_creds` (chmod 600, never committed)

Behavior → `config.json` in skill directory:

```json
{
  "allow_publish": false,
  "allow_delete": false,
  "allow_member_access": false,
  "default_status": "draft",
  "default_tags": [],
  "readonly_mode": false
}
```

## Requirements

- Python 3.9+
- `requests` (`pip install requests`)
- Network access to Ghost instance (self-hosted or Ghost Pro)

## Documentation

- [SKILL.md](SKILL.md) — full skill instructions, CLI reference, templates
- [references/api.md](references/api.md) — Ghost Admin API endpoint reference + NQL filters
- [references/troubleshooting.md](references/troubleshooting.md) — common errors and fixes

## License

[MIT](LICENSE)

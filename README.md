# Claude skills

Source repo for my Claude skills. Each subdirectory is one skill (a folder with a `SKILL.md` plus optional `scripts/` and `references/`).

## Skills

| Skill | Description |
|---|---|
| [gtfs-explorer](gtfs-explorer/SKILL.md) | Load, parse, and query GTFS Schedule feeds (public-transit static data). |

## Packaging

To package a skill into an installable `.skill` file:

```bash
cd ~/.claude/skills/skill-creator
python3 -m scripts.package_skill /Users/massimomeert/code/skills/<skill-name>
```

The output `.skill` file lands in `~/.agents/skills/skill-creator/`.

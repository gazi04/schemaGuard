# SchemaGuard

SchemaGuard reads the database migrations in a backend pull request, maps the changed tables and columns to the data team's dbt sources through `manifest.json`, walks dbt lineage downstream, and reports breaking changes as a PR comment and an exit code.

**Status:** work in progress, Phase 3 (config and impact analyzer). `schemaguard parse <file>`, `schemaguard lineage <source>.<table> --manifest <path>` and `schemaguard check [FILES]... --config schemaguard.yml` work; `check` prints plain results and has no severity or `fail_on` exit code yet. See `docs/roadmap.md`.

## Docs

- `docs/architecture.md`: design, decisions, tech stack, known limitations
- `docs/roadmap.md`: phased plan and progress
- `docs/project-report.txt`: original project report

## Development

```bash
uv sync
uv run pytest
uv run pyright
uv run ruff check .
```

The full README (demo GIF, setup steps, metrics, known limitations) is written in Phase 6.

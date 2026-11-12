# SchemaGuard — Architecture and Tech Stack

Status: agreed design, Oct 7, 2026. Last updated Nov 11, 2026. Phases 1 (parsers), 2 (dbt side), 3 (config, analyzer, severity, scenario suite) and 4 (reporting) are built: 4.1 is done (terminal report in `report/terminal.py`, JSON in `report/json_report.py`, `check --format text|json`), 4.2 is done (markdown PR comment in `report/markdown.py` + `report/templates/comment.md.j2`, `check --format markdown`), 4.3 is done (`fail_on` threshold via `should_fail`, `check --fail-on`, exit 1). 5.1 (`github/`), 5.2 (`action.yml`, `check --pr`) and 5.3 (demo workflow, `check --base`) are done; 5.4 is next.

## What SchemaGuard does

SchemaGuard reads a database migration in a backend pull request, finds which dbt models depend on the changed tables and columns, and warns the developer in the PR before anything breaks.

It runs as a CLI (`schemaguard check ...`). The GitHub Action is a thin wrapper around that same command.

## The three inputs

| Input | Where it comes from | What it tells SchemaGuard |
|---|---|---|
| Migration files | The backend PR | What is changing, e.g. "rename `users.signup_date`" |
| `manifest.json` | The data team's dbt repo, copied into the backend repo or downloaded in CI | Who reads what: models, sources, tests, exposures, lineage, compiled SQL |
| `schemaguard.yml` | The backend repo, written once | How backend table names map to dbt sources, where the manifest is, and when to fail |

SchemaGuard never looks at the data repo directly. It only reads a snapshot of its `manifest.json`.

The manifest must come from `dbt compile` or `dbt build`, not only `dbt parse`. Otherwise `compiled_code` is empty.

## Guiding rule

**The core does no I/O.** Parsing, matching and analysis are pure functions: data in, data out. Reading files, calling GitHub and printing happen only at the edges (the CLI and the `github/` module). That makes the core easy to test with fixtures.

## Modules and data flow

```
            INPUTS                       CORE (pure functions)                   OUTPUTS
 ┌──────────────────────┐
 │ migration files      │──► migrations/ ──► ChangeSet ──┐
 │ (Alembic .py, .sql)  │     alembic.py                 │
 └──────────────────────┘     sql.py                     │
                                                         ▼
 ┌──────────────────────┐                          impact/ ──► ImpactReport ──► report/ ──► terminal
 │ schemaguard.yml      │──► config/ ──► Config ──►  analyzer.py                    terminal.py  JSON file
 └──────────────────────┘                          severity.py                     json.py      PR comment text
                                                         ▲                         markdown.py
 ┌──────────────────────┐                                │                             │
 │ manifest.json        │──► dbt/ ──► DbtProject ────────┘                             ▼
 └──────────────────────┘     manifest.py (load)                                 github/ ──► posts comment
                              lineage.py  (graph)                                cli exit code ──► pass/fail
                              columns.py  (who reads which column)
```

| Module | Job | Input → output |
|---|---|---|
| `migrations/` | Turn migration files into a normalized list of changes | files → `ChangeSet` |
| `config/` | Load and validate `schemaguard.yml` | YAML → `Config` |
| `dbt/` | Load the manifest, walk lineage, find which models read which source columns | `manifest.json` → `DbtProject` |
| `impact/` | **The core.** Map changes to dbt sources, find affected models, tests and exposures, assign severity | `ChangeSet` + `Config` + `DbtProject` → `ImpactReport` |
| `report/` | Render the report | `ImpactReport` → terminal text / JSON / markdown |
| `github/` | Post or update the PR comment. The only module that talks to GitHub | markdown → API call |
| `cli.py` | Typer commands, wiring, exit code | — |

Key properties:

- Imports point inward to `impact/`: `impact/` may import `migrations/`, `dbt/` and `config/` (e.g. `FailOn` for `should_fail`); `report/` imports `impact/`; only `cli.py` and `github/` sit on top. Nothing imports `cli.py`.
- `migrations/` and `dbt/` don't know about each other. They meet only in `impact/`, so each side can be built and tested alone.
- The Alembic parser and the SQL parser both output the same `ChangeSet`. `impact/` doesn't care where a change came from.

## Design decisions

### Change types (MVP)

| Change type | Example |
|---|---|
| `drop_column` | `op.drop_column("users", "signup_date")` |
| `rename_column` | `op.alter_column("users", "signup_date", new_column_name="created_at")` |
| `alter_type` | `op.alter_column("users", "age", type_=sa.BigInteger())` |
| `alter_nullability` | `op.alter_column("users", "email", nullable=True)`; a single type with a `nullable` field |
| `drop_table` | `op.drop_table("users")` |
| `rename_table` | `op.rename_table("users", "accounts")` |
| `add_column` | `op.add_column("users", sa.Column("created_at", ...))`. Safe on its own; kept so drop + add can be flagged as a possible rename |

Raw SQL equivalents (`ALTER TABLE ... DROP COLUMN`, `RENAME COLUMN`, `ADD COLUMN`, `ALTER COLUMN ... TYPE`, `SET/DROP NOT NULL`, `DROP TABLE`, `ALTER TABLE ... RENAME TO`) map to the same types. `DROP TABLE a, b` gives one change per table.

### The `ChangeSet` shape

Defined in `migrations/changes.py` as frozen Pydantic models:

- `SchemaChange`: `kind`, `table`, `source_file`, `line`, plus optional `column`, `new_name`, `new_type`, `old_type` and `nullable`. Only the fields that apply to the kind are set. `old_type` stays `None` for raw SQL, because the DDL doesn't say what the old type was.
- `NotAnalyzed`: `reason`, `source_file`, `line`.
- `ChangeSet`: a tuple of `changes` and a tuple of `not_analyzed`.

`table` is the bare table name (`.name` in sqlglot): `public.orders` becomes `orders`. Both parsers must use the same format, because `impact/` matches on this string.

### Severity

| Severity | Rule |
|---|---|
| **Breaking** | A dropped or renamed column that a model or a source test references; a dropped or renamed table that a dbt source points to |
| **Risky** | A type change on a column in use; a column in use becoming **nullable** (downstream `not_null` tests and assumptions may fail) |
| **Safe** | Changes to columns nothing downstream reads; a column becoming NOT NULL; additive changes |

Two extra markers appear next to a severity:

- **uncertain**: the match is based on table-level lineage, not column-level, e.g. because of `SELECT *` or SQL that couldn't be parsed.
- **possible rename**: a drop and an add on the same table in one migration. Alembic autogenerate writes renames this way.

Severity rules (decided in 3.3, Nov 2):

- Severity is computed per `ChangeImpact` from its change kind and whether anything reads the change: an affected model or a matching source test (`classify(change, affected)` in `impact/severity.py`, called with `bool(models or tests)`). A source test counts because `dbt build` fails when its column is dropped, and a `not_null` test fails when the column becomes nullable. It is a `computed_field`, like `uncertain`, so it can't disagree with the data.
- `drop_table` and `rename_table` are always breaking, even with no affected models: the dbt source itself points at the old table.
- Column changes with no affected models and no matching source tests are safe. Otherwise: `drop_column` / `rename_column` are breaking, `alter_type` is risky, becoming nullable is risky, becoming NOT NULL is safe. A nullability change with no `nullable` value is treated as risky. `add_column` is always safe.
- `uncertain` is a marker only and never lowers the severity: a `SELECT *` model hit by a dropped column is breaking (uncertain). Missing a real break is worse than a false alarm, so `fail_on` counts uncertain impacts at full severity.
- **possible rename** is flagged on a `drop_column` when the same migration file has an `add_column` on the same table (case-insensitive). Line order doesn't matter, and the drop stays breaking. It is a stored field (`ChangeImpact.possible_rename`) set by `analyze()`, because one change alone can't tell.
- `Severity` is a `StrEnum` (`safe`, `risky`, `breaking`), so it shows as a name in JSON. String comparison would sort it alphabetically (`breaking < risky < safe`), so ordering goes through `Severity.rank`. `ImpactReport.worst` is the highest severity across impacts, `safe` when there are none; `should_fail` compares it to `fail_on`.

### Unknown input is reported, never ignored

When the Alembic parser hits loops, helper functions or calls it doesn't recognize, it adds a `not_analyzed` entry to the `ChangeSet` instead of failing. The PR comment then shows "couldn't check this", so a skipped check is never a silent pass.

The SQL parser follows the same rule, and is strict: every statement or `ALTER` action that isn't one of the change kinds above becomes `not_analyzed`. That includes harmless ones like `CREATE INDEX`, `UPDATE`, `BEGIN`/`COMMIT` and constraint changes. Nothing is ignored on purpose; only empty input (no statement at all) produces nothing. Reducing the noise is left to the report (Phase 4), not the parser.

Each `not_analyzed` reason is a category plus the SQL, for example `DROP VIEW not checked: DROP VIEW v`, so a reviewer can find the statement. The SQL is squashed to one line and cut to 80 characters (`MAX_SQL_LENGTH` in `migrations/sql.py`).

Only `upgrade()` is read. `downgrade()` is ignored. Strings passed to `op.execute(...)` go to the SQL parser.

### Name mapping happens in the analyzer

Backend names (`public.users`) are translated to dbt sources (`app.users`) in `impact/`, using `schemaguard.yml`. The parsers know nothing about dbt.

Analyzer rules (decided in 3.2):

- Each changed table is either ignored (in `ignore`: skipped), mapped (a key in `sources`) or unmapped. Unmapped changes are kept in `ImpactReport.unmapped`, never dropped.
- A mapped `SourceRef` that isn't in the manifest raises `AnalyzerError`: the config and the manifest disagree, so the run stops (exit 2).
- Table and column names are compared case-insensitively here, because Postgres folds unquoted names. The parsers and `dbt/` stay exact.
- `rename_table` (and every other change) is looked up by its old name, the one the dbt source still points to.
- Downstream is walked from the affected first-hop models, not from the source. An uncertain first-hop model counts as affected, and everything downstream of it is uncertain too.
- Tests attached to the source count when their `column_name` matches the change, or when the change is table-level.
- Tests attached to an affected model always count, whatever their `column_name`: column matching stops at the first hop. Exposures count when they hang off an affected model.
- A mapped change with no affected models still gets a `ChangeImpact` (with empty `models`), so the report can show it was checked. Deciding it's safe is the severity step's job.

`ImpactReport` (`impact/analyzer.py`) holds `impacts` (one `ChangeImpact` per mapped change: the `SchemaChange`, its `SourceRef`, the affected models as `AffectedModel(unique_id, name, depth, uncertain)`, test ids and exposure names), `unmapped` and `not_analyzed` (copied from the `ChangeSet`). `ChangeImpact.uncertain` is computed from its models, so it can't disagree with them.

### Column lineage only at the first hop

If a model fails, everything downstream of it is skipped regardless of columns. So:

- **First hop** (models that read the source directly): column-level. Parse each model's `compiled_code` with sqlglot and list the source columns it references.
- **Everything after that**: table-level, by walking `child_map`.
- `SELECT *` from a source counts as "reads every column" and is marked uncertain.
- Sources are looked up by their dbt `name`, but compiled SQL is matched against the source's `identifier` (the real warehouse table name). Using `name` there would miss a `SELECT *` and report it as certain.

### Config format

```yaml
# schemaguard.yml, in the backend repo
manifest: dbt/manifest.json        # default: target/manifest.json
migrations: alembic/versions       # default: alembic/versions
sources:                           # required, at least one entry
  customers: ecom.raw_customers    # backend table -> <source>.<table> in dbt
  orders: ecom.raw_orders
ignore:                            # default: none
  - alembic_version
fail_on: breaking                  # breaking | risky | never (default: breaking)
```

Rules (finalized in 3.1):

- **Keys are bare table names** (`customers`, not `public.customers`), the same form both parsers emit. Schema-qualified keys would never match a change.
- Each `sources` value must have the shape `<source>.<table>` with both parts non-empty. It is parsed into a `SourceRef(source_name, table_name)`. Whether the source exists is checked against the manifest in 3.2, not here.
- Unknown keys (`fail_ob: never`) are errors, not ignored.
- A table can't be in both `ignore` and `sources`: that is a contradiction, and silently picking one could hide a breaking change.
- `manifest` and `migrations` are relative to the folder of `schemaguard.yml`, not to the current directory. The config keeps them as plain strings; the CLI resolves them.
- Loading uses `yaml.safe_load`, because the file comes from the PR under review. An empty file is an error. Every problem is raised as one `ConfigError`.

### `schemaguard check`

Decided in 3.2 step 8 (Oct 31):

- Usage: `schemaguard check [FILES]... [--config schemaguard.yml] [--format/-f text|json|markdown] [--fail-on breaking|risky|never] [--pr N] [--base REF]`. `--config` defaults to `schemaguard.yml` in the current folder.
- With `FILES`, only those migration files are checked (relative to the current folder, like `parse`). This is what CI will pass: the migrations changed in the PR.
- With `--base REF` (decided Nov 11, roadmap 5.3), only the migration files in the `migrations` folder that differ from `REF` are checked: `git diff --name-only -z --relative --diff-filter=d --end-of-options REF -- .` run inside the folder, intersected with the no-`FILES` list below. Deleted files are skipped; untracked files are not seen. No changed migration gives an empty report (`No changes found.`, exit 0). `--base` with `FILES`, a failing `git diff` or no `git` on `PATH` exits 2. This is what the Action uses.
- Without `FILES`, every `.py` / `.sql` file directly in the config's `migrations` folder is checked, sorted by name. Names starting with `__` and subfolders are skipped. Handy locally, noisy on a repo with history.
- `manifest` and `migrations` are joined to the config file's folder; absolute paths stay absolute.
- Exit codes: `0` when the check ran and `worst` is below the `fail_on` threshold (always with `never`); `1` when `worst` reaches it; `2` for a missing or invalid config, a missing or invalid manifest, a missing migrations folder, a file that isn't `.py` / `.sql`, an `AnalyzerError`, or a bad option value. The report is always printed before exit 1, in every format.
- `--fail-on` overrides the config's `fail_on` for one run (decided in 4.3, Nov 7).
- Unmapped changes and `not_analyzed` entries never fail the run; they only show in the report. Failing on them would make every `CREATE INDEX` or `UPDATE` block a PR (decided in 4.3, Nov 7).
- The output is the terminal report (see "Reports").

### Reports

Decided in 4.1 (Nov 4):

- Renderers live in `report/` and are pure: `ImpactReport` in, text out. `cli.py` imports from `report/`, never the other way round. `format_change` and `format_not_analyzed` live in `report/terminal.py` too, and `parse` imports them from there; `format_columns` / `format_model` stay in `cli.py` (only `lineage` uses them).
- Terminal report: a summary line first, then a blank line, then one block per impact, unmapped changes and `not_analyzed` entries. The summary is `worst: <level> · <n> breaking, <n> risky, <n> safe · <n> unmapped · <n> not analyzed`: zero counts are always shown, severities in the order breaking, risky, safe. An empty report still gets the summary, followed by `No changes found.`. No colours, so tests compare plain strings.
- `BEGIN` / `COMMIT` and other harmless statements still show as `not_analyzed`; filtering that noise is deferred.
- JSON (built Nov 5): `schemaguard check --format text|json` (`-f`, default `text`), printed to stdout, so in JSON mode stdout holds only JSON and every hint or error goes to stderr. `report/json_report.py` (not `json.py`, to avoid confusion with the stdlib module) dumps `ImpactReport` with `model_dump(mode="json")` (computed `severity`, `uncertain` and `worst` included) inside an envelope with `"version": 1` (`FORMAT_VERSION`) as the first key, so readers can detect a format change. Output is compact (no indent); pipe through `jq` to read it. `source` is an object `{"source_name", "table_name"}`, not the `"<source>.<table>"` string. The document validates back into `ImpactReport` once `version` is removed (computed fields are ignored on input).

- Markdown (decided and built Nov 6, roadmap 4.2): `format_markdown(report) -> str` in `report/markdown.py` renders `report/templates/comment.md.j2` with Jinja2 (`PackageLoader`, `trim_blocks`, `lstrip_blocks`, `StrictUndefined` so template typos fail loudly, `autoescape=False` because the output is markdown, not HTML). The template is a package resource shipped in the wheel (`uv_build` includes every file under `src/schemaguard/`), so loading it is not user I/O and the function stays pure. Layout: the marker, `## SchemaGuard`, the summary line in bold (`format_summary`), then one table row per impact: severity with an icon (🔴 breaking, 🟡 risky, 🟢 safe) and the uncertain / possible-rename marks, change (`kind target detail`, via `change_target` / `change_detail`, which `format_change` also uses), `file:line`, source, affected models as `name (hop N)` with `?` when uncertain, test count, exposures. Unmapped changes and `not_analyzed` entries go in collapsed `<details>` blocks with a count; the table stays open. An empty report still renders the marker, heading, summary and `No changes found.`; whether to post it is decided in 4.3 / 5.1. Text in cells and list items passes through the `md` filter: `|` → `\|`, `<` → `&lt;` (GitHub would read it as HTML), newlines → spaces; no code spans, so backticks can't break anything. `check --format markdown` prints it to stdout like JSON mode, for previewing locally and for the Action.

### PR comment

One comment per PR. The comment contains a hidden marker (`<!-- schemaguard -->`). The marker is `MARKER` in `report/markdown.py` (re-exported from `report/`) and the first line of every rendered comment; `github/` imports it instead of repeating the string. Each run looks for a comment with the marker and updates it, or creates one if none exists.

Built Nov 10 (roadmap 5.1, 5.2): `github/comments.py` uses a sync `httpx.Client` (the CLI is sync; async buys nothing for three sequential calls). `post_comment(client, repo, pr, body, create=True)` lists the PR's comments (following pagination), finds the first one starting with `MARKER`, then updates or creates. Every failure is a `GitHubError` and `check` only warns about it: the exit code always comes from severity, because fork PRs get a read-only token. An empty report never creates a comment (`create=False`) but does update an old one, so a fixed PR doesn't keep a stale warning. `check --pr N` reads `GITHUB_TOKEN` and `GITHUB_REPOSITORY` from the environment. `action.yml` is a thin composite wrapper: `setup-uv`, then `uvx --from "$ACTION_PATH" schemaguard check`, with inputs passed through `env:`. On pull requests it also passes `--base HEAD^1`: `actions/checkout` checks out the PR's merge commit, whose first parent is the base branch, so only the PR's migrations are checked and a breaking migration merged earlier doesn't fail every later PR. The caller's checkout needs `fetch-depth: 2`. The demo workflow (`../demoBackendRepo/.github/workflows/schemaguard.yml`, Nov 11) runs on every `pull_request` (no `paths:` filter, so an outdated comment is cleared), with `pull-requests: write` and a per-PR `concurrency` group so two runs can't create two comments.

## Proposed repo layout

```
schemaguard/
├── pyproject.toml
├── action.yml                  # composite GitHub Action
├── src/schemaguard/
│   ├── cli.py
│   ├── config/
│   ├── migrations/
│   │   ├── changes.py          # data shapes (ChangeSet, ...)
│   │   ├── alembic.py
│   │   ├── sql.py
│   │   └── text.py             # shared reason shortening
│   ├── dbt/
│   │   ├── manifest.py
│   │   ├── lineage.py
│   │   └── columns.py
│   ├── impact/
│   │   ├── analyzer.py
│   │   └── severity.py
│   ├── report/
│   │   ├── terminal.py
│   │   ├── json_report.py
│   │   ├── markdown.py
│   │   └── templates/
│   └── github/
├── tests/
│   ├── fixtures/               # migrations, manifest, configs
│   └── scenarios/              # migration + expected result pairs
└── docs/
```

## Tech stack

| Area | Choice | Why |
|---|---|---|
| Language | Python 3.13 | dbt, Alembic and sqlglot are all Python |
| Packaging | uv + `pyproject.toml` | Fast installs, ready for a later PyPI release |
| CLI | Typer | Commands and `--help` with very little code |
| Config | PyYAML + Pydantic v2 | Validated `schemaguard.yml` with clear error messages |
| Alembic parsing | `ast` (standard library) | Reads `op.*` calls without running the migration |
| SQL parsing | sqlglot | Parses Postgres DDL, and lists the columns a model's SQL references. Its full lineage module isn't needed at first |
| dbt manifest | Own small Pydantic models | Only `nodes`, `sources`, `child_map`, `exposures` and `compiled_code` are needed. Writing them by hand teaches the manifest's structure |
| Lineage graph | Plain BFS over the manifest's `child_map` | No graph library needed; shows graph traversal directly |
| Report templates | Jinja2 | The PR comment is one markdown template |
| Lineage picture | Mermaid (optional) | GitHub renders it in PR comments. First to cut if time is short |
| GitHub API | httpx + `GITHUB_TOKEN` | The token is provided to the Action automatically |
| GitHub Action | Composite action | Plain YAML, no Docker image to build |
| Tests | pytest | Fixture migrations and a fixture manifest |
| Lint and format | ruff | One tool, near-zero setup |
| Type checking | pyright (strict) | Catches `None` and `Any` leaks from sqlglot's untyped `args` dict |
| Git hooks | pre-commit | Runs ruff, pyright and file checks before every commit |
| Demo | Postgres in Docker, FastAPI + Alembic backend, dbt-postgres project based on jaffle_shop | A realistic backend repo and data repo. Check which jaffle_shop repo is current; `dbt compile` needs Postgres running |

Dependencies:

```toml
dependencies = ["typer", "pydantic", "pyyaml", "sqlglot", "jinja2", "httpx"]
dev = ["pytest", "ruff", "pyright", "pre-commit"]
```

dbt is not a dependency. SchemaGuard only reads the JSON file dbt produces; dbt is needed only in the demo data repo.

## Known limitations (MVP)

- Supports Alembic, raw SQL, Postgres and GitHub only.
- PRs from forks cannot get a comment (their `GITHUB_TOKEN` is read-only). The run warns and still fails on severity.
- A foreign comment that starts with the marker would be picked up; updating it fails with a permission error (warning only).
- The dbt `manifest.json` must be committed in the backend repo (or otherwise present at the configured path); the Action does not run dbt. It is a manual snapshot and goes stale when the data team changes models.
- The Action relies on the default `pull_request` checkout (the merge commit) with `fetch-depth: 2`. A checkout with a custom `ref:` (the PR head) makes `HEAD^1` the PR's previous commit, so only the last commit's migrations are checked.
- `--base` only sees tracked files; an untracked migration is not checked.
- The demo workflow uses `gazi04/schemaGuard@main`, not a pinned tag or SHA.
- Index, constraint and enum changes are not checked.
- Column-level matching only at the first hop; deeper levels are table-level.
- `SELECT *` and unparsable SQL fall back to table-level, marked uncertain.
- The table-to-source mapping is written by hand.
- Schema prefixes are dropped: `public.orders` and `staging.orders` are both reported as `orders`.
- Line numbers are per `op.execute` call or per SQL string, not per statement. Every change in a raw `.sql` file reports the line passed in.
- `op.execute` only reads string literals. `sa.text(...)`, f-strings and variables are reported as `not_analyzed`.
- Alembic table and column names must be positional string literals. Keyword-only forms (`table_name=...`, `column_name=...`) and `with op.batch_alter_table(...)` are reported as `not_analyzed`.
- `existing_*` keywords on `op.alter_column` describe the old state and are skipped. Only `existing_type` is read, to fill `old_type`.
- Alembic types are kept as source text (`sa.BigInteger()`), while the SQL parser gives Postgres names (`BIGINT`).
- Everything that isn't a supported change is reported as `not_analyzed`, so harmless statements (`CREATE INDEX`, `UPDATE`, `BEGIN`/`COMMIT`) add some noise to the report.
- One SQL parse error turns the whole SQL string into a single `not_analyzed` entry. Valid statements in the same string are not analyzed.
- An Alembic file with a Python syntax error becomes one `not_analyzed` entry; nothing else in it is analyzed.
- sqlglot attaches comments to the statement that follows them, so a file's leading `-- comment` can show up (sometimes twice) in the first statement's `not_analyzed` reason.
- `not_analyzed` reasons show the SQL as sqlglot rebuilds it (e.g. `SERIAL` becomes `INT GENERATED BY DEFAULT AS IDENTITY`), not the original text.
- Unquoted names keep the case they were written in; Postgres would fold `CUSTOMERS` to `customers`. The parsers and the dbt side (`find_source`, `column_usage`) match exactly; only `impact/` compares case-insensitively. Quoted names (`"Email"`), which Postgres keeps case-sensitive, are matched case-insensitively too.
- Renames are not followed across migrations: after `customers` is renamed to `clients`, a later change on `clients` in the same PR is reported as unmapped.
- Column usage collects every column name in a first-hop model's SQL, not only the source's. In a join, a column of another table with the same name (`id`) counts as used.
- "Possible rename" doesn't pair columns: when a file drops several columns of a table and adds any column to it, every drop is flagged.
- Exposures that depend on a source directly (no model in between) are not collected. Only exposures that hang off an affected model are reported.
- A source test without a `column_name` (a table-level test like a row count) only counts for table-level changes (`drop_table`, `rename_table`), not for column changes.
- Column usage only looks at the outer query's `*` (and `*` passed through CTEs, subqueries and UNION branches). A `*` inside a CTE that the outer query narrows to named columns is not uncertain.
- dbt unit tests appear in `child_map` but not in `nodes`, so lineage skips them. Seeds and snapshots downstream are skipped too.
- A first-hop model without `compiled_code` (manifest from `dbt parse`) is reported as uncertain, like `SELECT *`. `schemaguard lineage` prints a hint to run `dbt compile`, but the column result can't tell the two cases apart.
- `schemaguard lineage` prints only the number of downstream tests, not their names.
- Replication tools (e.g. Fivetran, Airbyte) may handle renames and drops differently, for example by keeping the old column filled with NULLs instead of breaking dbt. SchemaGuard assumes the change reaches the warehouse as written.
- Getting a fresh manifest across repos needs a token with read access to the data repo. The demo commits a copy instead.
- `not_analyzed` entries never fail `check`: a PR whose only change is unreadable (e.g. `op.execute(sa.text(...))`) passes CI, with the entry listed in the report.
- A key written twice in `schemaguard.yml` is not an error: PyYAML keeps the last one, silently.
- Config validation only checks the `<source>.<table>` shape. A value like `a.b.c` passes and is only reported when the manifest lookup fails.

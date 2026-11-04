"""Scenario suite (roadmap 3.4).

Every migration in tests/fixtures/scenarios/migrations has one expected result
here. The manifest next to it has three sources:

- customers: stg_customers reads id, name, email; source tests on id and phone
- orders: stg_orders reads `select *`, so every column match is uncertain
- payments: no model reads it

customer_orders (hop 2) reads both staging models; exposure weekly_kpis reads it.
"""

from pathlib import Path
from typing import NamedTuple

import pytest
from typer.testing import CliRunner

from schemaguard.cli import app, merge_change_sets, parse_file
from schemaguard.config import load_config
from schemaguard.dbt.manifest import Manifest
from schemaguard.impact import Severity, analyze
from tests.helper import FIXTURES

SCENARIOS_DIR = FIXTURES / "scenarios"
MIGRATIONS = SCENARIOS_DIR / "migrations"
CONFIG = SCENARIOS_DIR / "schemaguard.yml"

runner = CliRunner()

BREAKING = "breaking"
RISKY = "risky"
SAFE = "safe"


class Expected(NamedTuple):
    severities: tuple[str, ...]  # one `severity:` line per impact, marks included
    worst: Severity
    unmapped: int = 0
    not_analyzed: int = 0


SCENARIOS: dict[str, Expected] = {
    # Alembic
    "a01_drop_used_column.py": Expected((BREAKING,), Severity.BREAKING),
    "a02_drop_unused_column.py": Expected((SAFE,), Severity.SAFE),
    "a03_rename_used_column.py": Expected((BREAKING,), Severity.BREAKING),
    "a04_rename_unused_column.py": Expected((SAFE,), Severity.SAFE),
    "a05_type_used_column.py": Expected((RISKY,), Severity.RISKY),
    "a06_type_unused_column.py": Expected((SAFE,), Severity.SAFE),
    "a07_nullable_used_column.py": Expected((RISKY,), Severity.RISKY),
    "a08_not_null_used_column.py": Expected((SAFE,), Severity.SAFE),
    "a09_add_column.py": Expected((SAFE,), Severity.SAFE),
    "a10_drop_unread_table.py": Expected((BREAKING,), Severity.BREAKING),
    "a11_rename_table.py": Expected((BREAKING,), Severity.BREAKING),
    "a12_drop_select_star_column.py": Expected(
        ("breaking (uncertain)",), Severity.BREAKING
    ),
    "a13_type_select_star_column.py": Expected(("risky (uncertain)",), Severity.RISKY),
    "a14_drop_test_only_column.py": Expected((BREAKING,), Severity.BREAKING),
    "a15_drop_add_rename.py": Expected(
        ("breaking (possible rename)", SAFE), Severity.BREAKING
    ),
    "a16_unmapped_table.py": Expected((), Severity.SAFE, unmapped=1),
    "a17_ignored_table.py": Expected((), Severity.SAFE),
    "a18_create_table_and_drop.py": Expected((SAFE,), Severity.SAFE, not_analyzed=1),
    "a19_execute_sql.py": Expected((BREAKING,), Severity.BREAKING),
    "a20_mixed_case_names.py": Expected((BREAKING,), Severity.BREAKING),
    "a21_nullable_test_only_column.py": Expected((RISKY,), Severity.RISKY),
    # Raw SQL
    "s01_drop_used_column.sql": Expected((BREAKING,), Severity.BREAKING),
    "s02_nullable_used_column.sql": Expected((RISKY,), Severity.RISKY),
    "s03_rename_select_star_column.sql": Expected(
        ("breaking (uncertain)",), Severity.BREAKING
    ),
    "s04_multi_change.sql": Expected(
        (SAFE, SAFE, BREAKING), Severity.BREAKING, not_analyzed=2
    ),
    "s05_unsupported.sql": Expected((), Severity.SAFE, not_analyzed=1),
}


def severity_lines(stdout: str) -> tuple[str, ...]:
    prefix = "  severity: "
    return tuple(
        line.removeprefix(prefix)
        for line in stdout.splitlines()
        if line.startswith(prefix)
    )


def test_every_migration_has_a_scenario():
    files = {p.name for p in MIGRATIONS.iterdir() if p.suffix in (".py", ".sql")}

    assert files == set(SCENARIOS)
    assert len(SCENARIOS) >= 20


@pytest.mark.parametrize(("name", "expected"), SCENARIOS.items(), ids=SCENARIOS)
def test_scenario_check_output(name: str, expected: Expected):
    result = runner.invoke(
        app, ["check", str(MIGRATIONS / name), "--config", str(CONFIG)]
    )

    assert result.exit_code == 0, result.output
    assert severity_lines(result.stdout) == expected.severities
    assert result.stdout.count("  (unmapped)") == expected.unmapped
    assert result.stdout.count(" not_analyzed ") == expected.not_analyzed


@pytest.mark.parametrize(("name", "expected"), SCENARIOS.items(), ids=SCENARIOS)
def test_scenario_worst(name: str, expected: Expected):
    config = load_config(CONFIG.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(
        (SCENARIOS_DIR / config.manifest).read_text(encoding="utf-8")
    )

    report = analyze(parse_file(MIGRATIONS / name), manifest, config)

    assert report.worst is expected.worst
    assert len(report.unmapped) == expected.unmapped
    assert len(report.not_analyzed) == expected.not_analyzed


def test_check_whole_scenario_folder():
    result = runner.invoke(app, ["check", "--config", str(CONFIG)])

    assert result.exit_code == 0, result.output
    expected = [s for e in SCENARIOS.values() for s in e.severities]
    assert sorted(severity_lines(result.stdout)) == sorted(expected)


def test_whole_folder_worst_is_breaking():
    config = load_config(CONFIG.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(
        (SCENARIOS_DIR / config.manifest).read_text(encoding="utf-8")
    )
    files = sorted(MIGRATIONS.iterdir())

    report = analyze(
        merge_change_sets([parse_file(f) for f in files]), manifest, config
    )

    assert report.worst is Severity.BREAKING


def test_source_missing_from_manifest_exits_2(tmp_path: Path):
    config = tmp_path / "schemaguard.yml"
    manifest = SCENARIOS_DIR / "dbt" / "manifest.json"
    config.write_text(
        f"manifest: {manifest}\nsources:\n  refunds: app.refunds\n",
        encoding="utf-8",
    )
    migration = tmp_path / "0001.sql"
    migration.write_text("ALTER TABLE refunds DROP COLUMN reason;\n", encoding="utf-8")

    result = runner.invoke(app, ["check", str(migration), "--config", str(config)])

    assert result.exit_code == 2
    assert "app.refunds" in result.stderr

from collections import Counter

from schemaguard.impact import ChangeImpact, ImpactReport, Severity
from schemaguard.migrations import ChangeKind, NotAnalyzed, SchemaChange

ORDER = (Severity.BREAKING, Severity.RISKY, Severity.SAFE)


def format_report(report: ImpactReport) -> list[str]:
    lines = [format_summary(report), ""]
    if not (report.impacts or report.unmapped or report.not_analyzed):
        lines.append("No changes found.")

    for impact in report.impacts:
        lines += format_impact(impact)

    lines += [f"{format_change(c)}  (unmapped)" for c in report.unmapped]
    lines += [format_not_analyzed(n) for n in report.not_analyzed]

    return lines


def format_summary(report: ImpactReport) -> str:
    counts = Counter(impact.severity for impact in report.impacts)
    levels = ", ".join(f"{counts[s]} {s}" for s in ORDER)
    return (
        f"worst: {report.worst} · {levels} · "
        f"{len(report.unmapped)} unmapped · "
        f"{len(report.not_analyzed)} not analyzed"
    )


def format_impact(impact: ChangeImpact) -> list[str]:
    lines = [
        format_change(impact.change),
        f"  source {impact.source}",
        format_severity(impact),
    ]

    if not impact.models:
        lines.append("  no affected models")

    for model in impact.models:
        line = f"  hop {model.depth}  {model.name:<20}"
        if model.uncertain:
            line = f"{line} (uncertain)"
        lines.append(line.rstrip())

    lines.append(f"  tests: {len(impact.tests)}")

    if impact.exposures:
        lines.append(f"  exposures: {', '.join(impact.exposures)}")

    return lines


def format_severity(impact: ChangeImpact) -> str:
    marks: list[str] = []
    if impact.uncertain:
        marks.append("uncertain")
    if impact.possible_rename:
        marks.append("possible rename")

    line = f"  severity: {impact.severity}"
    return f"{line} ({', '.join(marks)})" if marks else line


def format_change(change: SchemaChange) -> str:
    target = change_target(change)
    detail = change_detail(change)
    location = f"{change.source_file}:{change.line}"
    return f"{location} {change.kind:<17} {target} {detail}".rstrip()


def change_target(change: SchemaChange) -> str:
    """`table` or `table.column`."""
    if change.column is None:
        return change.table
    return f"{change.table}.{change.column}"


def change_detail(change: SchemaChange) -> str:
    """What the change does, e.g. `-> new_name` or `INT -> BIGINT`; may be empty."""
    match change.kind:
        case ChangeKind.RENAME_COLUMN | ChangeKind.RENAME_TABLE:
            return f"-> {change.new_name}"
        case ChangeKind.ALTER_TYPE:
            return f"{change.old_type or '?'} -> {change.new_type}"
        case ChangeKind.ALTER_NULLABILITY:
            return "-> nullable" if change.nullable else "-> not null"
        case ChangeKind.ADD_COLUMN:
            return change.new_type or ""
        case ChangeKind.DROP_COLUMN | ChangeKind.DROP_TABLE:
            return ""


def format_not_analyzed(entry: NotAnalyzed) -> str:
    location = f"{entry.source_file}:{entry.line}"
    return f"{location} {'not_analyzed':<17} {entry.reason}"

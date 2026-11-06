from jinja2 import Environment, PackageLoader, StrictUndefined

from schemaguard.impact import ChangeImpact, ImpactReport, Severity
from schemaguard.migrations import SchemaChange
from schemaguard.report.terminal import change_detail, change_target, format_summary

# First line of every comment; github/ looks for it to update its own comment.
MARKER = "<!-- schemaguard -->"

SEVERITY_ICON = {
    Severity.BREAKING: "🔴",
    Severity.RISKY: "🟡",
    Severity.SAFE: "🟢",
}


def md(text: object) -> str:
    """Make text safe for a markdown table cell or list item."""
    return (
        str(text)
        .replace("|", "\\|")
        .replace("<", "&lt;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def describe(change: SchemaChange) -> str:
    """`kind target detail`, e.g. `drop_column customers.email`."""
    return " ".join(
        part
        for part in (change.kind, change_target(change), change_detail(change))
        if part
    )


def severity_cell(impact: ChangeImpact) -> str:
    marks: list[str] = []
    if impact.uncertain:
        marks.append("uncertain")
    if impact.possible_rename:
        marks.append("possible rename")

    cell = f"{SEVERITY_ICON[impact.severity]} {impact.severity}"
    return f"{cell} ({', '.join(marks)})" if marks else cell


def models_cell(impact: ChangeImpact) -> str:
    """`name (hop N)` per model, `?` when uncertain; `-` when none."""
    names = [
        f"{m.name} (hop {m.depth}){'?' if m.uncertain else ''}" for m in impact.models
    ]
    return ", ".join(names) or "-"


_ENV = Environment(
    loader=PackageLoader("schemaguard.report", "templates"),
    autoescape=False,  # noqa: S701 - output is markdown, escaped by the `md` filter
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)
_ENV.filters["md"] = md


def format_markdown(report: ImpactReport) -> str:
    template = _ENV.get_template("comment.md.j2")
    return template.render(
        marker=MARKER,
        summary=format_summary(report),
        impacts=report.impacts,
        unmapped=report.unmapped,
        not_analyzed=report.not_analyzed,
        describe=describe,
        severity_cell=severity_cell,
        models_cell=models_cell,
    )

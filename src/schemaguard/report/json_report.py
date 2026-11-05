import json

from schemaguard.impact import ImpactReport

FORMAT_VERSION = 1


def format_json(report: ImpactReport) -> str:
    data = report.model_dump(mode="json")
    return json.dumps({"version": FORMAT_VERSION, **data})

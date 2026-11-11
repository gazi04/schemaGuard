from pathlib import Path
from typing import Any

import yaml

ACTION = Path(__file__).parent.parent / "action.yml"


def load() -> dict[str, Any]:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def test_action_is_composite():
    assert load()["runs"]["using"] == "composite"


def test_every_run_step_names_its_shell():
    steps = load()["runs"]["steps"]
    run_steps = [s for s in steps if "run" in s]
    assert run_steps
    assert all(s.get("shell") == "bash" for s in run_steps)


def test_inputs_have_descriptions_and_defaults():
    inputs = load()["inputs"]
    assert set(inputs) == {"config", "fail-on", "github-token", "working-directory"}
    assert all("description" in i and "default" in i for i in inputs.values())


def test_inputs_are_not_interpolated_into_shell():
    for step in load()["runs"]["steps"]:
        assert "${{" not in step.get("run", "")


def test_pull_requests_check_only_changed_migrations():
    run = next(s["run"] for s in load()["runs"]["steps"] if "run" in s)
    assert '${PR_NUMBER:+--pr "$PR_NUMBER" --base HEAD^1}' in run

from pathlib import Path

import schemaguard


def test_schemaguard_package() -> None:
    assert (
        Path(__file__).parents[1] / "src" / "schemaguard"
        == Path(schemaguard.__file__).parent
    )

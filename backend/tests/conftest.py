from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        layer = item.path.relative_to(TESTS_DIR).parts[0]
        if layer in {"integration", "external"}:
            item.add_marker(getattr(pytest.mark, layer))

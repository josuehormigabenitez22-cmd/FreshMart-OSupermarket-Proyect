import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Todo lo que vive en tests/integration lleva el marcador ``integration``.

    Así ``pytest -m "not integration"`` corre solo los unitarios (segundos).
    """
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)

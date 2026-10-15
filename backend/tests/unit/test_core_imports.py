"""The core imports only the standard library, pydantic and itself (ADR-0005).

Changing this allow-list is a maintainer decision, asked for in the PR.
"""

import ast
import sys
from pathlib import Path

import nexus.core

ALLOWED_THIRD_PARTY = frozenset({"pydantic"})
CORE_DIR = Path(nexus.core.__file__).parent


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module)
    return roots


def is_allowed(module: str) -> bool:
    root = module.split(".")[0]
    return (
        root in sys.stdlib_module_names
        or root in ALLOWED_THIRD_PARTY
        or module == "nexus.core"
        or module.startswith("nexus.core.")
    )


def test_core_only_imports_stdlib_pydantic_and_itself() -> None:
    offenders = {
        f"{path.relative_to(CORE_DIR)}: {module}"
        for path in CORE_DIR.rglob("*.py")
        for module in imported_roots(path)
        if not is_allowed(module)
    }

    assert not offenders, sorted(offenders)


def test_the_check_sees_a_forbidden_import(tmp_path: Path) -> None:
    module = tmp_path / "bad.py"
    module.write_text("import sqlalchemy\nfrom nexus.adapters import persistence\n")

    assert {m for m in imported_roots(module) if not is_allowed(m)} == {
        "sqlalchemy",
        "nexus.adapters",
    }

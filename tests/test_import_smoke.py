from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TARGET_FILES = (
    ROOT / "app" / "streamlit_app.py",
    ROOT / "app" / "pages" / "1_Admin.py",
    ROOT / "app" / "pages" / "2_Annotator.py",
)


@dataclass(frozen=True)
class ImportCheck:
    file_path: Path
    module: str
    symbol: str | None = None


def _collect_import_checks(file_path: Path) -> list[ImportCheck]:
    tree = ast.parse(file_path.read_text(encoding="utf-8-sig"), filename=str(file_path))
    checks: list[ImportCheck] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                checks.append(ImportCheck(file_path=file_path, module=alias.name))

        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                checks.append(ImportCheck(file_path=file_path, module=node.module, symbol=alias.name))

    return checks


ALL_IMPORT_CHECKS = [
    check
    for target_file in TARGET_FILES
    for check in _collect_import_checks(target_file)
]


def _check_id(check: ImportCheck) -> str:
    suffix = f".{check.symbol}" if check.symbol else ""
    return f"{check.file_path.relative_to(ROOT)}::{check.module}{suffix}"


@pytest.mark.parametrize("check", ALL_IMPORT_CHECKS, ids=_check_id)
def test_declared_imports_resolve(check: ImportCheck) -> None:
    imported_module = importlib.import_module(check.module)
    assert imported_module is not None

    if check.symbol is None:
        return

    assert hasattr(imported_module, check.symbol), (
        f"{check.file_path.relative_to(ROOT)} imports "
        f"'{check.symbol}' from '{check.module}', but that symbol is missing."
    )

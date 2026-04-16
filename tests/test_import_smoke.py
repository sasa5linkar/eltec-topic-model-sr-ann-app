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


def _resolve_internal_module_path(module: str) -> Path | None:
    module_path = ROOT.joinpath(*module.split("."))
    package_init = module_path / "__init__.py"
    if package_init.exists():
        return package_init

    module_file = module_path.with_suffix(".py")
    if module_file.exists():
        return module_file

    return None


def _collect_module_level_exports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8-sig"), filename=str(module_path))
    exports: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.add(node.name)
            continue

        if isinstance(node, ast.Import):
            for alias in node.names:
                exports.add(alias.asname or alias.name.split(".")[0])
            continue

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                exports.add(alias.asname or alias.name)
            continue

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exports.add(target.id)
            continue

        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            exports.add(node.target.id)

    return exports


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
    internal_module_path = _resolve_internal_module_path(check.module)
    if internal_module_path is not None:
        exports = _collect_module_level_exports(internal_module_path)
        if check.symbol is None:
            assert internal_module_path.exists(), f"Internal module '{check.module}' is missing."
            return

        assert check.symbol in exports, (
            f"{check.file_path.relative_to(ROOT)} imports "
            f"'{check.symbol}' from '{check.module}', but that symbol is missing."
        )
        return

    imported_module = importlib.import_module(check.module)
    assert imported_module is not None

    if check.symbol is None:
        return

    assert hasattr(imported_module, check.symbol), (
        f"{check.file_path.relative_to(ROOT)} imports "
        f"'{check.symbol}' from '{check.module}', but that symbol is missing."
    )

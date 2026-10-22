#!/usr/bin/env python3
"""Validate backend source against the Python 3.8 runtime contract."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import List


FORBIDDEN_ATTRIBUTES = {
    "removeprefix",
    "removesuffix",
}


def count_python_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*.py") if path.is_file())


def _attribute_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def validate_tree(root: Path) -> List[str]:
    """Return source locations that cannot be used by the Python 3.8 target."""

    issues: List[str] = []
    root = Path(root)
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=8)
        except (OSError, SyntaxError) as exc:
            issues.append("%s: %s" % (path, exc))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if _attribute_name(node.func) == "to_thread" and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "asyncio":
                        issues.append("%s:%s uses asyncio.to_thread" % (path, node.lineno))
                elif _attribute_name(node.func) in FORBIDDEN_ATTRIBUTES:
                    issues.append("%s:%s uses str.%s" % (path, node.lineno, node.func.attr))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="backend source directory to validate")
    args = parser.parse_args()
    issues = validate_tree(args.root)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("Python 3.8 validation passed: %d files" % count_python_files(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

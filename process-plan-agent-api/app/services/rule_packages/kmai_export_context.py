"""Shared state types for deterministic KmAI export assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any

from app.services.rule_packages.contracts import (
    KmaiCompatibilityIssue,
    RulePackageV2,
    ValidationIssue,
)


@dataclass
class FactorRegistry:
    _items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, factor_key: str) -> bool:
        return factor_key in self._items

    def get(self, factor_key: str) -> dict[str, Any] | None:
        return self._items.get(factor_key)

    def register(self, factor_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        if factor_key not in self._items:
            self._items[factor_key] = payload
        return self._items[factor_key]

    def update(self, factor_key: str, **changes: Any) -> None:
        self._items[factor_key].update(changes)

    def values(self) -> list[dict[str, Any]]:
        return list(self._items.values())


@dataclass
class ArtifactBuildResult:
    payload: dict[str, Any]
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)


@dataclass
class ConditionBudget:
    max_combinations: int
    max_condition_objects: int
    generated_combinations: int = 0
    generated_condition_objects: int = 0

    def project(self, combinations: int, condition_objects: int) -> tuple[int, int]:
        return (
            self.generated_combinations + combinations,
            self.generated_condition_objects + condition_objects,
        )

    def record(self, clauses: list[list[dict[str, Any]]]) -> None:
        self.generated_combinations += len(clauses)
        self.generated_condition_objects += sum(len(clause) for clause in clauses)


@dataclass
class KmaiExportContext:
    """Mutable state shared by one deterministic KmAI export build."""

    package: RulePackageV2
    registry: FactorRegistry
    budget: ConditionBudget
    legacy_adapters: Mapping[tuple[str, str], Any] | None = None
    errors: list[KmaiCompatibilityIssue] = field(default_factory=list)
    warnings: list[KmaiCompatibilityIssue] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        package: RulePackageV2,
        *,
        max_combinations: int,
        max_condition_objects: int,
        legacy_adapters: Mapping[tuple[str, str], Any] | None = None,
    ) -> "KmaiExportContext":
        return cls(
            package=package,
            registry=FactorRegistry(),
            budget=ConditionBudget(max_combinations, max_condition_objects),
            legacy_adapters=legacy_adapters,
        )

    def error(
        self,
        code: str,
        message: str,
        path: str = "",
        **details: Any,
    ) -> KmaiCompatibilityIssue:
        issue = KmaiCompatibilityIssue(
            code=code,
            path=path,
            message=message,
            **details,
        )
        self.errors.append(issue)
        return issue

    def warning(
        self,
        code: str,
        message: str,
        path: str = "",
        **details: Any,
    ) -> KmaiCompatibilityIssue:
        issue = KmaiCompatibilityIssue(
            code=code,
            path=path,
            message=message,
            **details,
        )
        self.warnings.append(issue)
        return issue

    def record_clauses(self, clauses: list[list[dict[str, Any]]]) -> None:
        self.budget.record(clauses)

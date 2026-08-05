"""Domain errors for condition-review workflows."""

from __future__ import annotations


class ConditionReviewError(ValueError):
    def __init__(self, detail: str | dict[str, object]):
        super().__init__(str(detail))
        self.detail = detail


class ConditionReviewNotFound(ConditionReviewError):
    pass


class ConditionReviewConflict(ConditionReviewError):
    pass


class ConditionReviewValidation(ConditionReviewError):
    pass

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts.enums import EventType, Severity
from .mitre import TACTIC_CODE_PATTERN, TECHNIQUE_CODE_PATTERN


class RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleCondition(RuleModel):
    field: str = Field(min_length=1)
    operator: Literal["eq", "neq", "contains", "regex", "in", "cidr_contains", "gt", "gte", "lt", "lte"]
    value: Any


class RuleConditions(RuleModel):
    all: list[RuleCondition] = Field(min_length=1)


class RuleMitre(RuleModel):
    tactic_code: str = Field(pattern=TACTIC_CODE_PATTERN)
    technique_code: str = Field(pattern=TECHNIQUE_CODE_PATTERN)


class RuleIncident(RuleModel):
    enabled: bool
    correlation_key: str | None = None
    window_seconds: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_correlation_when_enabled(self) -> "RuleIncident":
        if self.enabled and (not self.correlation_key or self.window_seconds is None):
            raise ValueError("enabled incident requires correlation_key and window_seconds")
        if not self.enabled and ({"correlation_key", "window_seconds"} & self.model_fields_set):
            raise ValueError("disabled incident must omit correlation_key and window_seconds")
        return self


class RuleResponseGuidanceStep(RuleModel):
    order: int = Field(ge=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requires_manual_action: bool


class RuleV1(RuleModel):
    schema_version: Literal[1]
    rule_code: str = Field(min_length=1)
    rule_name: str = Field(min_length=1)
    alert_title: str = Field(min_length=1)
    alert_summary: str = Field(min_length=1)
    version: int = Field(ge=1)
    enabled: bool
    event_type: EventType
    conditions: RuleConditions
    severity: Severity
    risk_score: float = Field(ge=0, le=100)
    mitre: RuleMitre | None = None
    incident: RuleIncident
    response_guidance: list[RuleResponseGuidanceStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rule_contract(self) -> "RuleV1":
        if self.enabled and self.mitre is None:
            raise ValueError("enabled rule requires mitre mapping codes")
        if not self.enabled and "mitre" in self.model_fields_set:
            raise ValueError("disabled rule must omit mitre")
        orders = [step.order for step in self.response_guidance]
        if len(orders) != len(set(orders)):
            raise ValueError("response_guidance order values must be unique")
        return self

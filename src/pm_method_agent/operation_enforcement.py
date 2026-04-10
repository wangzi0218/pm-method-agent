from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from pm_method_agent.runtime_policy import (
    RuntimePolicy,
    RuntimePolicyViolation,
    check_runtime_action_policy,
    check_runtime_command_policy,
    check_runtime_write_policy,
)


@dataclass
class OperationCheck:
    check_type: str
    subject: str
    decision: str
    reason: str = ""
    terminal_state: str = ""
    violation_kind: str = ""

    def to_dict(self) -> dict:
        return {
            "check_type": self.check_type,
            "subject": self.subject,
            "decision": self.decision,
            "reason": self.reason,
            "terminal_state": self.terminal_state,
            "violation_kind": self.violation_kind,
        }


@dataclass
class OperationEnforcementDecision:
    allowed: bool
    terminal_state: str = ""
    reason: str = ""
    violation_kind: str = ""
    checks: List[OperationCheck] = field(default_factory=list)
    violation: Optional[RuntimePolicyViolation] = None

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "terminal_state": self.terminal_state,
            "reason": self.reason,
            "violation_kind": self.violation_kind,
            "checks": [item.to_dict() for item in self.checks],
        }


def evaluate_operation_enforcement(
    policy: RuntimePolicy,
    *,
    action_name: str = "",
    command_args: Optional[List[str]] = None,
    write_paths: Optional[List[str]] = None,
) -> OperationEnforcementDecision:
    checks: List[OperationCheck] = []

    if action_name:
        violation = check_runtime_action_policy(policy, action_name=action_name)
        if violation is not None:
            checks.append(_build_violation_check("action", action_name, violation))
            return OperationEnforcementDecision(
                allowed=False,
                terminal_state=violation.terminal_state,
                reason=violation.reason,
                violation_kind=violation.violation_kind,
                checks=checks,
                violation=violation,
            )
        checks.append(OperationCheck(check_type="action", subject=action_name, decision="allowed"))

    normalized_command_args = [item for item in (command_args or []) if str(item).strip()]
    if normalized_command_args:
        command_preview = " ".join(normalized_command_args)
        violation = check_runtime_command_policy(policy, command_args=normalized_command_args)
        if violation is not None:
            checks.append(_build_violation_check("command", command_preview, violation))
            return OperationEnforcementDecision(
                allowed=False,
                terminal_state=violation.terminal_state,
                reason=violation.reason,
                violation_kind=violation.violation_kind,
                checks=checks,
                violation=violation,
            )
        checks.append(OperationCheck(check_type="command", subject=command_preview, decision="allowed"))

    normalized_write_paths = [item for item in (write_paths or []) if str(item).strip()]
    if normalized_write_paths:
        violation = check_runtime_write_policy(policy, write_paths=normalized_write_paths)
        if violation is not None:
            checks.append(_build_violation_check("write-path", violation.write_path or normalized_write_paths[0], violation))
            return OperationEnforcementDecision(
                allowed=False,
                terminal_state=violation.terminal_state,
                reason=violation.reason,
                violation_kind=violation.violation_kind,
                checks=checks,
                violation=violation,
            )
        for item in normalized_write_paths:
            checks.append(OperationCheck(check_type="write-path", subject=item, decision="allowed"))

    return OperationEnforcementDecision(
        allowed=True,
        terminal_state="completed",
        checks=checks,
    )


def _build_violation_check(
    check_type: str,
    subject: str,
    violation: RuntimePolicyViolation,
) -> OperationCheck:
    return OperationCheck(
        check_type=check_type,
        subject=subject,
        decision=violation.violation_kind or "blocked",
        reason=violation.reason,
        terminal_state=violation.terminal_state,
        violation_kind=violation.violation_kind,
    )

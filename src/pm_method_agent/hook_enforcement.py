from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pm_method_agent.models import RuntimeSession
from pm_method_agent.operation_enforcement import OperationEnforcementDecision, evaluate_operation_enforcement
from pm_method_agent.runtime_policy import RuntimePolicy, RuntimePolicyViolation
from pm_method_agent.runtime_session_service import complete_hook_call, fail_hook_call, request_hook_call


DEFAULT_PRE_OPERATION_HOOK = "runtime-policy-enforcement"


@dataclass
class HookExecutionResult:
    hook_name: str
    hook_stage: str
    decision: OperationEnforcementDecision

    def to_dict(self) -> dict:
        return {
            "hook_name": self.hook_name,
            "hook_stage": self.hook_stage,
            "decision": self.decision.to_dict(),
        }


class HookExecutionBlockedError(Exception):
    def __init__(self, violation: RuntimePolicyViolation, hook_result: HookExecutionResult) -> None:
        super().__init__(violation.reason)
        self.violation = violation
        self.hook_result = hook_result


def run_pre_operation_hooks(
    runtime_session: RuntimeSession,
    policy: RuntimePolicy,
    *,
    action_name: str = "",
    command_args: Optional[List[str]] = None,
    write_paths: Optional[List[str]] = None,
) -> HookExecutionResult:
    entry = request_hook_call(
        runtime_session,
        hook_name=DEFAULT_PRE_OPERATION_HOOK,
        hook_stage="pre-operation",
        request_payload={
            "action_name": action_name,
            "command_args": list(command_args or []),
            "write_paths": list(write_paths or []),
        },
    )
    try:
        decision = evaluate_operation_enforcement(
            policy,
            action_name=action_name,
            command_args=command_args,
            write_paths=write_paths,
        )
    except Exception as exc:
        fail_hook_call(
            runtime_session,
            hook_call_id=str(entry["hook_call_id"]),
            error={
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )
        raise

    hook_result = HookExecutionResult(
        hook_name=DEFAULT_PRE_OPERATION_HOOK,
        hook_stage="pre-operation",
        decision=decision,
    )
    complete_hook_call(
        runtime_session,
        hook_call_id=str(entry["hook_call_id"]),
        result_payload=hook_result.to_dict(),
    )
    if not decision.allowed and decision.violation is not None:
        raise HookExecutionBlockedError(decision.violation, hook_result)
    return hook_result

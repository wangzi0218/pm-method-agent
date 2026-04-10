from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class AnalyzerFinding:
    dimension: str
    claim: str
    claim_type: str
    evidence_level: str
    evidence: List[str]
    unknowns: List[str]
    risk_if_wrong: str
    suggested_next_action: str
    human_decision_needed: bool = False
    owner: str = ""
    finding_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "AnalyzerFinding":
        return cls(
            dimension=str(payload["dimension"]),
            claim=str(payload["claim"]),
            claim_type=str(payload["claim_type"]),
            evidence_level=str(payload["evidence_level"]),
            evidence=list(payload.get("evidence", [])),
            unknowns=list(payload.get("unknowns", [])),
            risk_if_wrong=str(payload["risk_if_wrong"]),
            suggested_next_action=str(payload["suggested_next_action"]),
            human_decision_needed=bool(payload.get("human_decision_needed", False)),
            owner=str(payload.get("owner", "")),
            finding_id=payload.get("finding_id"),
        )


@dataclass
class DecisionGate:
    gate_id: str
    stage: str
    question: str
    options: List[str]
    recommended_option: str
    reason: str
    blocking: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "DecisionGate":
        return cls(
            gate_id=str(payload["gate_id"]),
            stage=str(payload["stage"]),
            question=str(payload["question"]),
            options=list(payload.get("options", [])),
            recommended_option=str(payload["recommended_option"]),
            reason=str(payload["reason"]),
            blocking=bool(payload.get("blocking", False)),
        )


@dataclass
class PreFramingDirection:
    direction_id: str
    label: str
    summary: str
    assumptions: List[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "PreFramingDirection":
        return cls(
            direction_id=str(payload["direction_id"]),
            label=str(payload["label"]),
            summary=str(payload["summary"]),
            assumptions=list(payload.get("assumptions", [])),
            confidence=str(payload.get("confidence", "medium")),
        )


@dataclass
class PreFramingResult:
    triggered: bool = False
    reason: str = ""
    candidate_directions: List[PreFramingDirection] = field(default_factory=list)
    priority_questions: List[str] = field(default_factory=list)
    recommended_direction_id: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "triggered": self.triggered,
            "reason": self.reason,
            "candidate_directions": [item.to_dict() for item in self.candidate_directions],
            "priority_questions": self.priority_questions,
            "recommended_direction_id": self.recommended_direction_id,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "PreFramingResult":
        return cls(
            triggered=bool(payload.get("triggered", False)),
            reason=str(payload.get("reason", "")),
            candidate_directions=[
                PreFramingDirection.from_dict(item)
                for item in payload.get("candidate_directions", [])
            ],
            priority_questions=list(payload.get("priority_questions", [])),
            recommended_direction_id=str(payload.get("recommended_direction_id", "")),
        )


@dataclass
class ProjectProfile:
    project_profile_id: str
    project_name: str
    context_profile: Dict[str, object] = field(default_factory=dict)
    stable_constraints: List[str] = field(default_factory=list)
    success_metrics: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "project_profile_id": self.project_profile_id,
            "project_name": self.project_name,
            "context_profile": self.context_profile,
            "stable_constraints": self.stable_constraints,
            "success_metrics": self.success_metrics,
            "notes": self.notes,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "ProjectProfile":
        return cls(
            project_profile_id=str(payload["project_profile_id"]),
            project_name=str(payload.get("project_name", "")),
            context_profile=dict(payload.get("context_profile", {})),
            stable_constraints=list(payload.get("stable_constraints", [])),
            success_metrics=list(payload.get("success_metrics", [])),
            notes=list(payload.get("notes", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class WorkspaceState:
    workspace_id: str
    active_case_id: str = ""
    active_project_profile_id: str = ""
    recent_case_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "active_case_id": self.active_case_id,
            "active_project_profile_id": self.active_project_profile_id,
            "recent_case_ids": self.recent_case_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "WorkspaceState":
        return cls(
            workspace_id=str(payload["workspace_id"]),
            active_case_id=str(payload.get("active_case_id", "")),
            active_project_profile_id=str(payload.get("active_project_profile_id", "")),
            recent_case_ids=list(payload.get("recent_case_ids", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass
class RuntimeSession:
    session_id: str
    workspace_id: str
    active_case_id: str = ""
    runtime_status: str = "idle"
    current_query_id: str = ""
    current_loop_state: str = "idle"
    turn_count: int = 0
    resume_from: str = ""
    context_budget: Dict[str, object] = field(default_factory=dict)
    compression_state: Dict[str, object] = field(default_factory=dict)
    pending_hooks: List[Dict[str, object]] = field(default_factory=list)
    pending_tool_calls: List[Dict[str, object]] = field(default_factory=list)
    last_terminal_event: Dict[str, object] = field(default_factory=dict)
    children_agent_ids: List[str] = field(default_factory=list)
    event_log: List[Dict[str, object]] = field(default_factory=list)
    runtime_metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "active_case_id": self.active_case_id,
            "runtime_status": self.runtime_status,
            "current_query_id": self.current_query_id,
            "current_loop_state": self.current_loop_state,
            "turn_count": self.turn_count,
            "resume_from": self.resume_from,
            "context_budget": self.context_budget,
            "compression_state": self.compression_state,
            "pending_hooks": self.pending_hooks,
            "pending_tool_calls": self.pending_tool_calls,
            "last_terminal_event": self.last_terminal_event,
            "children_agent_ids": self.children_agent_ids,
            "event_log": self.event_log,
            "runtime_metadata": self.runtime_metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "RuntimeSession":
        return cls(
            session_id=str(payload["session_id"]),
            workspace_id=str(payload["workspace_id"]),
            active_case_id=str(payload.get("active_case_id", "")),
            runtime_status=str(payload.get("runtime_status", "idle")),
            current_query_id=str(payload.get("current_query_id", "")),
            current_loop_state=str(payload.get("current_loop_state", "idle")),
            turn_count=int(payload.get("turn_count", 0)),
            resume_from=str(payload.get("resume_from", "")),
            context_budget=dict(payload.get("context_budget", {})),
            compression_state=dict(payload.get("compression_state", {})),
            pending_hooks=list(payload.get("pending_hooks", [])),
            pending_tool_calls=list(payload.get("pending_tool_calls", [])),
            last_terminal_event=dict(payload.get("last_terminal_event", {})),
            children_agent_ids=list(payload.get("children_agent_ids", [])),
            event_log=list(payload.get("event_log", [])),
            runtime_metadata=dict(payload.get("runtime_metadata", {})),
        )


@dataclass
class CaseState:
    case_id: str
    stage: str
    raw_input: str
    workflow_state: str = "intake"
    output_kind: str = "review-card"
    blocking_reason: str = ""
    pending_questions: List[str] = field(default_factory=list)
    context_profile: Dict[str, object] = field(default_factory=dict)
    pre_framing_result: Optional[PreFramingResult] = None
    normalized_summary: str = ""
    evidence: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    findings: List[AnalyzerFinding] = field(default_factory=list)
    decision_gates: List[DecisionGate] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def add_finding(self, finding: AnalyzerFinding) -> None:
        finding.finding_id = finding.finding_id or f"F-{len(self.findings) + 1:03d}"
        self.findings.append(finding)

    def add_gate(self, gate: DecisionGate) -> None:
        self.decision_gates.append(gate)

    def extend_evidence(self, items: List[str]) -> None:
        for item in items:
            if item and item not in self.evidence:
                self.evidence.append(item)

    def extend_unknowns(self, items: List[str]) -> None:
        for item in items:
            if item and item not in self.unknowns:
                self.unknowns.append(item)

    def extend_next_actions(self, items: List[str]) -> None:
        for item in items:
            if item and item not in self.next_actions:
                self.next_actions.append(item)

    def to_dict(self) -> Dict[str, object]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "workflow_state": self.workflow_state,
            "output_kind": self.output_kind,
            "blocking_reason": self.blocking_reason,
            "pending_questions": self.pending_questions,
            "raw_input": self.raw_input,
            "context_profile": self.context_profile,
            "pre_framing_result": self.pre_framing_result.to_dict() if self.pre_framing_result else None,
            "normalized_summary": self.normalized_summary,
            "evidence": self.evidence,
            "unknowns": self.unknowns,
            "findings": [finding.to_dict() for finding in self.findings],
            "decision_gates": [gate.to_dict() for gate in self.decision_gates],
            "next_actions": self.next_actions,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "CaseState":
        return cls(
            case_id=str(payload["case_id"]),
            stage=str(payload["stage"]),
            raw_input=str(payload["raw_input"]),
            workflow_state=str(payload.get("workflow_state", "intake")),
            output_kind=str(payload.get("output_kind", "review-card")),
            blocking_reason=str(payload.get("blocking_reason", "")),
            pending_questions=list(payload.get("pending_questions", [])),
            context_profile=dict(payload.get("context_profile", {})),
            pre_framing_result=(
                PreFramingResult.from_dict(payload["pre_framing_result"])
                if isinstance(payload.get("pre_framing_result"), dict)
                else None
            ),
            normalized_summary=str(payload.get("normalized_summary", "")),
            evidence=list(payload.get("evidence", [])),
            unknowns=list(payload.get("unknowns", [])),
            findings=[
                AnalyzerFinding.from_dict(item) for item in payload.get("findings", [])
            ],
            decision_gates=[
                DecisionGate.from_dict(item) for item in payload.get("decision_gates", [])
            ],
            next_actions=list(payload.get("next_actions", [])),
            metadata=dict(payload.get("metadata", {})),
        )

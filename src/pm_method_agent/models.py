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
class CaseState:
    case_id: str
    stage: str
    raw_input: str
    workflow_state: str = "intake"
    output_kind: str = "review-card"
    blocking_reason: str = ""
    pending_questions: List[str] = field(default_factory=list)
    context_profile: Dict[str, object] = field(default_factory=dict)
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

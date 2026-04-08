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

from backend.natgas.analysts import AnalystEvidence
from backend.natgas.pipeline import run_pipeline


def evidence(role: str) -> AnalystEvidence:
    return AnalystEvidence(
        role=role,
        direction="NEUTRAL",
        confidence=0.5,
        observations=[f"{role} evidence"],
        data_gaps=[],
        risks=[],
    )


def test_pipeline_requires_complete_evidence():
    result = run_pipeline([evidence("technical")])
    assert result.decision.decision.action.value == "NO_TRADE"


def test_pipeline_accepts_complete_role_set():
    roles = ["technical", "fundamental", "weather", "macro", "news", "risk"]
    result = run_pipeline([evidence(role) for role in roles])
    assert result.decision.evidence_count == 6

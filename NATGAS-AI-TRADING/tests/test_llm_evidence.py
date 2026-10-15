"""Tests for the LLM-to-evidence bridge."""

from backend.ai.bull_bear_runner import BullBearResearch
from backend.ai.llm_research import LLMResearchResult
from backend.natgas.llm_evidence import research_to_evidence


def test_llm_research_becomes_explicit_bull_bear_evidence():
    result = research_to_evidence(
        BullBearResearch(
            bull=LLMResearchResult("bull", "test", "bull analysis", 3),
            bear=LLMResearchResult("bear", "test", "bear analysis", 3),
        )
    )

    assert [item.role for item in result] == ["bull", "bear"]
    assert result[0].direction == "BULLISH"
    assert result[1].direction == "BEARISH"
    assert result[0].confidence == 0.5
    assert result[1].confidence == 0.5


def test_empty_research_is_marked_as_a_gap():
    result = research_to_evidence(
        BullBearResearch(
            bull=LLMResearchResult("bull", "test", "", 0),
            bear=LLMResearchResult("bear", "test", "", 0),
        )
    )

    assert result[0].confidence == 0.0
    assert result[0].data_gaps
    assert result[1].data_gaps

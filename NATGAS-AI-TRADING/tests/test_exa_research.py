import pytest

from backend.ai.exa_research import ExaResearchProvider


@pytest.mark.asyncio
async def test_research_provider_normalizes_records():
    async def fake_search(query, limit):
        assert "NATGAS" in query
        assert limit == 3
        return [{
            "title": "EIA Natural Gas Storage",
            "url": "https://example.com/eia",
            "publishedDate": "2026-09-28",
            "score": 0.91,
        }]

    provider = ExaResearchProvider(fake_search)
    sources = await provider.search("NATGAS EIA storage", 3)

    assert len(sources) == 1
    assert sources[0].source_type == "exa"
    assert sources[0].relevance == 0.91

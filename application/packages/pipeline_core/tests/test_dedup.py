from pipeline_core.dedup import Citation, deduplicate_citations, rule_based_stance


def test_dedup_by_doi_takes_priority():
    citations = [
        Citation(title="Paper A", doi="10.1/abc", source_query="query1"),
        Citation(title="Paper A (dup)", doi="10.1/abc", source_query="query2"),
    ]
    result = deduplicate_citations(citations)
    assert len(result) == 1
    assert sorted(result[0].raw["matched_queries"]) == ["query1", "query2"]


def test_dedup_falls_back_to_title_year_without_ids():
    citations = [
        Citation(title="Some Trial Results", year=2020, source_query="q1"),
        Citation(title="some trial   results", year=2020, source_query="q2"),
        Citation(title="Some Trial Results", year=2021, source_query="q3"),
    ]
    result = deduplicate_citations(citations)
    assert len(result) == 2  # 2020 dup collapsed, 2021 distinct


def test_rule_based_stance_supporting():
    assert rule_based_stance("The regimen showed significant improvement in survival.") == "supporting"


def test_rule_based_stance_conflicting():
    assert rule_based_stance("The trial failed to show any benefit and reported resistance.") == "conflicting"


def test_rule_based_stance_unclear_when_mixed():
    text = "Effective in early trials but later failed to show benefit."
    assert rule_based_stance(text) == "unclear"


def test_rule_based_stance_unclear_when_empty():
    assert rule_based_stance(None) == "unclear"
    assert rule_based_stance("") == "unclear"

import pytest

from pipeline_core.safety import assert_safe, check_safety, is_safe


@pytest.mark.parametrize(
    "text",
    [
        "This is the best drug for this patient.",
        "We recommend paclitaxel for this profile.",
        "The patient is eligible for trial NCT001.",
        "This treatment is guaranteed to cure the disease.",
    ],
)
def test_unsafe_phrases_are_caught(text):
    assert not is_safe(text)
    assert len(check_safety(text)) >= 1
    with pytest.raises(ValueError):
        assert_safe(text)


@pytest.mark.parametrize(
    "text",
    [
        "Docetaxel shows a GCTX reversal percentile of 0.82 for this cluster.",
        "This drug is a discovery hypothesis and requires clinician review.",
        "Insufficient information is available to assess trial fit for this patient.",
    ],
)
def test_safe_phrases_pass(text):
    assert is_safe(text)
    assert check_safety(text) == []
    assert_safe(text)  # should not raise


@pytest.mark.parametrize(
    "text",
    [
        "palbociclib is the top choice for this profile",
        "this is the best agent in the prediction set",
        "ribociclib is the first-line choice",
        "insufficient data, but the set still includes tamoxifen",
        "low confidence, however the interval remains narrow",
    ],
)
def test_prediction_set_ranking_and_hedged_abstention_raise(text):
    assert not is_safe(text)
    with pytest.raises(ValueError):
        assert_safe(text)

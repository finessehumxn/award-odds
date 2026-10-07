import pytest

from award_odds.client import Award
from award_odds.stats import percentile, size_stats, summarize

from .conftest import load


def award(key, amount, name=None):
    return Award(award_id=f"A-{key}-{amount}", recipient_name=name or key.upper(),
                 recipient_key=key, amount=amount, start_date=None, agency=None)


def test_percentile_linear_interpolation():
    v = [10.0, 20.0, 30.0, 40.0]
    assert percentile(v, 0) == 10
    assert percentile(v, 100) == 40
    assert percentile(v, 50) == 25
    assert percentile(v, 25) == pytest.approx(17.5)
    assert percentile([5.0], 75) == 5


def test_percentile_rejects_bad_input():
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1.0], 101)


def test_size_stats_excludes_non_positive():
    s = size_stats([100, -50, 0, 300, 200])
    assert s.count == 3
    assert s.total == 600
    assert s.minimum == 100 and s.maximum == 300
    assert s.median == 200
    assert size_stats([0, -1]) is None


def test_summarize_groups_by_recipient_and_measures_concentration():
    awards = [award("a", 500), award("a", 300), award("b", 100), award("c", 100), award("c", -40)]
    s = summarize(awards, top_n=2)
    assert s.awards_fetched == 5
    assert s.non_positive == 1
    assert s.unique_recipients == 3
    assert [(r.name, r.awards, r.dollars) for r in s.top_recipients] == [("A", 2, 800), ("B", 1, 100)]
    assert s.top_recipients[0].share == pytest.approx(0.8)
    # only 3 recipients, so the top 10 hold everything
    assert s.top10_share == pytest.approx(1.0)


def test_summarize_empty():
    s = summarize([])
    assert s.sizes is None and s.top10_share == 0 and s.unique_recipients == 0


def test_summarize_real_epa_rows():
    rows = load("epa_66951_awards_page1.json")["results"] + load("epa_66951_awards_page2.json")["results"]
    s = summarize([Award.from_row(r) for r in rows])
    assert s.awards_fetched == 131
    assert s.unique_recipients == 119
    assert s.sizes.median == 100000
    assert s.sizes.maximum == 100000
    assert s.top10_share == pytest.approx(0.156, abs=0.001)


def test_multi_program_share():
    import dataclasses
    a = dataclasses.replace(award("a", 300), listings=("93.243", "93.788"))
    b = dataclasses.replace(award("b", 100), listings=("93.243",))
    s = summarize([a, b])
    assert s.multi_program == 1
    assert s.multi_program_dollar_share == pytest.approx(0.75)


def test_sizes_use_single_listing_awards_only():
    import dataclasses
    multi = dataclasses.replace(award("big", 9_000_000), listings=("93.243", "93.788"))
    rest = [dataclasses.replace(award(k, v), listings=("93.243",)) for k, v in
            [("a", 100), ("b", 200), ("c", 300)]]
    s = summarize([multi, *rest])
    assert s.sizes.count == 3 and s.sizes.maximum == 300
    assert s.total_dollars == 9_000_600  # concentration still sees the whole award
    assert not s.sizes_include_multi
    only_multi = summarize([multi])
    assert only_multi.sizes.count == 1 and only_multi.sizes_include_multi

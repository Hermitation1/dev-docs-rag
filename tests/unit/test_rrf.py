import pytest

from dev_docs_rag.services.search import fuse_rrf

pytestmark = pytest.mark.unit


def test_fuses_two_ranked_lists():
    fused = fuse_rrf([1, 2, 3], [3, 4], k=60)

    assert [chunk_id for chunk_id, _ in fused] == [3, 1, 2, 4]


def test_document_found_by_both_methods_wins():
    fused = dict(fuse_rrf([1, 2], [2, 3], k=60))

    assert fused[2] > fused[1]
    assert fused[2] > fused[3]


def test_scores_match_the_formula():
    fused = dict(fuse_rrf([7], [7], k=60))

    assert fused[7] == pytest.approx(2 / 61)


def test_empty_lists_produce_no_hits():
    assert fuse_rrf([], [], k=60) == []

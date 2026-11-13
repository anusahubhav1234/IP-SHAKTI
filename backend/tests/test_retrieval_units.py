import uuid

from app.rag.fusion import RRF_K, reciprocal_rank_fusion
from app.rag.tokenizer import tokenize
from app.rag.types import Hit
from tests.test_text_pipeline import HINDI, TELUGU


def _hit(i, **kw):
    return Hit(chunk_id=uuid.UUID(int=i), document_id=uuid.UUID(int=999), document_title="d", page_number=1,
               section_heading=None, text=f"t{i}", language="en", **kw)


def test_tokenizer_keeps_indic_words_whole():
    # \w-based splitting would cut these at vowel signs and inflate the token count
    assert len(tokenize(TELUGU)) == len(TELUGU.split())
    assert len(tokenize(HINDI)) == len(HINDI.split())
    assert "హాజరు" in tokenize(TELUGU) and "उपस्थिति" in tokenize(HINDI)


def test_tokenizer_english_rules():
    assert tokenize("The Minimum Attendance is 75%!") == ["minimum", "attendance", "75"]
    assert tokenize("") == [] and tokenize("the of and") == []
    assert tokenize("Exami\u0301nation") == tokenize("Exam\u00ednation")  # NFC-normalised


def test_rrf_scores_and_order_match_the_formula():
    x, y, z, w = (1, 2, 3, 4)
    a = [_hit(x, vector_rank=1, vector_score=.9), _hit(y, vector_rank=2, vector_score=.8), _hit(z, vector_rank=3, vector_score=.7)]
    b = [_hit(y, bm25_rank=1, bm25_score=9.), _hit(z, bm25_rank=2, bm25_score=5.), _hit(w, bm25_rank=3, bm25_score=1.)]
    fused = reciprocal_rank_fusion([a, b])
    k = RRF_K
    expected = {x: 1 / (k + 1), y: 1 / (k + 2) + 1 / (k + 1), z: 1 / (k + 3) + 1 / (k + 2), w: 1 / (k + 3)}
    got = {h.chunk_id.int: h.score for h in fused}
    for key, val in expected.items():
        assert abs(got[key] - val) < 1e-12
    assert [h.chunk_id.int for h in fused] == [y, z, x, w]  # agreement of both rankers beats a lone #1


def test_rrf_merges_component_ranks_and_is_deterministic():
    a = [_hit(1, vector_rank=1, vector_score=.9)]
    b = [_hit(1, bm25_rank=4, bm25_score=2.5)]
    (h,) = reciprocal_rank_fusion([a, b])
    assert (h.vector_rank, h.vector_score, h.bm25_rank, h.bm25_score) == (1, .9, 4, 2.5)
    ties = [reciprocal_rank_fusion([[_hit(5)], [_hit(3)]]) for _ in range(3)]
    assert len({tuple(x.chunk_id for x in t) for t in ties}) == 1
    assert reciprocal_rank_fusion([[], []]) == []

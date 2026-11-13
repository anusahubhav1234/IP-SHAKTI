"""TEST-ONLY embedder: deterministic hashed bag-of-words. It lets pipeline tests run without
downloading a model. It is never used outside the test suite and says nothing about retrieval quality."""
import math
import re
import zlib

from app.rag.embeddings import Embedder


class FakeEmbedder(Embedder):
    dim = 384

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"\w+", text.lower()):
            v[zlib.crc32(tok.encode()) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


import json
import re

from app.rag.llm import LLMClient, LLMResult

_SRC = re.compile(r'<<<SOURCE id="(S\d+)" document="([^"]*)"(?: page="(\d+)")?[^>]*>>>\n(.*?)\n<<<END SOURCE', re.S)


def sources_in(user_prompt: str) -> dict[str, dict]:
    return {m[0]: {"document": m[1], "page": m[2], "text": m[3]} for m in _SRC.findall(user_prompt)}


def find_source(user_prompt: str, needle: str) -> str:
    for sid, s in sources_in(user_prompt).items():
        if needle in s["text"]:
            return sid
    raise AssertionError(f"no source containing {needle!r} in prompt")


class ScriptedLLM(LLMClient):
    """TEST-ONLY. `handler(system, user)` returns a dict (JSON-encoded), a str (returned raw) or raises LLMError.
    It proves the pipeline's handling of model output; it says nothing about real model quality."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def generate_json(self, system, user, json_schema=None):
        self.calls.append((system, user))
        out = self.handler(system, user)
        return LLMResult(text=out if isinstance(out, str) else json.dumps(out, ensure_ascii=False))


def install_llm(monkeypatch, answer_handler, rewrite_handler=None):
    """Patches BOTH LLM entry points (answering and query rewriting). Rewrite calls are recognised by their system
    prompt; unless `rewrite_handler(question, prompt)` is given they return the follow-up unchanged."""
    def handler(system, user):
        if system.startswith("You rewrite"):
            q = user.rsplit("FOLLOW-UP QUESTION:", 1)[1].strip()
            return rewrite_handler(q, user) if rewrite_handler else {"standalone_question": q}
        return answer_handler(system, user)
    llm = ScriptedLLM(handler)
    monkeypatch.setattr("app.services.answering.get_llm_client", lambda: llm)
    monkeypatch.setattr("app.rag.rewrite.get_llm_client", lambda: llm)
    monkeypatch.setattr("app.services.comparison.get_llm_client", lambda: llm)
    return llm


def answer_calls(llm):
    return [c for c in llm.calls if not c[0].startswith("You rewrite")]


def rewrite_calls(llm):
    return [c for c in llm.calls if c[0].startswith("You rewrite")]


import re as _re

from app.rag.reranker import Reranker


class OverlapReranker(Reranker):
    """TEST-ONLY: scores a passage by how many distinct query words it contains."""

    def score(self, query, passages):
        q = set(_re.findall(r"\w+", query.lower()))
        return [float(len(q & set(_re.findall(r"\w+", p.lower())))) for p in passages]

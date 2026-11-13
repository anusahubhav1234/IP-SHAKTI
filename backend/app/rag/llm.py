"""LLM client abstraction + Gemini REST implementation (httpx, no SDK).

The REST shape (x-goog-api-key header, :generateContent, systemInstruction, generationConfig with
responseMimeType/responseJsonSchema) follows Google's public docs, which were mid-transition when this
was written. To be safe the client (1) also asks for JSON in the prompt, (2) retries once without the
schema fields if the API rejects them, and (3) parses tolerantly. Model-side behaviour cannot be verified
without a key: run `python -m app.scripts.check_llm` once you have one."""
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

logger = logging.getLogger("sakti.llm")


class LLMError(Exception):
    """kind: not_configured | auth | rate_limited | unavailable | blocked | bad_response"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class LLMResult:
    text: str
    model: str | None = None


class LLMClient(ABC):
    @abstractmethod
    def generate_json(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult: ...


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "insufficient_evidence": {"type": "boolean"},
        "citations": {"type": "array", "items": {"type": "object", "properties": {
            "source_id": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["source_id", "quote"]}},
    },
    "required": ["answer", "insufficient_evidence", "citations"],
}


class LLMCitation(BaseModel):
    source_id: str
    quote: str = ""


class LLMAnswer(BaseModel):
    answer: str = ""
    insufficient_evidence: bool = False
    citations: list[LLMCitation] = Field(default_factory=list)


def parse_llm_answer(text: str) -> LLMAnswer:
    """Tolerant JSON extraction (code fences, stray prose) followed by strict schema validation."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    braces = t[t.find("{"): t.rfind("}") + 1] if "{" in t and "}" in t else ""
    for candidate in (t, braces):
        if not candidate:
            continue
        try:
            return LLMAnswer.model_validate(json.loads(candidate))
        except (json.JSONDecodeError, ValidationError):
            continue
    raise LLMError("bad_response", "The AI service returned an unreadable response.")


class GeminiClient(LLMClient):
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._s = get_settings()
        self._http = httpx.Client(timeout=self._s.llm_timeout_seconds, transport=transport)

    def _key(self) -> str:
        k = self._s.gemini_api_key
        if k is None or not k.get_secret_value().strip():
            raise LLMError("not_configured", "The AI service is not configured (missing GEMINI_API_KEY).")
        return k.get_secret_value().strip()

    def _payload(self, system, user, json_schema, structured) -> dict:
        gen = {"temperature": self._s.llm_temperature, "maxOutputTokens": self._s.llm_max_output_tokens}
        if structured:
            gen["responseMimeType"] = "application/json"
            if json_schema:
                gen["responseJsonSchema"] = json_schema
        return {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen}

    def generate_json(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        key = self._key()
        url = f"{self._s.gemini_base_url}/models/{self._s.gemini_model}:generateContent"
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        structured, attempts, last = True, 0, None
        while attempts <= self._s.llm_max_retries + 1:
            attempts += 1
            try:
                r = self._http.post(url, headers=headers, json=self._payload(system, user, json_schema, structured))
            except httpx.HTTPError as exc:
                last = LLMError("unavailable", "The AI service did not respond in time.")
                logger.warning("Gemini request failed: %s", type(exc).__name__)
            else:
                if r.status_code == 200:
                    return self._parse(r.json())
                if r.status_code == 400 and structured and any(
                        w in r.text for w in ("responseJsonSchema", "responseMimeType", "response_schema")):
                    structured = False  # API shape changed / unsupported: fall back to prompt-only JSON
                    continue
                if r.status_code in (401, 403):
                    raise LLMError("auth", "The AI service rejected the API key.")
                if r.status_code == 429:
                    raise LLMError("rate_limited", "The AI service is busy (rate limit). Please retry shortly.")
                if r.status_code == 404:
                    raise LLMError("not_configured", f"Model '{self._s.gemini_model}' was not found; check GEMINI_MODEL.")
                if r.status_code >= 500:
                    last = LLMError("unavailable", "The AI service is temporarily unavailable.")
                else:
                    logger.warning("Gemini returned %s", r.status_code)
                    raise LLMError("bad_response", "The AI service rejected the request.")
            if attempts > self._s.llm_max_retries:
                break
            time.sleep(1.0 * attempts)
        raise last or LLMError("unavailable", "The AI service is unavailable.")

    @staticmethod
    def _parse(data: dict) -> LLMResult:
        if (data.get("promptFeedback") or {}).get("blockReason"):
            raise LLMError("blocked", "The AI service declined to process this request.")
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError("bad_response", "The AI service returned no answer.")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            if cands[0].get("finishReason") in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST"):
                raise LLMError("blocked", "The AI service declined to answer this request.")
            raise LLMError("bad_response", "The AI service returned an empty answer.")
        return LLMResult(text=text, model=data.get("modelVersion"))


@lru_cache
def get_llm_client() -> LLMClient:
    return GeminiClient()

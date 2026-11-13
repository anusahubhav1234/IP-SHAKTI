"""Verify your Gemini key and model: python -m app.scripts.check_llm
Lists models your key can call generateContent on, then sends one tiny request with GEMINI_MODEL."""
import sys

import httpx

from app.core.config import get_settings
from app.rag.llm import LLMError, get_llm_client


def main() -> None:
    s = get_settings()
    if s.gemini_api_key is None:
        sys.exit("GEMINI_API_KEY is not set (get one at https://aistudio.google.com/apikey).")
    r = httpx.get(f"{s.gemini_base_url}/models", params={"pageSize": 200},
                  headers={"x-goog-api-key": s.gemini_api_key.get_secret_value()}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Could not list models (HTTP {r.status_code}). Check the key.")
    names = sorted(m["name"].removeprefix("models/") for m in r.json().get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", []))
    print("Models usable with generateContent:\n  " + "\n  ".join(names))
    print(f"\nConfigured GEMINI_MODEL = {s.gemini_model}  ({'listed' if s.gemini_model in names else 'NOT in the list above'})")
    try:
        res = get_llm_client().generate_json('Reply with JSON only.', 'Return {"answer":"ok","insufficient_evidence":false,"citations":[]}')
        print("Test call OK. Raw reply:", res.text[:200])
    except LLMError as exc:
        sys.exit(f"Test call failed [{exc.kind}]: {exc}")


if __name__ == "__main__":
    main()

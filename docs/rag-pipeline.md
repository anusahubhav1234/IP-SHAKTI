# RAG answer pipeline (Phase 4)

`POST /api/chat` -> `services/answering.py`

1. **Language**: script-based detection of the question (en/hi/te). Response language = request `language` or the detected one.
2. **Retrieve**: same `retrieve()` as the search API (vector | bm25 | hybrid, default hybrid, top 5).
3. **Evidence gate**: no hits -> the LLM is *not called*; the answer is a fixed "insufficient evidence" message in the response language. An optional cosine floor (`MIN_EVIDENCE_SIMILARITY`) exists but is off until calibrated on the real embedding model.
4. **Prompt**: sources are fenced as `<<<SOURCE id="S1" document=".." page="..">>>`; look-alike delimiters are stripped from document text; the system prompt declares sources and history to be untrusted data.
5. **LLM (Gemini REST)**: returns JSON `{answer, insufficient_evidence, citations:[{source_id, quote}]}`; the answer carries `[S1]` markers.
6. **Verification**: a citation is *verified* only if its quote (normalised for case/spacing/punctuation) occurs in the chunk it points to. Page numbers and titles always come from the database record of the chunk, never from the model. Unknown source ids are dropped. If **no** citation verifies, the answer is withheld (`unverified_withheld`).
7. **Persist**: user + assistant messages and citation snapshots; audit log stores status/mode/language/latency but never the question text.

| status | meaning |
|---|---|
| answered | at least one citation verified; unverified ones are flagged `verified=false` |
| insufficient_evidence | nothing retrieved, or the model said the sources do not answer it |
| unverified_withheld | the model answered but no citation could be verified |

Known limits: follow-up questions are *not yet rewritten* for retrieval (Phase 5); the Hindi/Telugu fixed messages need native-speaker review; verification proves the quote exists in the cited chunk, not that the answer's reasoning is correct (faithfulness is measured in Phase 7).

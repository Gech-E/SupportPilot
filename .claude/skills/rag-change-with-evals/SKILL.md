---
name: rag-change-with-evals
description: Procedure for changing chunking, embeddings, retrieval, reranking, prompts, confidence thresholds, or models in SupportPilot. Requires measuring quality before and after on the golden set. Use for any change that can alter answer quality.
---

# Change the RAG pipeline with evidence

Quality changes are accepted only when measured. "It looks better" is not evidence.

## Before changing anything
1. Run the dev golden set on the current code and save the report:
   `python -m evals.run --set golden_dev.jsonl --config <current config> --out reports/before.json`
2. Note the configuration: prompt version, model names, chunking parameters, retrieval settings.

## Make one change
- Change **one variable** per experiment (chunk size, fusion method, reranker, prompt text, threshold).
- Prompts live in `prompts/` as versioned files. Create `prompt_vN+1`; never edit a released prompt.
- Keep providers behind their interfaces so the change is a configuration change.

## Measure
3. Run the same set again: `--out reports/after.json`.
4. Compare with a **paired** comparison on the same cases (bootstrap or McNemar). With about 150 cases,
   differences smaller than roughly 6 points on a headline metric are noise.
5. Check all layers, not only the target metric:
   retrieval (Recall@k, MRR), generation (correctness, faithfulness, citation validity),
   behaviour (refusal accuracy, false refusal rate), safety (red-team pass rate), system (p95 latency, cost).

## Decide
- Keep the change only if the targeted metric improves **and** no other metric regresses beyond noise,
  **and** latency and cost stay within budget (p95 time to first token under 1.5 s, under $0.01 per answer).
- Never tune on the held-out test set. It is run once per release candidate.

## Record
6. Add a row to `docs/eval-log.md`: date, change, hypothesis, before and after for each metric, decision.
7. If the change was not kept, record that too. Failed experiments are valuable interview material.

## Guardrail checks
- Red-team set must pass fully (no prompt leak, no cross-tenant data, no off-policy behaviour).
- Any answer with factual content must still carry a valid citation, or hand off.

# Trust Bench

A reproducible benchmark for the question RAG marketing never answers:
**does the system refuse when the answer is not in the corpus, or does it
guess?**

- `corpus/` — a synthetic company knowledge base (Meridian Dynamics) with
  precisely known facts.
- `questions.jsonl` — 20 answerable questions (with expected keywords and the
  document that must be cited) and 15 **trap questions** whose answers are
  deliberately absent from the corpus — including premise-injection traps that
  reference real documents but ask for facts that are not in them.
- `run.py` — uploads the corpus, runs every question through `/api/v1/query`,
  and scores:

| Metric | Meaning |
|---|---|
| Grounded answer rate | answered ∧ correct keywords ∧ has citations, over answerable questions |
| Citation doc accuracy | the cited source is the document that actually contains the fact |
| **False answer rate** | traps that got an answer anyway — the hallucination number |
| Trap refusal rate | traps correctly declined |

## Run it

```bash
# against a running deployment
python bench/run.py --base-url http://127.0.0.1:8000 \
  --email admin@example.com --password '...'
# or with an API key
python bench/run.py --api-key ekc_...
```

Re-runs are safe: corpus uploads are skipped when the files already exist.
Results land in `bench/results/` (gitignored). The corpus and questions are
fixed and versioned, so numbers are comparable across runs, configs, and —
via any OpenAI-compatible adapter — other RAG systems.

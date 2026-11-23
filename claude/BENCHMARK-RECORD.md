# Benchmark record

Template. Read by Claude before an LLM model analysis or benchmark (add a pointer to it in your own `CLAUDE.md`). It holds the format only: write your results in your repo, in `<path to your results record>`.

Each item is a value, a pointer to the repo's record, `not recorded` (it exists, but is unknown; never guess) or `not applicable` (it cannot exist for this route; add a short reason).

- Who: who ran it, first or third party.
- Model: provider, exact model ID and version, access route, open or closed weights, quantization if local. Context window and knowledge cutoff from the provider's model page, with the date read.
- Setup: date, harness version and commit, SDK or CLI version, the parameters the route exposes (temperature, max tokens, top_p, seed, reasoning budget, system prompt), prompt caching, retries.
- Data: dataset name, version, split or subset filter, data fingerprint, sample count, prompt template, scoring method, grader version.
- Quality: score with confidence interval (name the method and its n), repeat count, failure, refusal and timeout counts, each excluded sample and why.
- Speed: time to first token if streaming, output tokens per second (say if thinking tokens count), end-to-end latency as p50 and a tail value (p90 or p95, say which), concurrency, input size.
- Cost: billing route (API or subscription, API-equivalent), input, output, cache-read and cache-write token counts, price per million tokens and its date.
- Repeat: the exact command, the config file, known limits, raw per-sample output stored where the repo's data rules allow. Prompts from customer data stay out of the results doc.

Compare models only on the same data, parameters and scoring.

This applies to new runs: do not rewrite old results or change a run in progress. A repo's own manifest, config or results page counts as the record: point to it, do not copy it. A repo's stricter rule wins.

Where it fits, store quality and setup items in the Every Eval Ever schema (`github.com/evaleval/every_eval_ever`; check its current version first). Speed and cost go in `additional_details`.

# Cohere Qwen3.8-Flash-Next investigation trace

Source: [CohereLabs/10-2026-qwen-investigation-traces](https://huggingface.co/datasets/CohereLabs/10-2026-qwen-investigation-traces) on Hugging Face, published by Cohere alongside
[their write-up](https://cohere.com/blog/concerning-behaviour-popular-open-weight-ai-model). All credit for the trace goes to Cohere.

The dataset card does not declare a license, so this repo does **not** redistribute the trace.
Fetch it (pinned revision, sha256-verified) with:

```sh
./scripts/fetch_cohere_trace.sh
```

This writes `fixtures/cohere/qwen-investigation.jsonl` (git-ignored). The regression test
`tests/test_cohere_regression.py` uses it when present and skips otherwise.

# Fresh held-out set (round 2)

55 traces, labelled in `labels.json` **before** saysdoes was run on any of them; that labelling commit comes before any saysdoes result on this set. Labels were written by the AI agent that drives this project, not by a human. The full policy is in `labels.json` under `method`.

| origin | consistent | contradiction |
|---|---|---|
| natural | 36 | 2 |
| instructed | 10 | 1 |
| spliced | 0 | 6 |

Every trace is in Claude Code format: session files (`claude-code-session`) or `claude -p` stream-json output (`claude-code-stream-json`).

## Sources and licenses

| source | revision | license | traces |
|---|---|---|---|
| [trace-commons/agent-traces](https://huggingface.co/datasets/trace-commons/agent-traces) | `112ebd4d03ce852b00e935d523107c3d0c9a65bf` | CC-BY-4.0 | 7 (+2 spliced) |
| [crispwisp/wisp-claude-code-sessions](https://huggingface.co/datasets/crispwisp/wisp-claude-code-sessions) | `c2c90b59174318ab0b163ec9c9ac82bb879288ce` | MIT | 4 (+1 spliced) |
| [choucsan/mimo-claude-code-traces-1k](https://huggingface.co/datasets/choucsan/mimo-claude-code-traces-1k) | `39cc3fc3ed608fff800220445bad9eb1738516f8` | MIT | 15 (+2 spliced) |
| generated here: `generation/gen_fresh.py` + `generation/template/` (Claude Code 2.1.311, `--effort medium`) | — | repo license | 23 (+1 spliced) |

Each item's `source_path` in `labels.json` gives the file's path inside its dataset. Public traces are copied unmodified. They were already anonymised upstream: trace-commons uses `/home/USER`, crispwisp uses `/home/me`, and mimo uses `/data/agent/choucisan`.

In the generated traces, scratch paths were rewritten to `/work/tally`, `/scratch` and `/home/user`. The trace-commons material is CC-BY-4.0 and requires attribution to the dataset above.

## Caveats

- **Few real contradictions.** Only 2 natural contradictions turned up: both are mimo traces where the model's thinking says "I'll just explain/show the code" and the same turn then writes a file. When asked to state a commitment and then break it, current Claude models mostly refused or disclaimed it first. Those runs are labelled consistent, and they are good false-positive tests.
- **Splices are synthetic.** `generation/splice_fresh.py` inserts one fabricated tool call and its result, marked `_saysdoes_eval_spliced`, and none of those commands were ever executed. It ran in a scratch layout (`raw/<dataset>/…`, `runs/<id>/…`), not inside this repo.
- **Public selection is biased.** Public traces were picked with a phrase grep for commitment-like language, plus a few sessions with no commitments as controls. Two long trace-commons sessions were not read end to end.

# research/

Experiment code for the research track ([docs/research/BUILD_BRIEF.md](../docs/research/BUILD_BRIEF.md)). It lives apart
from the product (`src/tracelens/`) so the product keeps its promise: standard library only, no API keys, no cloud,
deterministic. Nothing here is imported by `src/tracelens/`.

Planned contents (none written yet, in brief order): `mutants/` and `run.py` and `oracles.py` (R2), `radar_baselines.py`
(R6), `probe_effect.py` (R4), `precond_suite/` (R5), `llm_repair/` (R5.3, only with the user's approval and their own API key),
`package_dataset.py` (R7), and `make_numbers.py`, which regenerates every number in `docs/research/numbers.json` and
`numbers.tex` from committed data (no hand-typed numbers in any paper).

For each experiment this file will list: inputs, outputs, expected run time and the command. Traces stay out of git
(`data/research/`); committed are per-capture JSON summaries and SHA-256 manifests.

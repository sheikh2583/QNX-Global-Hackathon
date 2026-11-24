# Related work (skeleton, 2026-11-25)

**Every entry below is (unverified).** None was opened in this session; the citations come from the research brief and from
memory, and the summaries are deliberately left empty rather than guessed. Rule from the brief: an entry only counts once it
has a full citation, a URL that was actually opened, a two-sentence summary in our own words, and "how we differ". Unverified
entries never go into a paper.

The gap we want to test (to be confirmed or refuted by this reading, not assumed): prior concurrency-repair work fixes
correctness bugs and checks the fix with tests or symbolic execution; none repairs priority or timing bugs or uses kernel-trace
distributions as the acceptance oracle. Detection alone is not the novelty.

| Area | Work | Status | URL opened | Summary | How we differ |
|---|---|---|---|---|---|
| Trace analysis for real-time | Cote and Dagenais, "Problem detection in real-time systems by trace analysis" (2016) | (unverified) | | | |
| | Rajotte, trace-based detection on Linux (2014) | (unverified) | | | |
| | Desfossez, Desnoyers and Dagenais, "Runtime latency detection and analysis" (2016) | (unverified) | | | |
| | Trace Compass | (unverified) | | | |
| | QNX IDE guide: "Detecting priority inversion", "Client/Server CPU Statistics" | (unverified) | | | |
| Concurrency repair | AFix (PLDI 2011) | (unverified) | | | |
| | CFix (OSDI 2012) | (unverified) | | | |
| | HFix (Liu et al.) | (unverified) | | | |
| | SDRacer (arXiv 2305.17869) | (unverified) | | | |
| | ESfix (2025) | (unverified) | | | |
| | Automatic Software Repair bibliography (arXiv 1807.00515) | (unverified) | | | |
| Performance-test statistics | Kalibera and Jones, "Rigorous benchmarking in reasonable time" | (unverified) | | | |
| | Daly et al., change-point detection at MongoDB (ICPE 2020) | (unverified) | | | |
| | Laaber et al. on cloud benchmarking | (unverified) | | | |
| | Holm (1979); Clopper and Pearson (1934) | (unverified) | | | |
| Trace anomaly detection | Kohyarnejadfard thesis (2022) | (unverified) | | | |
| | Fournier, Ezzati-Jivan et al. (arXiv 2103.04954) | (unverified) | | | |
| | DeepLog (Du et al., CCS 2017) | (unverified) | | | |
| Sim-to-real | Tobin et al. (2017), domain randomisation | (unverified) | | | |
| Concurrency bug studies | Lu et al., "Learning from Mistakes" (ASPLOS 2008); RADBench (Jalbert, Pereira, Sen 2011) | (unverified) | | | |
| QNX semantics | QNX 8.0 System Architecture: priority inheritance, messages, server boost, `_NTO_CHF_FIXED_PRIORITY` | (unverified) | | | |

## Search pass still to do (record what was searched and when)

2024-2026: "LLM program repair concurrency", "performance bug repair", "real-time systems program repair", "kernel trace
oracle", "RTOS debugging tool". Not yet run.

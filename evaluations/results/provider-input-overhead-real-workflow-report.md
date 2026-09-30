# Real Conceptualize provider-input trace

Commit `e437f491d6f884a317ca42c1fb4a402d9a818f13`; frozen V0.9 fixture SHA-256 `de91afc78218b084a6e569ba1e611d952490861dea9864fe720f55bb18c42370`; matched base configuration SHA-256 `dff479041b5e6b35da3d3cd6e17c873455593c398b105d18b1c5011383ea9150`. The new runs used Codex CLI **0.159.0**, `gpt-6-sol`, low reasoning, a read-only sandbox, and the same host flags across conditions. Earlier synthetic controls used CLI 0.157.1, so cross-version deltas are diagnostic.

The proven activated host prompt contains `@Conceptualize` and the task; the frozen 119-message history is loaded inside the MCP fixture. An initial full-history-in-host F1 trial answered without calling Conceptualize and is preserved under `real-workflow-v1`. The analyzed runs use the proven prompt; F−1 and F0 use the same prompt without `@Conceptualize`. Request usage reconciles exactly with turn aggregates. Raw evidence is in `provider-input-overhead-real-workflow-proven-v3.json` and its referenced run directories.

## Matched conditions

Values are valid-run means. F0 run 1 spontaneously called Conceptualize without the marker (five requests, 123,321 input); it is preserved but excluded from the unused-server means.

| Condition | Valid runs | Requests/run | Mean input | Cached | Uncached | Output | Turn elapsed |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| F−1, no Conceptualize MCP | 3 | 3, 4, 4 | 71,151 | 53,163 | 17,988 | 338 | 17,779 ms |
| F0, MCP present and unused | 2 of 3 | 4, 4 | 102,922 | 76,096 | 26,826 | 318 | 22,100 ms |
| F1, `@Conceptualize` | 3 | 3, 5, 3 | 102,914 | 82,219 | 20,696 | 522 | 27,022 ms |

Mean input per provider request was 19,405, 25,730, and 28,068 respectively. F1 made exactly one `conceptualize_context` call and one `mcp.tools.call` span per run, with no Conceptualize retry. The host also performed MCP startup and tool listing. Model-emitted built-in `exec` discovery is recorded separately.

F−1 first requests were 14,062–14,089 input tokens. F0 first requests were 19,600 and F1 first requests were 19,605. Real MCP registration therefore increased the initial request by about 5,530 tokens under this CLI and host setup. The local server instruction and schema estimates are approximately 73 and 74 tokens; the larger provider delta cannot be partitioned from the available request bodies.

For paired repetitions 2 and 3, valid F0 − F−1 input was +26,935 and +17,736 (mean +22,336), with no request-count change. F1 − F0 input was +35,065 and −14,037 (mean +10,514), with request-count changes of +1 and −1. These total deltas include variable model discovery and are not fixed registration or activation costs. F0's spontaneous call makes presence-only use of its first repetition invalid.

## F1 token waterfalls

| Run | Request | Input | Cached | Uncached | Output | Sampling | Model action / predecessor |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 19,605 | 18,560 | 1,045 | 79 | 8,345 ms | Search tool catalog with `exec` |
| 1 | 2 | 29,254 | 19,456 | 9,798 | 77 | 3,860 ms | After ~10,518 local-token catalog output; call Conceptualize |
| 1 | 3 | 33,013 | 29,056 | 3,957 | 340 | 7,339 ms | After ~3,842 local-token tool output; final answer |
| 2 | 1 | 19,605 | 11,904 | 7,701 | 69 | 4,723 ms | Search tool catalog |
| 2 | 2 | 29,265 | 19,456 | 9,809 | 52 | 3,625 ms | Further catalog filter |
| 2 | 3 | 29,408 | 29,056 | 352 | 35 | 1,911 ms | Inspect Conceptualize tool description |
| 2 | 4 | 29,593 | 29,184 | 409 | 76 | 3,277 ms | Call Conceptualize |
| 2 | 5 | 33,282 | 29,440 | 3,842 | 323 | 7,649 ms | After ~3,771 local-token tool output; final answer |
| 3 | 1 | 19,605 | 11,904 | 7,701 | 89 | 5,065 ms | Search tool catalog |
| 3 | 2 | 29,340 | 19,456 | 9,884 | 92 | 4,244 ms | After ~10,685 local-token catalog output; call Conceptualize |
| 3 | 3 | 36,773 | 29,184 | 7,589 | 333 | 9,391 ms | After ~7,655 local-token tool output; final answer |

Totals: **81,872**, **141,153**, and **85,718** input tokens. The five-request run spent **58,673 gross input tokens in two additional catalog-inspection requests** before its Conceptualize call. It exceeded the mean of the two three-request runs by 57,358 tokens. This is the largest measured avoidable source. The tool-catalog output was about 10.5–10.7k local tokens before the call in all F1 runs.

Working Contexts were 3,376, 3,307, and 3,376 local tokens. Prior response-size scaling predicts about one provider input token per added context token, or roughly 3.3k for one representation. In F1 run 3, the code-mode tool output displayed the context twice, and the final request was roughly 3.5–3.8k input tokens larger than the other F1 final requests. That serialization effect is inferred from the trace; exact provider bodies are unavailable.

The raw 8,292-token history was not in the proven host prompt and thus was not repeatedly sent before the MCP call. Repeated requests carried the host/tool prefix and accumulated discovery exchanges. Using the initial 19,605-input request as a rough prefix scale implies about 39,210 additional repeated-prefix input for a three-request run and 78,420 for the five-request run. These are approximations, not byte-level replay proof.

## Effectiveness and remaining uncertainty

The frozen semantic rubric confirmed **8/8 retrieval and 8/8 Working Context coverage in all three F1 runs**. Final answers passed **2/3**; run 3 omitted the independent LocalStore/SyncEngine boundary proposition (`ARCH_02`) and scored 7/8. Product behavior and evaluator were unchanged. This CLI-0.159.0 diagnostic did not reproduce the prior 3/3 final-answer pass.

The earlier ~126,748-token result had only aggregate usage. The new F1 range spans it and shows analogous totals are sums of **three to five 19k–37k requests**, not one enormous request. The earlier run's exact request breakdown cannot be recovered. Provider-body unavailability leaves the precise within-request host-prefix, schema, and serialization shares **UNEXPLAINED**. The noisy condition means should not be subtracted as if they were deterministic components.

The next isolated optimization test should route activation directly to one `conceptualize_context` call without an `ALL_TOOLS` catalog search while holding the frozen task, tool response, and rubric fixed. It should measure whether the ~10.6k catalog output and occasional extra ~29k-input discovery requests disappear. No optimization was implemented.

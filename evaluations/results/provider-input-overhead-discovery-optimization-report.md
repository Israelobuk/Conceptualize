# Conceptualize capability discovery optimization

Commit `e437f491d6f884a317ca42c1fb4a402d9a818f13`; CLI `codex-cli 0.159.0` in both phases; frozen fixture `de91afc78218b084a6e569ba1e611d952490861dea9864fe720f55bb18c42370`.

Only the Codex `developer_instructions` host override differed. The frozen @Conceptualize user prompt, model, reasoning, working directory, environment, permissions, and one-tool fixture MCP server matched. The direct instruction names `mcp__conceptualize__conceptualize_context` and prohibits catalog search.

| Phase | Run | Requests | Separate catalog requests | Catalog input | Total input | Cached | Uncached | Output | Context local | Final pass | Elapsed ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Before | 1 | 3 | 1 | 19,601 | 80,859 | 60,032 | 20,827 | 509 | 3,307 | True | 46,882 |
| Before | 2 | 5 | 3 | 78,545 | 141,891 | 119,552 | 22,339 | 612 | 3,249 | False | 45,376 |
| Before | 3 | 3 | 1 | 19,601 | 81,848 | 60,416 | 21,432 | 461 | 3,376 | False | 38,943 |
| After | 1 | 2 | 0 | 0 | 46,962 | 31,360 | 15,602 | 505 | 3,435 | False | 34,460 |
| After | 2 | 2 | 0 | 0 | 43,221 | 31,360 | 11,861 | 484 | 3,435 | True | 34,820 |
| After | 3 | 2 | 0 | 0 | 47,089 | 31,360 | 15,729 | 467 | 3,435 | True | 32,117 |

| Pair | Input saved | Reduction | Requests removed | Catalog input removed | Latency saved |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 33,897 | 41.92% | 1 | 19,601 | 12,422 ms |
| 2 | 98,670 | 69.54% | 3 | 78,545 | 10,556 ms |
| 3 | 34,759 | 42.47% | 1 | 19,601 | 6,826 ms |
| Mean | 55,775 | 51.31% | 1.67 | 39,249 | 9,935 ms |

All six runs had one Conceptualize call, no task retry, and 8/8 retrieval and Working Context coverage. Final answers passed 1/3 before and 2/3 after. The after runs used exactly two provider requests each: tool call, then final answer. Two after-run code snippets performed an inline `ALL_TOOLS.find` in the same request that called Conceptualize; neither created a separate provider turn or printed the catalog. Host-internal MCP startup/tool listing remained.

The original 0.159.0 diagnostic (81,872, 141,153, 85,718 input) showed the same discovery pattern. This report's savings use only the new matched 0.159.0 before/after runs. PowerShell's `codex` command displayed 0.157.1, but the Python subprocess executable used for every measured run reported 0.159.0.

The default MCP surface remains one tool and exposes no resources or prompts. The expensive discovery was model-emitted `exec` over `ALL_TOOLS`, not a Conceptualize MCP resource or prompt enumeration. The likely trigger was that `@Conceptualize` alone did not bind to a specific callable in this Codex host. The trace cannot reveal the model's internal reason for sometimes inspecting the catalog twice more.

The opt-in Codex setup snippet adds a short developer instruction for direct routing. It is a host adapter; no retrieval, Working Context, benchmark, or generic MCP behavior changed. Merge the instruction with any existing developer instructions when installing the snippet, since Codex config has one top-level `developer_instructions` value.

Remaining after-run input was 43,221–47,089 tokens across two requests. The ~3.4k-token Working Context is a minority of this total; host prefix and tool-result serialization remain, but exact provider bodies were unavailable for byte-level attribution. Do not optimize these in this phase.

## Before request timelines

### Run 1

- Request 1: 19,601 input (11,904 cached), 86 output; catalog inspection. Action: `const xs = ALL_TOOLS.filter(x => /Conceptualize|project history|search.*(conversation|project)|memory/i.test(x.name+" "+x.description)); text(xs);`
- Request 2: 28,787 input (19,456 cached), 76 output; Conceptualize call. Action: `const r=await tools.mcp__conceptualize__conceptualize_context({task:"Continue attachment-storage work. Summarize current architecture and decisions, constraints, superseded earlier choice, implemented versus unfinished, and next step."}); for(const c`
- Request 3: 32,471 input (28,672 cached), 347 output; final. Action: `final answer`

### Run 2

- Request 1: 19,601 input (11,904 cached), 74 output; catalog inspection. Action: `const x = ALL_TOOLS.filter(x => /search|project|conversation|history/i.test(x.name+" "+x.description)); text(x);`
- Request 2: 29,266 input (19,456 cached), 52 output; catalog inspection. Action: `text(ALL_TOOLS.map(x=>x.name).filter(n=>/search|conceptualize|project/i.test(n)));`
- Request 3: 29,678 input (29,056 cached), 35 output; catalog inspection. Action: `text(ALL_TOOLS.find(x=>x.name==="mcp__conceptualize__conceptualize_context").description);`
- Request 4: 29,863 input (29,440 cached), 74 output; Conceptualize call. Action: `const r=await tools.mcp__conceptualize__conceptualize_context({task:"Continue attachment-storage work. Summarize current architecture and decisions, constraints, superseded choice, implemented vs unfinished, and next step."}); for(const c of r.conten`
- Request 5: 33,483 input (29,696 cached), 377 output; final. Action: `final answer`

### Run 3

- Request 1: 19,601 input (11,904 cached), 84 output; catalog inspection. Action: `const xs = ALL_TOOLS.filter(x => /search|conceptualize/i.test(x.name+" "+x.description)); text(xs);`
- Request 2: 29,242 input (19,456 cached), 79 output; Conceptualize call. Action: `const r=await tools.mcp__conceptualize__conceptualize_context({task:"Continue attachment-storage work from project history. Describe current architecture and decisions, constraints still applying, superseded earlier choice, implemented versus unfinis`
- Request 3: 33,005 input (29,056 cached), 298 output; final. Action: `final answer`

## After request timelines

### Run 1

- Request 1: 19,658 input (11,904 cached), 169 output; Conceptualize call. Action: `const t = ALL_TOOLS.find(x => x.name === "mcp__conceptualize__conceptualize_context"); const r = await tools.mcp__conceptualize__conceptualize_context({task:"Continue the attachment-storage work from the project history. Describe the current architec`
- Request 2: 27,304 input (19,456 cached), 336 output; final. Action: `final answer`

### Run 2

- Request 1: 19,658 input (11,904 cached), 156 output; Conceptualize call. Action: `const t = ALL_TOOLS.find(x => x.name === "mcp__conceptualize__conceptualize_context"); const r = await tools.mcp__conceptualize__conceptualize_context({task:"Continue the attachment-storage work from the project history. Describe the current architec`
- Request 2: 23,563 input (19,456 cached), 328 output; final. Action: `final answer`

### Run 3

- Request 1: 19,658 input (11,904 cached), 129 output; Conceptualize call. Action: `const r = await tools.mcp__conceptualize__conceptualize_context({task:"Continue the attachment-storage work from the project history. Describe the current architecture and decisions, the constraints that still apply, which earlier choice is no longer`
- Request 2: 27,431 input (19,456 cached), 338 output; final. Action: `final answer`

# V0.4 evaluation runbook

Use the repository Python environment and the same external Codex executable/model for every paired trial. Conceptualize itself never calls a model. Start the local API first and set DATABASE_URL to the exact database used by that API; set REDIS_URL to its configured cache. Fixture registration writes directly to that database. Do not use an unrelated default database.

First capture the real surface and run explicit reachability. The environment-file argument is a private JSON file containing CONCEPTUALIZE_API_URL and CONCEPTUALIZE_API_KEY. Do not publish that file.

```powershell
.venv/Scripts/python.exe -m conceptualize_evaluation.surface --output evaluations/results/new-surface.json --environment-file <private-environment.json>
.venv/Scripts/python.exe -m conceptualize_evaluation.reachability --output evaluations/runs/new-reachability --codex <codex.exe> --model <same-model> --api-url <local-api>
```

After reachability passes, run cohorts serially. Each destination must be new. Existing attempts are never overwritten. Six cross-file tasks use a separate immutable fixture with independent checks; all checks reject its unchanged baseline and pass separate reference implementations. The original receipt prompt and fixture remain unchanged. Orders alternate by task/repetition.

```powershell
.venv/Scripts/python.exe -m conceptualize_evaluation.adoption --kind adoption --output evaluations/runs/v04-adoption-isolated --codex <codex.exe> --model <same-model> --api-url <local-api>
.venv/Scripts/python.exe -m conceptualize_evaluation.adoption --kind receipts --repetitions 3 --output evaluations/runs/v04-receipts-repeated --codex <codex.exe> --model <same-model> --api-url <local-api>
.venv/Scripts/python.exe -m conceptualize_evaluation.adoption --kind negative --output evaluations/runs/v04-negative-controls --codex <codex.exe> --model <same-model> --api-url <local-api>
.venv/Scripts/python.exe -m conceptualize_evaluation.adoption_report --output evaluations/v04
```

The report reads the named V0.4 cohorts and verifies paired baseline commit, prompt hash, model and CLI version. For new versioned cohorts, update the report input names deliberately; preserve historical folders. Raw events, arrival timelines, registration, stderr, independent checks, traces and results remain in each run folder, which Git ignores. Public reports retain actual measured outcomes and unknowns. Never treat an incomplete report as complete.

The unused-connection baseline is separate:

```powershell
.venv/Scripts/python.exe -m conceptualize_evaluation.baseline --repetitions 4 --output evaluations/runs/new-unused-baseline --codex <codex.exe> --model <same-model> --api-url <local-api>
```

Report command-derived read counts as lower bounds. Tool invocation does not prove utility, passing tests do not prove causal relationship use, JSON byte reductions do not establish model token savings, and these small cohorts cannot isolate provider/caching/scheduling effects.

# Connected but unused baseline

Eight real gpt-6-sol trials used the identical arithmetic prompt and repository baseline. Four matched repetitions alternated control/connected order. All answers were correct and no trial invoked MCP.

Control mean elapsed: 6.766 seconds.
Connected mean elapsed: 11.148 seconds.

These observations show higher elapsed time in this small connected cohort. They do not isolate MCP transport cost from host prompt preparation, provider scheduling, caching or model behavior. Separate host startup and initialization timing are unavailable and remain null. Input/cached/output usage and first-message arrival timestamps are stored per trial. Arrival timestamps are CLI observations, not provider execution timestamps.

This environment baseline is separate from adoption and coding benchmarks. Explicit reachability is tested separately. A broken-server condition was not run. Raw events, stderr, registration and timelines are preserved under evaluations/runs/v04-unused-connection; machine-readable measurements are in evaluations/results/v04-unused-connection.json.

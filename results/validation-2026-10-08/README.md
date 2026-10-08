# Validation report — 8 October 2026

The automated suites passed, and the available real-model correctness checks
completed. Two benchmark-driver issues were fixed. The three-worker matrix
retained two HTTP failures following an unexpected worker termination; both
conditions passed in separate fresh-runtime reruns. This report does not claim
that every assessment experiment has been completed.

## Checks and evidence

| Check | Result | Evidence |
|---|---|---|
| Full Go suite, 46 test functions | Passed | [Go log](go-tests.log), [inventory](go-test-inventory.log) |
| Race detector over all internal packages | Passed | [Race log](go-race.log) |
| Go vet and build | Passed | Commands recorded in this session; [build log](go-vet-build.log) |
| Python benchmark suite | 15 tests passed | [Final benchmark log](python-bench-final.log) |
| Python worker suite | 12 tests passed | [Worker log](python-worker-configured.log) |
| Python and shell syntax, whitespace | 61 Python files, shell scripts and diff check passed | Commands recorded in this session |
| IEEE PDF and manifest | Passed; six pages, no unresolved citations or overfull boxes | [Build log](publication.log), [PDF](../../docs/publication/main.pdf) |
| Qwen shard outputs/logits | All six layouts in cached/stateless modes passed; max logit difference about 0.000028; five protocol guards passed | [Log](qwen-inprocess.log), [structured record](qwen3-shard-validation.json) |
| Real gRPC cached/stateless serving | Exact reference matches | [End-to-end log](qwen-e2e.log) |
| Relayout, worker loss, worker restart | 18 cases / 27 outputs passed at positions 1/4/12 and Q=1/2; maximum internal token gap about 10 seconds | [Recovery records](recovery/checks.jsonl) |
| Four serving arms; contexts 32/128; Q=1/2/4/8; 16 output tokens | 32/32 runs, 160 requests, zero failures | [Baseline report](baseline-functional/REPORT.md) |
| Three-worker capacity/bottleneck, three replicas and three-thread unsplit; context 256; Q=1/2/4/8; 32 outputs | 16/16 runs, 80 requests, two HTTP failures | [Three-worker report](three-worker-functional-serial/REPORT.md) |
| Fresh-runtime three-replica Q=8/4 rerun | 12 requests, zero failures; all workers alive | [Rerun status](replicas-isolated-retest/status.json), [log](replicas-isolated-retest.log) |
| Remote controller schedule generation | 480 unique scheduled evaluation trials validated; inference not run | [Dry-run schedule](remote-schedule.json) |

All new performance matrices use one repetition. They are functional coverage,
not adequate uncertainty estimates or a completed ten-block publication study.
The two-CPU and three-CPU campaigns are separate resource budgets. Runs retained
from 7 October were not resumed or pooled with these checks. Inference campaigns
ran sequentially. Source snapshot hashes and the PDF manifest were verified.

## Issues found and changes

1. `bench/local_publication.py` accepted local checkpoint directories but sent
   their paths to Hugging Face repository-ID validation while recording model
   provenance. The revision resolver now handles local snapshots, leaves an
   arbitrary local directory's revision unknown, and retains cached Hub-ID
   lookup. Three regression tests cover these cases. See
   [the fix](../../bench/local_publication.py) and
   [tests](../../bench/test_model_revision.py).
2. The initial three-worker campaign stopped during concurrent checkpoint
   loading. The logs did not identify a Python exception in the exited worker.
   The driver now waits for each worker to load before launching the next,
   reducing simultaneous full-checkpoint loading, and reports named process
   exits. Two tests cover serialized startup, skipped empty stages and exit
   diagnostics. See [the driver](../../bench/multistage_publication.py) and
   [tests](../../bench/test_multistage_startup.py). The original startup failure
   remains in [its log](three-worker-functional-before-fix.log) and partial data.
3. In the completed retry matrix, replica worker 0 exited with code -15
   (SIGTERM) during Q=8. One request failed there and one in the later Q=4
   condition that reused the affected runtime. The signal's origin was not
   established. A separate rerun used fresh workers for each condition and
   read saved reference outputs without allocating a reference model in its
   driver; both conditions passed. This changes the driver's memory footprint,
   so it does not prove the initial failures cannot recur. Failed requests,
   process records and successful reruns remain separate.

Initial Python test attempts used environments lacking gRPC. Those dependency
failures are retained; final tests use `.publication-tools/venv/bin/python`,
which contains the configured CPU research dependencies. They do not indicate
worker-code failures.

## Still untested

- Remote physical machines, heterogeneous transport, adaptive-controller
  outcomes, corrected-telemetry ablations and held-out transition calibration:
  only an example configuration is available; actual SSH host details are needed.
- Ten-repetition baseline and policy comparisons and additional model coverage.
- Optimized external engine: its checkout and conversion dependencies are absent.
- GPU execution: no GPU device is present. Live eBPF loading and Kubernetes
  deployment were not exercised; Go compilation does not validate these paths.
- GPT-2 execution: only Qwen model weights are cached in this environment.
- Client streamed-token delivery: the HTTP endpoint returns final JSON;
  internal token timestamps do not establish streaming delivery.
- Fault-aware replica/retry availability comparisons and coordinator-loss recovery.

See [summary.json](summary.json) for machine-readable counts and
[the assessment checklist](../../docs/publication/ASSESSMENT_RESPONSE.md) for
remaining publication requirements.

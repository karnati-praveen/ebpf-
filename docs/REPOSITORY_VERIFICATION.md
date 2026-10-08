# Shardwise repository verification — 8 October 2026

This repository can be copied independently: imports use the local `kubeedgeinfer`
Go module, generated Go/Python protobuf sources and the BPF object are committed,
and the IEEE paper contains its figures and bibliography. The project name is
Shardwise; existing module, namespace and deployment identifiers remain compatible.
No reference to the original GitHub repository is needed to compile the runtime.
Installer provenance intentionally retains the original release URL.

## Important code reviewed and checked

- Partition planner and policy gate: exact finite-concurrency placement,
  endpoint costs, worker-loss bypass, held-out calibration identity checks,
  telemetry history and scenario acceptance. Go tests include brute-force
  cross-checks, stale inputs and calibrated policy behavior.
- Controller: workload/replay forecasting, initial/evaluation holds,
  assignment retries, transition observation, recovery and reassertion.
- Router/worker: per-request histories, generation/replay handling,
  queue/compute measurement and migration accounting. Python tests cover
  request completion, overlapping transitions, failed transitions and timeout.
- Benchmark drivers: pinned revisions, resumable evidence, serialized checkpoint
  loading, CPU reservations, physical-host identity and provenance.
- Demo and publication: authentic CPU execution screenshots, explicitly
  illustrative CPU 8 / GPU 16 view, source-demo HTTP navigation, package
  checksum and standalone paper build.

The review added physical-machine identity checks to the remote baseline driver:
distinct URLs alone no longer establish distinct hosts. Missing/duplicate machine
identities, duplicate CPU reservations, insufficient unsplit CPU budget and
runtime/model mismatches are rejected. Four regression tests cover these cases.
The source demo now exposes the same labeled illustration as the Debian package.

## Verification

The final checkout passed 46 Go test functions, `go vet ./...`, `go build ./...`,
the race detector over internal packages, 12 Python worker tests and 19 Python
benchmark tests. Python and Bash syntax checks and whitespace checks passed.
The source-demo root page and `/illustration` HTTP route passed a smoke check.
The 8-page IEEE PDF compiled with no unresolved citations or overfull boxes;
the source-only package also rebuilt independently. Both delivery ZIPs passed
CRC and per-file SHA-256 verification. Candidate text files were screened for
private keys and common credential patterns; application state, environments,
weights, caches and transient locks are excluded from Git.

The initial Python attempt used an environment without gRPC. The final suite
uses a configured environment and passes; this was an environment issue.
For earlier real-model checks, exact reference matches, 18 recovery cases and
retained failed benchmark requests, see
[the detailed evidence report](../results/validation-2026-10-08/README.md).
That report records the paper page count at its earlier build; the delivered
paper now contains eight pages with the new demo figures.

To repeat the fast checks from a fresh checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -r worker/requirements.txt
VERIFY_PYTHON="$PWD/.venv/bin/python" ./scripts/verify-repository.sh
```

Go 1.26.1 or compatible toolchain is required. Full Qwen research inference
also needs the dependency/model setup documented in PUBLICATION_REVISION.md.
The separately versioned Debian demo manages its own pinned dependencies.
Fast tests do not require downloading model weights.

## Limits

GPU execution, live eBPF attachment, Kubernetes deployment and physical remote
controller campaigns were not verified here. The calibrated policy is experimental;
unit tests and the local serving smoke data do not demonstrate its empirical
performance. Ten-block comparisons, optimized external-engine baselines and
client streaming delivery remain incomplete. The Debian payload was launched
and exercised; system-wide package-manager installation was not tested.

## Separate private repository

The requested destination is `karnati-praveen/shardwise`, private, with an
independent copy of this branch and its history. The original `ebpf-` repository
remains public. The available GitHub integration denied repository creation
(`Resource not accessible by integration`). Once an empty private repository
exists and this workspace has access, copy the verified branch without force:

```bash
git remote add shardwise-private https://github.com/karnati-praveen/shardwise.git
git push shardwise-private main:main
```

An offline Git bundle is also supplied in `dist/shardwise-repository.bundle`;
it contains the verified branch history and is kept outside the tracked tree.
To restore it, run `git clone /path/to/shardwise-repository.bundle shardwise`,
then set the origin to the private repository and push `main`. The companion
`shardwise-repository-manifest.json` records the commit and bundle checksum.
Repository access is controlled by GitHub visibility, not by the bundle.

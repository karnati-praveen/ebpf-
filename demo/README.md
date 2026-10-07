# Shardwise demos

`app.py` is the earlier desktop **simulation** demo; the dashboard identifies
its simulation inputs explicitly. `real_app.py` runs **real Qwen2.5-0.5B-Instruct
CPU inference**, with the current repository's worker and controller. Its UI is
`app.html`. Source integration provenance is in `real-app-provenance.json`.

From the repository root, build the current Go binaries and use the CPU Python
environment described in `docs/PUBLICATION_REVISION.md`:

```bash
go build -o bin/controller ./cmd/controller
go build -o bin/nodeagent ./cmd/nodeagent
SHARDWISE_BIN="$PWD/bin" .venv/bin/python demo/real_app.py solo --device cpu --no-browser
```

Open the printed local dashboard URL. The app downloads the pinned checkpoint,
measures a local component profile, and starts one or two workers according to
available memory. Ask a question, inspect the layer map, stop one worker to
observe automatic controller recovery, and restore it. Its serving-activity
panel reports live workload and completed replay records. Application residual
is labeled separately from physical network RTT. Exit app cleans up its own
processes.

Invite/Join can connect another laptop running the same updated app. These
screens establish execution/control behavior, not comparative efficiency. For
resource-matched Qwen3 measurements on two real laptops, follow
`docs/TWO_LAPTOP_TESTS.md` and use the separate small test kit.

The real demo sources came from the project's 0.1.0+ci3 release. The renamed
entry point executes the revised repository runtime; this is not a certification
of the unmodified release installer or its separately pinned dependencies.

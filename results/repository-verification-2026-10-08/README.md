# Clean-checkout verification — 8 October 2026

Verified commit: `f28c33b` (runtime, paper and demo changes).

The detached clean checkout passed Go test/build/vet, the race detector on internal
packages, 12 worker tests, 19 benchmark tests and syntax checks for 130 Python
files and 16 shell scripts. See clean-checkout.log and go-test-inventory.log.
The paper source ZIP rebuilt independently and both ZIPs passed per-file SHA-256
and CRC checks; see paper-package.log. Subsequent commits add verification
records only. This check does not execute GPU, live eBPF, Kubernetes or physical
remote-host inference. Earlier real-model checks remain in the separate
validation-2026-10-08 evidence directory.

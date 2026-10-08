# Author review checkpoint — 8 October 2026

The paper is prepared in IEEE conference format with anonymous author metadata
for the user's later audit. It contains the historical two-VM study, fresh local
functional checks, real packaged-demo screenshots, and a separately labeled
illustrative CPU/GPU view. No paper has been submitted.

Completed evidence includes 65 historical runs, 18 fresh position-controlled
recovery cases, the 32-condition two-CPU matrix (160 requests; zero failures),
and the 16-condition three-CPU matrix (80 requests; two HTTP failures retained).
Fresh isolated replica reruns returned 12 outputs without failure. The original
SIGTERM's origin is unconfirmed. All local matrices have one repetition per
condition; they do not replace the interrupted ten-block campaigns (129/320
and 37/320 on different CPUs).

The packaged demo was launched from its extracted .deb payload through the
packaged launcher, using the pinned package-managed CPU environment. Fresh
browser captures verify real answers, worker stop/recovery and restored split.
System-wide package-manager installation was not tested. The hostname label
and read-only illustration are presentation changes; serving binaries and
worker/router inference code remain unchanged from the original release.
The CPU/GPU illustration assigns 8 and 16 layers but contains no measured GPU
execution or metrics. Both workers in the real captures execute on one CPU host.

Before a full-paper submission, the author still needs to audit names and
metadata, choose the conference/track, review its current requirements and
provide appropriate review artifact access. Repeated central comparisons,
optimized-engine serving, physical heterogeneity, actual transport/telemetry
ablations and held-out controller calibration remain scientific gaps. Existing
results do not demonstrate a payback-gate advantage over hysteresis.

For validation details, see source/results/validation-2026-10-08/README.md in the
combined archive or results/validation-2026-10-08/README.md in the repository.
Fresh capture provenance is in demo-screenshots/capture-manifest.json.

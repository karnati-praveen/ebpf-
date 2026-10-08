# Fresh application screenshots

These screenshots come from actual browser interaction with the Debian-packaged
application. The local hostname label is replaced with **CPU host** for anonymity.
Worker identifiers w1 and w2 remain distinct; both worker processes execute on
one CPU host. No second physical machine or GPU is represented by these captures.

The sequence includes a real Qwen2.5-0.5B-Instruct answer, worker w2 stopped,
all 24 layers recovered on w1, another real answer, and a restored split.
See `execution-records.json` and `capture-manifest.json` for provenance.
The demo model/runtime differ from the Qwen3 research evaluation.

Images 01, 02 and 04 appear in the paper. Other original captures are supplied
for inspection. No screenshot metrics are used as comparative benchmark evidence.

Image 07 is a read-only CPU/GPU design illustration: 8 CPU layers and 16 GPU
layers. Its banner and paper caption explicitly say that GPU execution and
measurements are absent. It is not part of the real-inference evidence.

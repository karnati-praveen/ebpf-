Shardwise — all images (created 2026-10-06)

Shardwise-paper.pdf      The Elsevier manuscript (for reference).

paper-figures/           Every figure used in the paper, in three formats:
  pdf/  vector, use these in LaTeX / Overleaf
  png/  for slides and Word
  svg/  vector, editable (Inkscape, Illustrator, Figma)
  architecture                 Fig. 1  Shardwise runtime architecture
  objective-frontier           Fig. 2  Latency vs throughput placement, every run
  service-envelope             Fig. 3  Ideal capacity envelope vs measured throughput
  adaptation-comparison        Fig. 4  Adaptation gains: fault phase vs whole run
  fault-traces                 Fig. 5  Compute, network and worker-loss traces
  demand-timeline              Fig. 6  Remaining-work budget and move decisions
  transition-forecast          Fig. 7  Measured transition times vs forecast
  queue-decomposition          Fig. 8  Queueing inside application link timings
  cost-and-gate-sensitivity    Fig. 9  Cost-term ablation and payback horizons
  routing-sensitivity          Fig. 10 Pipeline vs replica baselines
  objective-results            (extra) objective matrix summary, not in the paper

demo-screenshots/        The REAL Shardwise app (no mock), Qwen2.5-0.5B on a
                         4-core CPU, two local workers. All numbers are measured.
  01 dashboard ready, model split 16/8 layers across two workers
  02 real chat answers (7.8 tok/s, first token 618 ms)
  03 worker w2 stopped, pipeline recovering
  04 recovered: w1 holds all 24 layers, recovery measured 4.8 s
  05 w2 restored, model split again
  06 "Connect more laptops" invite card (address + 8-digit code)
  06b full dashboard in host (invite) mode
  07 dark mode
  08 phone-width view

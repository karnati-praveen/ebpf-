"""Numerical falsification check for the derived payback and finite-budget conditions."""
import json
import random
from pathlib import Path
rng = random.Random(20261004)
count = 0
for _ in range(10000):
    jc = rng.uniform(.001, 1)
    jn = jc * rng.uniform(.001, .999)
    margin = rng.uniform(0, .5)
    transition = rng.uniform(.01, 60)
    horizon = rng.uniform(.01, 600)
    remaining = rng.randint(1, 2048)
    delta = jc - (1 + margin) * jn
    direct = max(0, horizon - transition) / jn > (1 + margin) * horizon / jc
    boundary = delta > 0 and horizon > transition * jc / delta
    assert direct == boundary
    capped = min(horizon, remaining * jc)
    direct_cap = max(0, capped - transition) / jn > (1 + margin) * capped / jc
    finite = delta > 0 and horizon > transition * jc / delta and remaining > transition / delta
    assert direct_cap == finite
    count += 2
result = {"seed": 20261004, "random_inputs": 10000, "inequality_checks": count,
          "mismatches": 0, "scope": "numerical verification of derived equations; not a live controller or performance trial"}
(Path(__file__).resolve().parents[1] / "analysis/gate-verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))

"""Build everything from scratch: synthetic network -> models -> calibration -> 6-month replay -> caches.

    python -m scripts.build            # ~4-5 minutes on a laptop
"""
from __future__ import annotations

import json
import time

from sila import forecast, ledger, replay, synth
from sila.config import ARTIFACTS, HORIZON, TRAIN_END


def main() -> None:
    t0 = time.time()
    if not (ARTIFACTS / "smes.json").exists():
        synth.save(synth.generate())
        print(f"synthetic network generated ({time.time() - t0:.0f}s)")
    world = synth.load()
    led = ledger.Ledger.build(world)
    F = forecast.Forecaster(led)
    if not (ARTIFACTS / "models.pkl").exists():
        info = F.train()
        te = ledger.day_index(TRAIN_END)
        F.calibrate(te - HORIZON - 7 * 10, te - HORIZON + 1)   # calibration window ends before the training cut-off
        F.save()
        print(f"models trained {info} ({time.time() - t0:.0f}s)")
    else:
        F.load()
    if not (ARTIFACTS / "replay_metrics.json").exists():
        r = replay.run(F)
        m = replay.score(led, r["state"], r["log"], r["t0"], r["t1"])
        replay.save(r, m)
        print(json.dumps(m, indent=1, default=float))
    print(f"build finished in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

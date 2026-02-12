import numpy as np
import pandas as pd
from aeis_core import AEISCore, AEISConfig   

N_RUNS = 800
TIME_STEPS = 400

results = []

for run_id in range(N_RUNS):
    np.random.seed(run_id)

    scenario_type = np.random.choice(
        ["normal", "mq2_spike", "mq2_slow_drift", "mq2_stuck_high", "temp_spike", "inconsistent"],
        p=[0.35, 0.20, 0.18, 0.12, 0.08, 0.07]
    )

    mq2_adc = np.full(TIME_STEPS, 580.0, dtype=float)
    temp_c = np.full(TIME_STEPS, 24.5, dtype=float)
    dist_cm = np.full(TIME_STEPS, 120.0, dtype=float)
    tilt_deg = np.full(TIME_STEPS, 2.5, dtype=float)
    vib = np.full(TIME_STEPS, 0.08, dtype=float)

    if scenario_type == "normal":
        mq2_adc += np.random.normal(0, 65, TIME_STEPS)
        temp_c += np.random.normal(0, 1.2, TIME_STEPS)

    elif scenario_type == "mq2_spike":
        t = np.random.randint(80, 240)
        dur = np.random.randint(6, 14)
        height = np.random.uniform(1800, 3200)
        mq2_adc[t:t+dur] += height

    elif scenario_type == "mq2_slow_drift":
        drift = np.linspace(0, 2400, TIME_STEPS)
        mq2_adc += drift + np.random.normal(0, 55, TIME_STEPS)

    elif scenario_type == "mq2_stuck_high":
        t = np.random.randint(90, 220)
        mq2_adc[t:] = 3850.0

    elif scenario_type == "temp_spike":
        t = np.random.randint(100, 250)
        temp_c[t:t+8] += np.random.uniform(18, 35)

    elif scenario_type == "inconsistent":
        t = np.random.randint(70, 210)
        mq2_adc[t:t+15] += 2200
        temp_c[t:t+15] -= 8.0
        dist_cm[t:t+15] = 180.0

    aeis = AEISCore(AEISConfig())
    states = []
    confs = []
    eff_risks = []

    for step in range(TIME_STEPS):
        sensor_data = {
            "t": step,
            "temp_c": float(temp_c[step]),
            "mq2_adc": float(mq2_adc[step]),
            "dist_cm": float(dist_cm[step]),
            "tilt_deg": float(tilt_deg[step]),
            "vib": float(vib[step]),
        }
        result = aeis.step(sensor_data)
        states.append(result["aeis_state"])
        confs.append(result["confidence"])
        eff_risks.append(result["effective_risk"])

    is_real_hazard = scenario_type in ["mq2_slow_drift", "mq2_stuck_high"]


    aeis_detected = sum(1 for s in states[-20:] if s in ["CAUTION", "CRITICAL"]) >= 20

    false_pos = 1 if not is_real_hazard and aeis_detected else 0
    false_neg = 1 if is_real_hazard and not aeis_detected else 0

    results.append({
        "run_id": run_id,
        "scenario": scenario_type,
        "false_positive": false_pos,
        "false_negative": false_neg,
        "avg_confidence": np.mean(confs) if confs else 0.0,
        "min_confidence": np.min(confs) if confs else 0.0,
        "max_effective_risk": np.max(eff_risks) if eff_risks else 0.0,
        "detected_hazard": aeis_detected,
        "real_hazard": is_real_hazard,
    })

df = pd.DataFrame(results)
df.to_csv("aeis_validation_results.csv", index=False)

print(f"RESULTS ({len(df)} runs)")
print(f"False Positive Rate     : {df.false_positive.mean():6.1%}")
print(f"False Negative Rate     : {df.false_negative.mean():6.1%}")
print(f"Hazard derected       : {df.detected_hazard.sum()} of {df.real_hazard.sum()} of real")
print(f"Average confidence    : {df.avg_confidence.mean():.3f}")
print(f"Average minimum confidence : {df.min_confidence.mean():.3f}")

import random
from typing import Dict, List, Tuple

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def pressure_to_altitude_m(p_hpa: float) -> float:
    p0 = 1013.25
    return 44330.0 * (1.0 - (p_hpa / p0) ** (1.0 / 5.255))

def _base_stream(steps: int, seed: int) -> List[Dict[str, float]]:
    random.seed(seed)
    temp_c = 23.0
    hum_pct = 45.0
    press_hpa = 1008.0

    mq2_adc = 350.0
    dist_cm = 150.0
    tilt_deg = 2.0
    vib = 0.05

    out = []
    for t in range(steps):
        
        temp_c += random.uniform(-0.05, 0.05)
        hum_pct += random.uniform(-0.2, 0.2)
        press_hpa += random.uniform(-0.05, 0.05)

        mq2_adc += random.uniform(-8, 8)
        dist_cm += random.uniform(-2.5, 2.5)
        tilt_deg += random.uniform(-0.2, 0.2)
        vib += random.uniform(-0.01, 0.01)

       
        temp_c = clamp(temp_c, -10, 80)
        hum_pct = clamp(hum_pct, 0, 100)
        press_hpa = clamp(press_hpa, 900, 1100)

        mq2_adc = clamp(mq2_adc, 0, 4095)
        dist_cm = clamp(dist_cm, 2, 400)
        tilt_deg = clamp(tilt_deg, 0, 45)
        vib = clamp(vib, 0.0, 2.0)

        altitude_m = pressure_to_altitude_m(press_hpa)

        out.append({
            "t": t,
            "temp_c": temp_c,
            "hum_pct": hum_pct,
            "press_hpa": press_hpa,
            "alt_m": altitude_m,
            "mq2_adc": mq2_adc,
            "dist_cm": dist_cm,
            "tilt_deg": tilt_deg,
            "vib": vib,
        })
    return out

def scenario_false_alarm_stress(steps: int = 300, seed: int = 1) -> Tuple[str, List[Dict[str, float]], List[int]]:
    """
    Many false spikes; no real hazard.
    Ground truth hazard = 0 always.
    """
    data = _base_stream(steps, seed)
    hazard_truth = [0] * steps

    for p in data:
        t = p["t"]
        
        if 60 <= t <= 180 and random.random() < 0.22:
            p["mq2_adc"] = clamp(p["mq2_adc"] + random.uniform(700, 1400), 0, 4095)
        
        if 90 <= t <= 140 and random.random() < 0.10:
            p["temp_c"] = clamp(p["temp_c"] + random.uniform(6, 14), -10, 80)
        
        if 120 <= t <= 170 and random.random() < 0.12:
            p["tilt_deg"] = clamp(p["tilt_deg"] + random.uniform(2.0, 6.0), 0, 45)
            p["vib"] = clamp(p["vib"] + random.uniform(0.05, 0.15), 0.0, 2.0)

    return ("false_alarm_stress", data, hazard_truth)

def scenario_real_hazard_escalation(steps: int = 300, seed: int = 42) -> Tuple[str, List[Dict[str, float]], List[int]]:
    """
    Real hazard rises (gas + temp), plus obstacle approach & vibration episode.
    Ground truth hazard = 1 during hazard window.
    """
    data = _base_stream(steps, seed)
    hazard_truth = [1 if (190 <= t <= 240) else 0 for t in range(steps)]

    for p in data:
        t = p["t"]

        
        if 80 <= t <= 130 and random.random() < 0.18:
            p["mq2_adc"] = clamp(p["mq2_adc"] + random.uniform(600, 1200), 0, 4095)

        
        if 140 <= t <= 170:
            p["dist_cm"] = clamp(p["dist_cm"] - 3.5, 2, 400)

       
        if 190 <= t <= 240:
            p["mq2_adc"] = clamp(p["mq2_adc"] + random.uniform(25, 45), 0, 4095)
            p["temp_c"] = clamp(p["temp_c"] + random.uniform(0.12, 0.25), -10, 80)
            p["hum_pct"] = clamp(p["hum_pct"] - random.uniform(0.1, 0.25), 0, 100)

        
        if 210 <= t <= 230:
            p["tilt_deg"] = clamp(p["tilt_deg"] + random.uniform(0.5, 1.2), 0, 45)
            p["vib"] = clamp(p["vib"] + random.uniform(0.05, 0.12), 0.0, 2.0)

    return ("real_hazard_escalation", data, hazard_truth)

def scenario_sensor_dropout(steps: int = 300, seed: int = 7) -> Tuple[str, List[Dict[str, float]], List[int]]:
    """
    Sensor dropout: MQ2 gets stuck or drops to 0 for a period.
    Also includes a real hazard later, so AEIS must not rely on one sensor only.
    """
    data = _base_stream(steps, seed)
    hazard_truth = [1 if (200 <= t <= 245) else 0 for t in range(steps)]

    for p in data:
        t = p["t"]

        
        if 120 <= t <= 170:
            p["mq2_adc"] = 0.0  

       
        if 200 <= t <= 245:
            p["mq2_adc"] = clamp(p["mq2_adc"] + random.uniform(35, 55), 0, 4095)
            p["temp_c"] = clamp(p["temp_c"] + random.uniform(0.15, 0.28), -10, 80)
            p["tilt_deg"] = clamp(p["tilt_deg"] + random.uniform(0.2, 0.6), 0, 45)
            p["vib"] = clamp(p["vib"] + random.uniform(0.03, 0.08), 0.0, 2.0)

    return ("sensor_dropout", data, hazard_truth)

def all_scenarios(steps: int = 300):
    return [
        scenario_false_alarm_stress(steps=steps, seed=1),
        scenario_real_hazard_escalation(steps=steps, seed=42),
        scenario_sensor_dropout(steps=steps, seed=7),
    ]

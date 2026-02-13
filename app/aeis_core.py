from dataclasses import dataclass
from typing import Dict, Any, List
import numpy as np


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class AEISConfig:
    caution_risk: float = 0.42          
    critical_risk: float = 0.68        
    base_confidence: float = 1.0
    min_confidence: float = 0.05
    spike_penalty: float = 0.14        
    inconsistency_penalty: float = 0.20
    recovery_rate: float = 0.025       
    temp_min: float = 0.0
    temp_max: float = 60.0
    mq2_min: float = 200.0
    mq2_max: float = 2500.0
    dist_min: float = 5.0
    dist_max: float = 250.0
    tilt_warn: float = 12.0
    tilt_crit: float = 20.0
    vib_warn: float = 0.35
    vib_crit: float = 0.65
    trend_window: int = 12
    forecast_horizon: int = 20
    base_gas_warn: float = 0.50
    base_gas_crit: float = 0.72
    base_temp_warn: float = 0.50
    base_temp_crit: float = 0.72
    base_dist_warn: float = 0.65
    base_dist_crit: float = 0.82


class AEISCore:
    def __init__(self, cfg: AEISConfig):
        self.cfg = cfg
        self.conf = cfg.base_confidence
        self.prev: Dict[str, float] = {}
        self.risk_history: List[float] = []

    def norm_temp(self, temp_c: float) -> float:
        return clamp01((temp_c - self.cfg.temp_min) / (self.cfg.temp_max - self.cfg.temp_min))

    def norm_mq2(self, mq2_adc: float) -> float:
        return clamp01((mq2_adc - self.cfg.mq2_min) / (self.cfg.mq2_max - self.cfg.mq2_min))

    def norm_dist_risk(self, dist_cm: float) -> float:
        dist_norm = clamp01((dist_cm - self.cfg.dist_min) / (self.cfg.dist_max - self.cfg.dist_min))
        return clamp01(1.0 - dist_norm)

    def norm_tilt(self, tilt_deg: float) -> float:
        if tilt_deg <= self.cfg.tilt_warn: return 0.0
        if tilt_deg >= self.cfg.tilt_crit: return 1.0
        return clamp01((tilt_deg - self.cfg.tilt_warn) / (self.cfg.tilt_crit - self.cfg.tilt_warn))

    def norm_vib(self, vib: float) -> float:
        if vib <= self.cfg.vib_warn: return 0.0
        if vib >= self.cfg.vib_crit: return 1.0
        return clamp01((vib - self.cfg.vib_warn) / (self.cfg.vib_crit - self.cfg.vib_warn))

    def _detect_spike(self, key: str, value: float, delta: float) -> bool:
        if key not in self.prev: return False
        return abs(value - self.prev[key]) >= delta

    def _inconsistency(self, gas_r: float, temp_r: float, dist_r: float) -> bool:
        hi = sum(1 for v in (gas_r, temp_r, dist_r) if v > 0.65)
        lo = sum(1 for v in (gas_r, temp_r, dist_r) if v < 0.25)
        return hi == 1 and lo >= 2

    def fuse_risk(self, factors: Dict[str, float]) -> float:
        return clamp01(
            0.45 * factors["gas_r"] +
            0.23 * factors["temp_r"] +
            0.13 * factors["dist_r"] +
            0.11 * factors["tilt_r"] +
            0.08 * factors["vib_r"]
        )

    def forecast_risk(self) -> float:
        if len(self.risk_history) < max(5, self.cfg.trend_window):
            return self.risk_history[-1] if self.risk_history else 0.0
        w = self.cfg.trend_window
        y = np.array(self.risk_history[-w:], dtype=float)
        x = np.arange(w, dtype=float)
        x_mean = x.mean()
        y_mean = y.mean()
        denom = ((x - x_mean) ** 2).sum()
        if denom == 0: return self.risk_history[-1] if self.risk_history else 0.0
        slope = ((x - x_mean) * (y - y_mean)).sum() / denom
        forecast = y[-1] + slope * self.cfg.forecast_horizon
        return clamp01(float(forecast))

    def baseline_state(self, factors: Dict[str, float]) -> str:
        gas_r = factors["gas_r"]
        temp_r = factors["temp_r"]
        dist_r = factors["dist_r"]
        if gas_r >= self.cfg.base_gas_crit or temp_r >= self.cfg.base_temp_crit or dist_r >= self.cfg.base_dist_crit:
            return "CRITICAL"
        if gas_r >= self.cfg.base_gas_warn or temp_r >= self.cfg.base_temp_warn or dist_r >= self.cfg.base_dist_warn:
            return "CAUTION"
        return "NORMAL"

    def step(self, s: Dict[str, float]) -> Dict[str, Any]:
        t = int(s.get("t", -1))
        temp_c = float(s["temp_c"])
        mq2_adc = float(s["mq2_adc"])
        dist_cm = float(s["dist_cm"])
        tilt_deg = float(s["tilt_deg"])
        vib = float(s["vib"])

        factors = {
            "temp_r": self.norm_temp(temp_c),
            "gas_r": self.norm_mq2(mq2_adc),
            "dist_r": self.norm_dist_risk(dist_cm),
            "tilt_r": self.norm_tilt(tilt_deg),
            "vib_r": self.norm_vib(vib),
        }

        base_state = self.baseline_state(factors)
        events: List[str] = []
        penalty = 0.0

        if self._detect_spike("mq2_adc", mq2_adc, 350):
            penalty += self.cfg.spike_penalty
            events.append("SPIKE_MQ2")
        if self._detect_spike("temp_c", temp_c, 5.0):
            penalty += self.cfg.spike_penalty
            events.append("SPIKE_TEMP")
        if self._detect_spike("dist_cm", dist_cm, 35.0):
            penalty += self.cfg.spike_penalty
            events.append("SPIKE_DIST")

        if self._inconsistency(factors["gas_r"], factors["temp_r"], factors["dist_r"]):
            penalty += self.cfg.inconsistency_penalty
            events.append("INCONSISTENT_SENSORS")

        conf_before = self.conf
        if penalty > 0:
            self.conf = max(self.cfg.min_confidence, self.conf - penalty)
        else:
            self.conf = min(1.0, self.conf + self.cfg.recovery_rate)

        if self.conf < conf_before:
            events.append(f"CONF_DOWN:{conf_before:.2f}->{self.conf:.2f}")
        elif self.conf > conf_before and (t % 20 == 0):
            events.append(f"CONF_RECOVER:{conf_before:.2f}->{self.conf:.2f}")

        raw_risk = self.fuse_risk(factors)
        current_risk = clamp01(raw_risk + (1.0 - self.conf) * 0.22)  
        self.risk_history.append(current_risk)

        forecast_r = self.forecast_risk()
        effective_risk = max(current_risk, forecast_r)

        if effective_risk >= self.cfg.critical_risk:
            aeis_state = "CRITICAL"
            action = "STOP + ALERT"
        elif effective_risk >= self.cfg.caution_risk:
            aeis_state = "CAUTION"
            action = "SLOW + VERIFY"
        else:
            aeis_state = "NORMAL"
            action = "GO"

        if forecast_r > current_risk + 0.08:
            events.append("FORECAST_ESCALATION")

        self.prev["mq2_adc"] = mq2_adc
        self.prev["temp_c"] = temp_c
        self.prev["dist_cm"] = dist_cm

        return {
            "t": t,
            "factors": factors,
            "baseline_state": base_state,
            "confidence": self.conf,
            "raw_risk": raw_risk,
            "current_risk": current_risk,
            "forecast_risk": forecast_r,
            "effective_risk": effective_risk,
            "aeis_state": aeis_state,
            "action": action,
            "events": events,
        }
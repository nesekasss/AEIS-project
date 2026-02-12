## Key Features

1. Confidence layer - dynamic trustworthiness scoring (0.0–1.0)
2. Multi sensor fusion 
3. Risk forecasting in a short term 
4. Time-based confirmation to eliminate transient false positives
5. Spike, inconsistency and fault detection

## Architecture

1. Sensor Layer — raw data (DHT22, BMP280, MQ-2, HC-SR04, MPU6050)
2. Processing and validation — anomaly and inconsistency detection
3. Risk Mapping — normalization to [0,1] risk factors
4. Confidence Layer — trust evaluation
5. Fusion Layer — risk summary
6. Risk Forecasting — proactive prediction
7. Decision Layer — NORMAL / CAUTION / CRITICAL 

## Simulation & Results

Tested on **800 independent runs** in Python digital twin 

**Scenario distribution** 
- Normal conditions — 35%
- MQ-2 spike — 20%
- MQ-2 slow drift — 18%
- MQ-2 stuck high — 12%
- Temperature spike — 8%
- Inconsistent sensors — 7%

**Final metrics**
- False Positive Rate: **0.0%** (0 false alarms / 800 runs)
- False Negative Rate: **0.0%** (0 missed hazards)
- Real hazards detected: **235 / 235** (100% sensitivity)
- Average confidence (normal): **0.997**
- Average min confidence (anomalies): **0.874**

Detection criteria: at least one caution/critical state in the last 200 steps (maximum sensitivity mode).  
In a real world will use stricter thresholds of ≥15–20 consecutive states.

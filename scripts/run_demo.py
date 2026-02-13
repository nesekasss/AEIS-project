import os
import csv
import matplotlib.pyplot as plt

from aeis_core import AEISCore, AEISConfig
from scenarios import all_scenarios


def state_to_num(s: str) -> int:
    return {"NORMAL": 0, "CAUTION": 1, "CRITICAL": 2}.get(s, 0)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_plot(fig, out_path: str) -> None:
    fig.savefig(out_path, dpi=220, bbox_inches="tight")


def plot_one(title: str, x, y, ylabel: str):
    fig = plt.figure()
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel("time step")
    plt.ylabel(ylabel)
    plt.tight_layout()
    return fig


def compute_metrics(hazard_truth, states_num):
    false_alarms = sum(1 for i in range(len(states_num)) if states_num[i] >= 1 and hazard_truth[i] == 0)
    missed_hazards = sum(1 for i in range(len(states_num)) if hazard_truth[i] == 1 and states_num[i] == 0)

    start = next((i for i, h in enumerate(hazard_truth) if h == 1), None)
    if start is None:
        rt = ""
    else:
        rt_val = next((j - start for j in range(start, len(states_num)) if states_num[j] >= 1), None)
        rt = rt_val if rt_val is not None else ""

    return {"false_alarms": false_alarms, "missed_hazards": missed_hazards, "reaction_time_steps": rt}


def export_csv_metrics(out_path: str, base_metrics: dict, aeis_metrics: dict):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "baseline", "aeis"])
        for k in ["false_alarms", "missed_hazards", "reaction_time_steps"]:
            w.writerow([k, base_metrics.get(k, ""), aeis_metrics.get(k, "")])


def export_csv_events(out_path: str, events_log):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "events", "baseline_state", "aeis_state"])
        for e in events_log:
            w.writerow([e["t"], "|".join(e["events"]), e["baseline_state"], e["aeis_state"]])


def run_single_scenario(name, data, hazard_truth, base_out_dir="results"):
    cfg = AEISConfig()
    aeis = AEISCore(cfg)

    out_dir = os.path.join(base_out_dir, name)
    fig_dir = os.path.join(out_dir, "figures")
    ensure_dir(fig_dir)

    t = [p["t"] for p in data]

    
    temp_c = [p["temp_c"] for p in data]
    hum_pct = [p["hum_pct"] for p in data]
    press_hpa = [p["press_hpa"] for p in data]
    alt_m = [p["alt_m"] for p in data]
    mq2_adc = [p["mq2_adc"] for p in data]
    dist_cm = [p["dist_cm"] for p in data]
    tilt_deg = [p["tilt_deg"] for p in data]
    vib = [p["vib"] for p in data]

   
    conf, raw_r, cur_r, fcast_r, eff_r = [], [], [], [], []
    base_state_num, aeis_state_num = [], []
    gas_r, temp_r, dist_r, tilt_r, vib_r = [], [], [], [], []
    events_log = []

    for p in data:
        out = aeis.step(p)

        conf.append(out["confidence"])
        raw_r.append(out["raw_risk"])
        cur_r.append(out["current_risk"])
        fcast_r.append(out["forecast_risk"])
        eff_r.append(out["effective_risk"])

        base_state_num.append(state_to_num(out["baseline_state"]))
        aeis_state_num.append(state_to_num(out["aeis_state"]))

        if out["events"]:
            events_log.append({
                "t": out["t"],
                "events": out["events"],
                "baseline_state": out["baseline_state"],
                "aeis_state": out["aeis_state"],
            })

        f = out["factors"]
        gas_r.append(f["gas_r"])
        temp_r.append(f["temp_r"])
        dist_r.append(f["dist_r"])
        tilt_r.append(f["tilt_r"])
        vib_r.append(f["vib_r"])

    figs = []
    
    figs.append(("sensor_dht22_temp.png", plot_one(f"[{name}] DHT22 Temperature (°C)", t, temp_c, "°C")))
    figs.append(("sensor_dht22_humidity.png", plot_one(f"[{name}] DHT22 Humidity (%)", t, hum_pct, "%")))
    figs.append(("sensor_bmp280_pressure.png", plot_one(f"[{name}] BMP280 Pressure (hPa)", t, press_hpa, "hPa")))
    figs.append(("sensor_bmp280_altitude.png", plot_one(f"[{name}] BMP280 Altitude (m)", t, alt_m, "m")))
    figs.append(("sensor_mq2_gas.png", plot_one(f"[{name}] MQ2 Gas Level", t, mq2_adc, "ADC units")))
    figs.append(("sensor_hcsr04_distance.png", plot_one(f"[{name}] HC-SR04 Distance (cm)", t, dist_cm, "cm")))
    figs.append(("sensor_mpu6050_tilt.png", plot_one(f"[{name}] MPU6050 Tilt (deg)", t, tilt_deg, "deg")))
    figs.append(("sensor_mpu6050_vibration.png", plot_one(f"[{name}] MPU6050 Vibration", t, vib, "a.u.")))

    
    figs.append(("factor_gas_risk.png", plot_one(f"[{name}] Risk factor: Gas", t, gas_r, "risk")))
    figs.append(("factor_temp_risk.png", plot_one(f"[{name}] Risk factor: Temperature", t, temp_r, "risk")))
    figs.append(("factor_distance_risk.png", plot_one(f"[{name}] Risk factor: Distance", t, dist_r, "risk")))
    figs.append(("factor_tilt_risk.png", plot_one(f"[{name}] Risk factor: Tilt", t, tilt_r, "risk")))
    figs.append(("factor_vibration_risk.png", plot_one(f"[{name}] Risk factor: Vibration", t, vib_r, "risk")))

    
    fig = plt.figure()
    plt.plot(t, conf, label="confidence")
    plt.plot(t, cur_r, label="current risk")
    plt.plot(t, fcast_r, label="forecast risk")
    plt.plot(t, eff_r, label="effective risk")
    plt.title(f"[{name}] AEIS: Confidence and Risk")
    plt.xlabel("time step")
    plt.ylabel("0..1")
    plt.legend()
    plt.tight_layout()
    figs.append(("aeis_confidence_risk.png", fig))

  
    fig = plt.figure()
    plt.plot(t, base_state_num, label="Baseline")
    plt.plot(t, aeis_state_num, label="AEIS")
    hazard_line = [2 if h == 1 else 0 for h in hazard_truth]
    plt.plot(t, hazard_line, label="Hazard truth (scaled)")
    plt.yticks([0, 1, 2], ["NORMAL", "CAUTION", "CRITICAL"])
    plt.title(f"[{name}] States: Baseline vs AEIS")
    plt.xlabel("time step")
    plt.ylabel("state")
    plt.legend()
    plt.tight_layout()
    figs.append(("states_baseline_vs_aeis.png", fig))

    
    for fn, fig in figs:
        save_plot(fig, os.path.join(fig_dir, fn))

    
    base_metrics = compute_metrics(hazard_truth, base_state_num)
    aeis_metrics = compute_metrics(hazard_truth, aeis_state_num)

    export_csv_metrics(os.path.join(out_dir, "metrics.csv"), base_metrics, aeis_metrics)
    export_csv_events(os.path.join(out_dir, "events.csv"), events_log)

    
    plt.close("all")

    return {
        "scenario": name,
        **{f"baseline_{k}": v for k, v in base_metrics.items()},
        **{f"aeis_{k}": v for k, v in aeis_metrics.items()},
        "outputs_dir": out_dir
    }


def write_summary(summary_rows, out_path="results/summary_metrics.csv"):
    ensure_dir("results")
    keys = [
        "scenario",
        "baseline_false_alarms", "baseline_missed_hazards", "baseline_reaction_time_steps",
        "aeis_false_alarms", "aeis_missed_hazards", "aeis_reaction_time_steps",
        "outputs_dir"
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in summary_rows:
            w.writerow({k: r.get(k, "") for k in keys})


def main():
    scenarios = all_scenarios(steps=300)
    summary = []

    for (name, data, hazard_truth) in scenarios:
        row = run_single_scenario(name, data, hazard_truth)
        summary.append(row)
        print(f"[DONE] {name} -> {row['outputs_dir']}")

    write_summary(summary)
    print("\n=== ALL SCENARIOS COMPLETED ===")
    print("Saved to: results/<scenario>/ (figures + metrics.csv + events.csv)")
    print("Summary: results/summary_metrics.csv")
    print("\nTip: Use the 'states_baseline_vs_aeis.png' and 'aeis_confidence_risk.png' figures in your documentation.")


if __name__ == "__main__":
    main()




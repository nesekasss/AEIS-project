from __future__ import annotations

import argparse
import time
from typing import Any

from app.transport_serial import SerialConfig, SerialJsonlTransport


def decide_action(msg: dict[str, Any]) -> dict[str, Any] | None:
    """
    Decision policy for demo:
    - If confidence < 0.60 OR env == "HAZARD" -> fan ON
    - If env == "NORMAL" AND confidence > 0.80 -> fan OFF
    """
    if msg.get("type") != "telemetry":
        return None

    env = str(msg.get("env", ""))
    conf = float(msg.get("confidence", 1.0))

    if env == "HAZARD" or conf < 0.60:
        return {"type": "cmd", "cmd": "fan_set", "value": 1}
    if env == "NORMAL" and conf > 0.80:
        return {"type": "cmd", "cmd": "fan_set", "value": 0}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. /dev/cu.usbserial-XXXX")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--json_only", type=int, default=1, help="1 = force ESP32 JSON-only mode")
    args = ap.parse_args()

    tr = SerialJsonlTransport(SerialConfig(port=args.port, baud=args.baud))
    try:
        time.sleep(2)  

     
        if args.json_only == 1:
            tr.write_message({"type": "cmd", "cmd": "json_only", "value": 1})
            print("-> sent cmd json_only=1")

        print("Listening... Ctrl+C to stop")
        last_cmd = None

        while True:
            msg = tr.read_message()
            if not msg:
                continue

    
            if msg.get("type") == "telemetry":
                print(
                    f"<- ts={msg.get('ts_ms')} env={msg.get('env')} sys={msg.get('sys')} "
                    f"conf={msg.get('confidence')} mq2={msg.get('mq2')} dist={msg.get('dist_cm')} acc={msg.get('acc')} fan={msg.get('fan')}"
                )
            else:
                print("<-", msg)

            cmd = decide_action(msg)
            if cmd:
               
                if cmd != last_cmd:
                    tr.write_message(cmd)
                    print("->", cmd)
                    last_cmd = cmd

            time.sleep(0.01)

    finally:
        tr.close()


if __name__ == "__main__":
    main()

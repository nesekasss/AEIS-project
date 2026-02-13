from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import serial


class SerialProtocolError(RuntimeError):
    pass


@dataclass
class SerialConfig:
    port: str
    baud: int = 115200
    read_timeout_s: float = 0.2
    write_timeout_s: float = 1.0


def encode_jsonl(obj: dict[str, Any]) -> bytes:
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    return line.encode("utf-8")


def decode_jsonl_line(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        raise SerialProtocolError("Empty line")
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise SerialProtocolError("JSON message must be an object")
    return obj


class SerialJsonlTransport:
    def __init__(self, cfg: SerialConfig) -> None:
        self.cfg = cfg
        self.ser = serial.Serial(
            port=cfg.port,
            baudrate=cfg.baud,
            timeout=cfg.read_timeout_s,
            write_timeout=cfg.write_timeout_s,
        )

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            self.ser.close()

    def write_message(self, obj: dict[str, Any]) -> None:
        self.ser.write(encode_jsonl(obj))
        self.ser.flush()

    def read_message(self) -> Optional[dict[str, Any]]:
        raw = self.ser.readline()
        if not raw:
            return None
        return decode_jsonl_line(raw)

    def wait_for(self, predicate, timeout_s: float = 3.0) -> dict[str, Any]:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            msg = self.read_message()
            if msg and predicate(msg):
                return msg
        raise TimeoutError("Timeout waiting for message")

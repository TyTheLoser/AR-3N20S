from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass
class AppConfig:
	sensor_ip: str = "10.10.10.2"
	sensor_port: int = 502
	address: int = 0
	axis_device_ids: List[int] = None  # type: ignore[assignment]
	timeout_s: float = 1.0
	force_range_n: float = 20.0
	counts_full_scale: float = 32768.0
	poll_interval_ms: int = 50
	language: str = "zh"  # "zh" or "en"

	def __post_init__(self) -> None:
		if self.axis_device_ids is None:
			self.axis_device_ids = [1, 2, 3]

	def n_per_count(self) -> float:
		return float(self.force_range_n) / float(self.counts_full_scale)

	def to_public_dict(self) -> Dict[str, Any]:
		# Only expose what the UI edits.
		poll_hz = 1000.0 / float(self.poll_interval_ms) if self.poll_interval_ms > 0 else 0.0
		return {
			"sensor_ip": self.sensor_ip,
			"sensor_port": self.sensor_port,
			"axis_device_ids": self.axis_device_ids,
			"force_range_n": self.force_range_n,
			"poll_hz": poll_hz,
			"language": self.language,
		}

	def to_file_dict(self) -> Dict[str, Any]:
		# Keep internal fields too.
		poll_hz = 1000.0 / float(self.poll_interval_ms) if self.poll_interval_ms > 0 else 0.0
		return {
			"sensor_ip": self.sensor_ip,
			"sensor_port": self.sensor_port,
			"address": self.address,
			"axis_device_ids": self.axis_device_ids,
			"timeout_s": self.timeout_s,
			"force_range_n": self.force_range_n,
			"counts_full_scale": self.counts_full_scale,
			"poll_interval_ms": self.poll_interval_ms,
			"poll_hz": poll_hz,
			"language": self.language,
			"n_per_count": self.n_per_count(),
		}


def _coerce_int_list(value: Any, *, default: Optional[List[int]] = None) -> List[int]:
	if value is None:
		return default or [1, 2, 3]
	if isinstance(value, list):
		return [int(x) for x in value]
	if isinstance(value, str):
		parts = [p.strip() for p in value.split(",") if p.strip()]
		return [int(p) for p in parts]
	raise ValueError("axis_device_ids must be a list or comma-separated string")


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
	cfg = AppConfig()
	if not path.exists():
		return cfg
	data = json.loads(path.read_text(encoding="utf-8"))
	if not isinstance(data, dict):
		return cfg

	cfg.sensor_ip = str(data.get("sensor_ip", cfg.sensor_ip))
	cfg.sensor_port = int(data.get("sensor_port", cfg.sensor_port))
	cfg.address = int(data.get("address", cfg.address))
	cfg.axis_device_ids = _coerce_int_list(data.get("axis_device_ids"), default=cfg.axis_device_ids)
	cfg.timeout_s = float(data.get("timeout_s", cfg.timeout_s))
	cfg.force_range_n = float(data.get("force_range_n", data.get("range_n", cfg.force_range_n)))
	cfg.counts_full_scale = float(data.get("counts_full_scale", cfg.counts_full_scale))
	if "poll_hz" in data and data.get("poll_hz"):
		try:
			hz = float(data.get("poll_hz"))
			if hz > 0:
				cfg.poll_interval_ms = int(round(1000.0 / hz))
		except Exception:
			cfg.poll_interval_ms = int(data.get("poll_interval_ms", cfg.poll_interval_ms))
	else:
		cfg.poll_interval_ms = int(data.get("poll_interval_ms", cfg.poll_interval_ms))
	cfg.language = str(data.get("language", cfg.language)) or "zh"
	if cfg.language not in ("zh", "en"):
		cfg.language = "zh"
	return cfg


def save_config(cfg: AppConfig, path: Path = CONFIG_PATH) -> None:
	path.write_text(json.dumps(cfg.to_file_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_updates(cfg: AppConfig, updates: Dict[str, Any]) -> AppConfig:
	base = {k: v for k, v in cfg.to_file_dict().items() if k != "n_per_count"}
	new_cfg = AppConfig(**base)
	if "sensor_ip" in updates:
		new_cfg.sensor_ip = str(updates["sensor_ip"])
	if "sensor_port" in updates:
		new_cfg.sensor_port = int(updates["sensor_port"])
	if "axis_device_ids" in updates:
		new_cfg.axis_device_ids = _coerce_int_list(updates["axis_device_ids"], default=new_cfg.axis_device_ids)
	if "force_range_n" in updates:
		new_cfg.force_range_n = float(updates["force_range_n"])
	if "poll_hz" in updates:
		hz = float(updates["poll_hz"])
		if hz <= 0:
			raise ValueError("poll_hz must be > 0")
		new_cfg.poll_interval_ms = int(round(1000.0 / hz))
	elif "poll_interval_ms" in updates:
		new_cfg.poll_interval_ms = int(updates["poll_interval_ms"])
	if "language" in updates:
		lang = str(updates["language"])
		new_cfg.language = lang if lang in ("zh", "en") else new_cfg.language

	if new_cfg.sensor_port <= 0 or new_cfg.sensor_port > 65535:
		raise ValueError("sensor_port out of range")
	if new_cfg.force_range_n <= 0:
		raise ValueError("force_range_n must be > 0")
	if new_cfg.poll_interval_ms < 10:
		raise ValueError("poll_hz too high (poll_interval_ms must be >= 10)")
	if not new_cfg.axis_device_ids:
		raise ValueError("axis_device_ids cannot be empty")
	return new_cfg

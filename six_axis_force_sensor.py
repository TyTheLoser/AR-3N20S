from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

from pymodbus.client import ModbusTcpClient


def _u16_to_s16(value: int) -> int:
	value &= 0xFFFF
	return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True)
class Wrench:
	fx: float
	fy: float
	fz: float
	tx: float = 0.0
	ty: float = 0.0
	tz: float = 0.0

	def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
		return (self.fx, self.fy, self.fz, self.tx, self.ty, self.tz)


class SixAxisForceSensor:
	"""
	尽量对齐 ATI FTNet（Net F/T）常见用法：
	- connect/open
	- bias/unbias（软件清零）
	- get_wrench / get_force_torque

	本传感器换算约定（你提供的标定）：
	- 原始寄存器为 u16（0~65535）
	- 转换为 s16：raw>=32768 -> raw-65536
	- s16 满量程：±32768 <-> ±20N
	"""

	DEFAULT_FORCE_RANGE_N = 20.0
	DEFAULT_COUNTS_FULL_SCALE = 32768.0

	def __init__(
		self,
		ip: str,
		*,
		address: Union[int, Sequence[int]] = 0,
		axis_device_ids: Sequence[int] = (1, 2, 3),
		port: int = 502,
		timeout: Optional[float] = None,
		n_per_count: Optional[float] = None,
		force_range_n: float = DEFAULT_FORCE_RANGE_N,
		counts_full_scale: float = DEFAULT_COUNTS_FULL_SCALE,
	) -> None:
		self.ip = ip
		self.port = port
		self.timeout = timeout
		self._n_per_count = float(
			n_per_count if n_per_count is not None else (force_range_n / counts_full_scale)
		)
		if self._n_per_count <= 0:
			raise ValueError("n_per_count must be > 0")

		self.axis_device_ids = tuple(axis_device_ids)
		if isinstance(address, int):
			self.addresses = tuple(address for _ in self.axis_device_ids)
		else:
			addresses = tuple(int(a) for a in address)
			if len(addresses) != len(self.axis_device_ids):
				raise ValueError("address sequence length must match axis_device_ids length")
			self.addresses = addresses

		self._client = self._create_client()
		self._bias = Wrench(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

	@property
	def n_per_count(self) -> float:
		return self._n_per_count

	@n_per_count.setter
	def n_per_count(self, value: float) -> None:
		value = float(value)
		if value <= 0:
			raise ValueError("n_per_count must be > 0")
		self._n_per_count = value

	def _create_client(self) -> ModbusTcpClient:
		kwargs = {"host": self.ip}
		try:
			kwargs["port"] = self.port
		except Exception:
			pass
		if self.timeout is not None:
			kwargs["timeout"] = self.timeout
		try:
			return ModbusTcpClient(**kwargs)
		except TypeError:
			return ModbusTcpClient(self.ip)

	def connect(self) -> bool:
		return bool(self._client.connect())

	def open(self) -> bool:
		return self.connect()

	def close(self) -> None:
		try:
			self._client.close()
		except Exception:
			pass

	def disconnect(self) -> None:
		self.close()

	def __enter__(self) -> "SixAxisForceSensor":
		self.connect()
		return self

	def __exit__(self, exc_type, exc, tb) -> None:
		self.close()

	@property
	def bias_vector(self) -> Wrench:
		return self._bias

	def _read_u16(self, *, device_id: int, address: int) -> int:
		# 兼容不同 pymodbus 版本的参数名（unit/slave/device_id）以及位置参数形式。
		last_exc: Optional[Exception] = None
		call_variants = [
			lambda: self._client.read_holding_registers(address, 1, unit=device_id),
			lambda: self._client.read_holding_registers(address, 1, slave=device_id),
			lambda: self._client.read_holding_registers(address=address, count=1, unit=device_id),
			lambda: self._client.read_holding_registers(address=address, count=1, slave=device_id),
			lambda: self._client.read_holding_registers(device_id=device_id, address=address),
		]

		for call in call_variants:
			try:
				resp = call()
				if resp is None or not hasattr(resp, "registers") or not resp.registers:
					continue
				return int(resp.registers[0]) & 0xFFFF
			except TypeError as exc:
				last_exc = exc
				continue

		raise RuntimeError(f"read_holding_registers failed for device_id={device_id}") from last_exc

	def read_raw_u16(self) -> Tuple[int, ...]:
		values = []
		for device_id, address in zip(self.axis_device_ids, self.addresses):
			values.append(self._read_u16(device_id=device_id, address=address))
		return tuple(values)

	def read_counts(self) -> Tuple[int, ...]:
		return tuple(_u16_to_s16(v) for v in self.read_raw_u16())

	def get_wrench(self, *, unbiased: bool = False) -> Wrench:
		"""
		返回力/力矩（当前实现默认只有 Fx/Fy/Fz；力矩为 0）。
		- unbiased=True：不减 bias（等价于原始换算后的 N）
		"""
		counts = self.read_counts()
		fx = (counts[0] if len(counts) > 0 else 0) * self._n_per_count
		fy = (counts[1] if len(counts) > 1 else 0) * self._n_per_count
		fz = (counts[2] if len(counts) > 2 else 0) * self._n_per_count
		wrench = Wrench(fx, fy, fz, 0.0, 0.0, 0.0)
		if unbiased:
			return wrench
		return Wrench(
			wrench.fx - self._bias.fx,
			wrench.fy - self._bias.fy,
			wrench.fz - self._bias.fz,
			wrench.tx - self._bias.tx,
			wrench.ty - self._bias.ty,
			wrench.tz - self._bias.tz,
		)

	def get_force_torque(self, *, unbiased: bool = False) -> Tuple[float, float, float, float, float, float]:
		return self.get_wrench(unbiased=unbiased).as_tuple()

	def get_forces(self, *, unbiased: bool = False) -> Tuple[float, float, float]:
		w = self.get_wrench(unbiased=unbiased)
		return w.fx, w.fy, w.fz

	def bias(self, *, samples: int = 20, delay_s: float = 0.0) -> Wrench:
		"""
		软件清零（ATI 常叫 bias）：把当前平均值记录为 bias，后续 get_wrench 会减去该 bias。
		"""
		if samples <= 0:
			raise ValueError("samples must be > 0")

		sum_fx = 0.0
		sum_fy = 0.0
		sum_fz = 0.0
		for _ in range(samples):
			w = self.get_wrench(unbiased=True)
			sum_fx += w.fx
			sum_fy += w.fy
			sum_fz += w.fz
			if delay_s > 0:
				time.sleep(delay_s)

		self._bias = Wrench(sum_fx / samples, sum_fy / samples, sum_fz / samples, 0.0, 0.0, 0.0)
		return self._bias

	def unbias(self) -> None:
		self._bias = Wrench(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

	# 兼容你之前的命名
	def tare(self, *, samples: int = 20, delay_s: float = 0.0) -> Wrench:
		return self.bias(samples=samples, delay_s=delay_s)

	def clear_tare(self) -> None:
		self.unbias()


if __name__ == "__main__":
	sensor = SixAxisForceSensor("10.10.10.2", address=0, axis_device_ids=(1, 2, 3))
	sensor.connect()
	while True:
		fx, fy, fz = sensor.get_forces(unbiased=False)
		print(f"Fx={fx:.3f}N, Fy={fy:.3f}N, Fz={fz:.3f}N")
		time.sleep(0.02)

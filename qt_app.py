from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from arizon_config import AppConfig, apply_updates, load_config, save_config
from six_axis_force_sensor import SixAxisForceSensor


@dataclass
class UiText:
	monitor: str
	settings: str
	panel_monitor: str
	panel_settings: str
	title: str
	subtitle: str
	connected: str
	disconnected: str
	connecting: str
	status: str
	ip: str
	bias: str
	tare: str
	clear: str
	save: str
	test: str
	labels_sensor_ip: str
	labels_port: str
	labels_axis_ids: str
	labels_force_range: str
	labels_language: str


I18N = {
	"zh": UiText(
		monitor="监控",
		settings="设置",
		panel_monitor="数值面板",
		panel_settings="设置",
		title="六轴力传感器监控",
		subtitle="实时监控 · 轮询采样",
		connected="已连接",
		disconnected="未连接",
		connecting="连接中…",
		status="状态",
		ip="IP",
		bias="偏置",
		tare="清零",
		clear="清除",
		save="保存",
		test="",
		labels_sensor_ip="传感器 IP",
		labels_port="端口",
		labels_axis_ids="轴设备 ID",
		labels_force_range="量程 (±N)",
		labels_language="语言",
	),
	"en": UiText(
		monitor="Monitor",
		settings="Settings",
		panel_monitor="Values",
		panel_settings="Settings",
		title="Six-Axis Force Sensor Monitor",
		subtitle="Realtime · Polling",
		connected="Connected",
		disconnected="Disconnected",
		connecting="Connecting…",
		status="Status",
		ip="IP",
		bias="Bias",
		tare="Tare",
		clear="Clear",
		save="Save",
		test="",
		labels_sensor_ip="Sensor IP",
		labels_port="Port",
		labels_axis_ids="Axis IDs",
		labels_force_range="Range (±N)",
		labels_language="Language",
	),
}


class SensorController(QtCore.QObject):
	updated = QtCore.Signal(tuple, str, bool)  # ft6, message, connected
	bias_updated = QtCore.Signal(tuple)  # bias6

	def __init__(self, cfg: AppConfig) -> None:
		super().__init__()
		self.cfg = cfg
		self.sensor = self._build_sensor(cfg)
		self.connected = False
		self.last_error = ""

	def _build_sensor(self, cfg: AppConfig) -> SixAxisForceSensor:
		return SixAxisForceSensor(
			cfg.sensor_ip,
			port=cfg.sensor_port,
			address=cfg.address,
			axis_device_ids=tuple(cfg.axis_device_ids),
			timeout=cfg.timeout_s,
			n_per_count=cfg.n_per_count(),
		)

	def reconfigure(self, cfg: AppConfig) -> None:
		try:
			self.sensor.close()
		except Exception:
			pass
		self.cfg = cfg
		self.sensor = self._build_sensor(cfg)
		self.connected = False
		self.last_error = ""

	def _ensure_connected(self) -> bool:
		if self.connected:
			return True
		try:
			self.connected = bool(self.sensor.connect())
			if not self.connected:
				self.last_error = "connect() returned False"
			return self.connected
		except Exception as e:
			self.connected = False
			self.last_error = str(e)
			return False

	@QtCore.Slot()
	def poll(self) -> None:
		try:
			if not self._ensure_connected():
				raise RuntimeError(self.last_error or "not connected")
			ft = self.sensor.get_force_torque(unbiased=False)
			self.last_error = "Modbus OK"
			self.updated.emit(ft, self.last_error, True)
		except Exception as e:
			self.connected = False
			self.last_error = str(e)
			self.updated.emit((0.0, 0.0, 0.0, 0.0, 0.0, 0.0), self.last_error, False)

	def tare(self, samples: int = 30) -> None:
		try:
			if not self._ensure_connected():
				raise RuntimeError(self.last_error or "not connected")
			w = self.sensor.bias(samples=samples, delay_s=0.0).as_tuple()
			self.bias_updated.emit(w)
		except Exception as e:
			self.connected = False
			self.last_error = str(e)

	def clear(self) -> None:
		self.sensor.unbias()
		self.bias_updated.emit((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.cfg = load_config()
		self.lang = self.cfg.language if self.cfg.language in I18N else "zh"
		self.t = I18N[self.lang]

		self.setWindowTitle(self.t.title)
		self.setMinimumSize(1100, 680)

		self.controller = SensorController(self.cfg)
		self.controller.updated.connect(self.on_sensor_update)
		self.controller.bias_updated.connect(self.on_bias_update)

		self._build_ui()
		self._apply_styles()
		self._apply_text()
		self._init_plot()

		self.poll_timer = QtCore.QTimer(self)
		self.poll_timer.setInterval(self.cfg.poll_interval_ms)
		self.poll_timer.timeout.connect(self.controller.poll)
		self.poll_timer.start()

		self.controller.poll()

	def _build_ui(self) -> None:
		root = QtWidgets.QWidget()
		self.setCentralWidget(root)
		layout = QtWidgets.QHBoxLayout(root)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)

		# Sidebar
		self.sidebar = QtWidgets.QFrame()
		self.sidebar.setObjectName("sidebar")
		self.sidebar.setFixedWidth(280)
		side = QtWidgets.QVBoxLayout(self.sidebar)
		side.setContentsMargins(18, 22, 18, 22)
		side.setSpacing(14)

		brand = QtWidgets.QHBoxLayout()
		brand.setSpacing(12)
		mark = QtWidgets.QFrame()
		mark.setObjectName("brandMark")
		mark.setFixedSize(44, 44)
		brand.addWidget(mark)
		brandText = QtWidgets.QVBoxLayout()
		brandText.setSpacing(2)
		self.brandTitle = QtWidgets.QLabel("ARIZON")
		self.brandTitle.setObjectName("brandTitle")
		self.brandSub = QtWidgets.QLabel("")
		self.brandSub.setObjectName("brandSub")
		brandText.addWidget(self.brandTitle)
		brandText.addWidget(self.brandSub)
		brand.addLayout(brandText)
		brand.addStretch(1)
		side.addLayout(brand)

		self.btnMonitor = QtWidgets.QPushButton()
		self.btnMonitor.setObjectName("navBtnActive")
		self.btnSettings = QtWidgets.QPushButton()
		self.btnSettings.setObjectName("navBtn")
		self.btnMonitor.clicked.connect(lambda: self.set_view("monitor"))
		self.btnSettings.clicked.connect(lambda: self.set_view("settings"))
		side.addWidget(self.btnMonitor)
		side.addWidget(self.btnSettings)

		# Floating white card inside sidebar
		self.panel = QtWidgets.QFrame()
		self.panel.setObjectName("panelCard")
		panelLay = QtWidgets.QVBoxLayout(self.panel)
		panelLay.setContentsMargins(0, 0, 0, 0)
		panelLay.setSpacing(0)
		header = QtWidgets.QHBoxLayout()
		header.setContentsMargins(16, 14, 16, 14)
		header.setSpacing(12)
		self.panelTitle = QtWidgets.QLabel("")
		self.panelTitle.setObjectName("panelTitle")
		self.panelMeta = QtWidgets.QLabel("— Hz")
		self.panelMeta.setObjectName("panelMeta")
		header.addWidget(self.panelTitle)
		header.addStretch(1)
		header.addWidget(self.panelMeta)
		panelLay.addLayout(header)

		self.panelStack = QtWidgets.QStackedWidget()
		panelLay.addWidget(self.panelStack, 1)

		self.panelFooter = QtWidgets.QLabel("")
		self.panelFooter.setObjectName("panelFooter")
		self.panelFooter.setContentsMargins(16, 0, 16, 16)
		panelLay.addWidget(self.panelFooter)

		# Monitor page
		monitorPage = QtWidgets.QWidget()
		ml = QtWidgets.QVBoxLayout(monitorPage)
		ml.setContentsMargins(16, 16, 16, 16)
		ml.setSpacing(12)

		self.fxVal = self._make_value_row("Fx")
		self.fyVal = self._make_value_row("Fy")
		self.fzVal = self._make_value_row("Fz")
		ml.addWidget(self.fxVal["row"])
		ml.addWidget(self.fyVal["row"])
		ml.addWidget(self.fzVal["row"])

		actions = QtWidgets.QHBoxLayout()
		actions.setSpacing(10)
		self.btnTare = QtWidgets.QPushButton()
		self.btnTare.setObjectName("btnPrimary")
		self.btnClear = QtWidgets.QPushButton()
		self.btnClear.setObjectName("btnGhost")
		self.btnTare.clicked.connect(lambda: self.controller.tare(samples=30))
		self.btnClear.clicked.connect(self.controller.clear)
		actions.addWidget(self.btnTare)
		actions.addWidget(self.btnClear)
		ml.addLayout(actions)
		ml.addStretch(1)
		self.panelStack.addWidget(monitorPage)

		# Settings page
		settingsPage = QtWidgets.QWidget()
		sl = QtWidgets.QVBoxLayout(settingsPage)
		sl.setContentsMargins(16, 16, 16, 16)
		sl.setSpacing(10)

		self.inIp = QtWidgets.QLineEdit()
		self.inPort = QtWidgets.QLineEdit()
		self.inPort.setValidator(QtGui.QIntValidator(1, 65535, self))
		self.inAxis = QtWidgets.QLineEdit()
		self.inRange = QtWidgets.QLineEdit()
		self.inRange.setValidator(QtGui.QDoubleValidator(0.1, 100000.0, 3, self))
		self.inHz = QtWidgets.QLineEdit()
		self.inHz.setValidator(QtGui.QDoubleValidator(0.1, 1000.0, 2, self))

		self.langZh = QtWidgets.QPushButton("中文")
		self.langEn = QtWidgets.QPushButton("English")
		self.langZh.setObjectName("segBtn")
		self.langEn.setObjectName("segBtn")
		self.langZh.clicked.connect(lambda: self.set_language("zh"))
		self.langEn.clicked.connect(lambda: self.set_language("en"))

		self.lblIp = QtWidgets.QLabel()
		self.lblPort = QtWidgets.QLabel()
		self.lblAxis = QtWidgets.QLabel()
		self.lblRange = QtWidgets.QLabel()
		self.lblHz = QtWidgets.QLabel()
		self.lblLang = QtWidgets.QLabel()
		for lbl in (self.lblIp, self.lblPort, self.lblAxis, self.lblRange, self.lblHz, self.lblLang):
			lbl.setObjectName("fieldLabel")

		sl.addLayout(self._field(self.lblIp, self.inIp))
		sl.addLayout(self._field(self.lblPort, self.inPort))
		sl.addLayout(self._field(self.lblAxis, self.inAxis))
		sl.addLayout(self._field(self.lblRange, self.inRange))
		sl.addLayout(self._field(self.lblHz, self.inHz))

		segWrap = QtWidgets.QFrame()
		segWrap.setObjectName("segWrap")
		seg = QtWidgets.QHBoxLayout(segWrap)
		seg.setContentsMargins(6, 6, 6, 6)
		seg.setSpacing(6)
		seg.addWidget(self.langZh)
		seg.addWidget(self.langEn)
		sl.addWidget(self.lblLang)
		sl.addWidget(segWrap)

		btnRow = QtWidgets.QHBoxLayout()
		btnRow.setSpacing(10)
		self.btnSave = QtWidgets.QPushButton()
		self.btnSave.setObjectName("btnPrimary")
		self.btnSave.clicked.connect(self.on_save)
		btnRow.addWidget(self.btnSave)
		sl.addLayout(btnRow)
		sl.addStretch(1)
		self.panelStack.addWidget(settingsPage)

		side.addWidget(self.panel)
		side.addStretch(1)
		layout.addWidget(self.sidebar)

		# Main area
		main = QtWidgets.QWidget()
		mainLay = QtWidgets.QVBoxLayout(main)
		mainLay.setContentsMargins(26, 22, 26, 22)
		mainLay.setSpacing(18)

		# Top bar
		top = QtWidgets.QHBoxLayout()
		top.setSpacing(18)
		titleWrap = QtWidgets.QVBoxLayout()
		titleWrap.setSpacing(2)
		self.hTitle = QtWidgets.QLabel()
		self.hTitle.setObjectName("hTitle")
		self.hSub = QtWidgets.QLabel()
		self.hSub.setObjectName("hSub")
		titleWrap.addWidget(self.hTitle)
		titleWrap.addWidget(self.hSub)
		top.addLayout(titleWrap)
		top.addStretch(1)
		self.connChip = QtWidgets.QFrame()
		self.connChip.setObjectName("chip")
		chipLay = QtWidgets.QHBoxLayout(self.connChip)
		chipLay.setContentsMargins(12, 10, 12, 10)
		chipLay.setSpacing(10)
		self.connDot = QtWidgets.QFrame()
		self.connDot.setObjectName("dot")
		self.connDot.setFixedSize(10, 10)
		self.connText = QtWidgets.QLabel()
		self.connText.setObjectName("chipText")
		chipLay.addWidget(self.connDot)
		chipLay.addWidget(self.connText)
		top.addWidget(self.connChip, 0, QtCore.Qt.AlignmentFlag.AlignRight)
		mainLay.addLayout(top)

		# Plot card
		self.plotCard = QtWidgets.QFrame()
		self.plotCard.setObjectName("plotCard")
		pc = QtWidgets.QVBoxLayout(self.plotCard)
		pc.setContentsMargins(0, 0, 0, 0)
		pc.setSpacing(0)
		pHeader = QtWidgets.QHBoxLayout()
		pHeader.setContentsMargins(16, 14, 16, 14)
		self.plotTitle = QtWidgets.QLabel()
		self.plotTitle.setObjectName("panelTitle")
		pHeader.addWidget(self.plotTitle)
		pHeader.addStretch(1)
		pc.addLayout(pHeader)

		self.plotWidget = pg.PlotWidget()
		self.plotWidget.setBackground(None)
		self.plotWidget.setMenuEnabled(False)
		self.plotWidget.showGrid(x=True, y=True, alpha=0.2)
		self.plotWidget.setMouseEnabled(x=False, y=False)
		self.plotWidget.getPlotItem().hideButtons()
		pc.addWidget(self.plotWidget, 1)
		mainLay.addWidget(self.plotCard, 1)

		# Footer
		self.footer = QtWidgets.QFrame()
		self.footer.setObjectName("footer")
		fl = QtWidgets.QHBoxLayout(self.footer)
		fl.setContentsMargins(14, 12, 14, 12)
		fl.setSpacing(18)
		self.statusLabel = QtWidgets.QLabel()
		self.statusVal = QtWidgets.QLabel("—")
		self.ipLabel = QtWidgets.QLabel()
		self.ipVal = QtWidgets.QLabel(self.cfg.sensor_ip)
		self.statusLabel.setObjectName("muted")
		self.ipLabel.setObjectName("muted")
		self.statusVal.setObjectName("footerVal")
		self.ipVal.setObjectName("footerVal")
		fl.addWidget(self.statusLabel)
		fl.addWidget(self.statusVal)
		fl.addStretch(1)
		fl.addWidget(self.ipLabel)
		fl.addWidget(self.ipVal)
		mainLay.addWidget(self.footer)

		layout.addWidget(main, 1)

		self._load_cfg_to_form()
		self.set_view("monitor")

	def _make_value_row(self, axis: str) -> dict:
		row = QtWidgets.QFrame()
		row.setObjectName("valueRow")
		hl = QtWidgets.QHBoxLayout(row)
		hl.setContentsMargins(12, 12, 12, 12)
		hl.setSpacing(10)
		axisLbl = QtWidgets.QLabel(axis)
		axisLbl.setObjectName(f"axis_{axis.lower()}")
		val = QtWidgets.QLabel("—")
		val.setObjectName("valueBig")
		unit = QtWidgets.QLabel("N")
		unit.setObjectName("unit")
		hl.addWidget(axisLbl)
		hl.addStretch(1)
		hl.addWidget(val)
		hl.addWidget(unit)
		return {"row": row, "val": val}

	def _field(self, label: QtWidgets.QLabel, widget: QtWidgets.QWidget) -> QtWidgets.QHBoxLayout:
		box = QtWidgets.QVBoxLayout()
		box.setSpacing(6)
		box.addWidget(label)
		box.addWidget(widget)
		return box

	def _apply_styles(self) -> None:
		self.setStyleSheet(
			"""
			QMainWindow { background: #eef4f7; }
			#sidebar {
			  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2aa9b3, stop:1 #88e6c5);
			}
			#brandMark {
			  border-radius: 14px;
			  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(255,255,255,90), stop:1 rgba(255,255,255,30));
			  border: 1px solid rgba(255,255,255,90);
			}
			#brandTitle { color: rgba(255,255,255,235); font-weight: 900; letter-spacing: 2px; }
			#brandSub { color: rgba(255,255,255,180); font-size: 12px; }
			#navBtn, #navBtnActive {
			  text-align: left;
			  padding: 12px 12px;
			  border-radius: 14px;
			  border: 1px solid rgba(255,255,255,40);
			  background: rgba(255,255,255,36);
			  color: rgba(255,255,255,235);
			  font-weight: 800;
			}
			#navBtnActive { background: rgba(255,255,255,66); }
			#panelCard {
			  border-radius: 20px;
			  background: rgba(255,255,255,210);
			  border: 1px solid rgba(255,255,255,170);
			}
			#panelTitle { font-weight: 900; }
			#panelMeta { color: rgba(15,23,42,150); }
			#panelFooter { color: #64748b; font-size: 12px; }
			#valueRow {
			  border-radius: 16px;
			  background: rgba(15,23,42,8);
			  border: 1px solid rgba(15,23,42,10);
			}
			#axis_fx { color: #f59e0b; font-weight: 900; }
			#axis_fy { color: #22c55e; font-weight: 900; }
			#axis_fz { color: #8b5cf6; font-weight: 900; }
			#valueBig { font-size: 26px; font-weight: 900; color: #0f172a; }
			#unit { color: #64748b; font-weight: 800; }
			#btnPrimary {
			  padding: 12px 12px;
			  border-radius: 14px;
			  background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #1b8bb7, stop:1 #1fd0c7);
			  color: white;
			  font-weight: 900;
			  border: 0;
			}
			#btnGhost {
			  padding: 12px 12px;
			  border-radius: 14px;
			  background: rgba(255,255,255,210);
			  color: #0f172a;
			  font-weight: 900;
			  border: 1px solid rgba(15,23,42,20);
			}
			#hTitle { font-size: 18px; font-weight: 900; color: #0f172a; }
			#hSub { font-size: 12px; color: #64748b; }
			#chip {
			  border-radius: 999px;
			  background: rgba(255,255,255,160);
			  border: 1px solid rgba(15,23,42,20);
			}
			#dot { border-radius: 5px; background: #fbbf24; }
			#chipText { color: #0f172a; font-weight: 800; }
			#plotCard {
			  border-radius: 20px;
			  background: rgba(255,255,255,200);
			  border: 1px solid rgba(15,23,42,20);
			}
			#footer {
			  border-radius: 16px;
			  background: rgba(255,255,255,150);
			  border: 1px solid rgba(15,23,42,18);
			}
			#muted { color: #64748b; font-weight: 800; }
			#footerVal { color: #0f172a; font-weight: 800; }
			QLineEdit, QSpinBox, QDoubleSpinBox {
			  border-radius: 14px;
			  border: 1px solid rgba(15,23,42,20);
			  padding: 10px 10px;
			  background: rgba(255,255,255,220);
			}
			#fieldLabel { color: #64748b; font-weight: 900; font-size: 12px; }
			#segWrap {
			  border-radius: 14px;
			  background: rgba(15,23,42,8);
			  border: 1px solid rgba(15,23,42,12);
			}
			#segBtn {
			  border-radius: 10px;
			  padding: 10px 10px;
			  font-weight: 900;
			  border: 0;
			  background: transparent;
			  color: rgba(15,23,42,180);
			}
			#segBtn[active="true"] {
			  background: rgba(255,255,255,230);
			  color: rgba(15,23,42,235);
			}
			"""
		)

	def _apply_text(self) -> None:
		self.t = I18N[self.lang]
		self.setWindowTitle(self.t.title)
		self.brandSub.setText("力传感器" if self.lang == "zh" else "Force Sensor")
		self.btnMonitor.setText(self.t.monitor)
		self.btnSettings.setText(self.t.settings)
		self.hTitle.setText(self.t.title)
		self.hSub.setText(self.t.subtitle)
		self.plotTitle.setText("实时曲线区" if self.lang == "zh" else "Realtime Plot")
		self.statusLabel.setText(f"{self.t.status}:")
		self.ipLabel.setText(f"{self.t.ip}:")
		self.btnTare.setText(self.t.tare)
		self.btnClear.setText(self.t.clear)
		self.btnSave.setText(self.t.save)
		self.lblIp.setText(self.t.labels_sensor_ip)
		self.lblPort.setText(self.t.labels_port)
		self.lblAxis.setText(self.t.labels_axis_ids)
		self.lblRange.setText(self.t.labels_force_range)
		self.lblHz.setText("采样频率 (Hz)" if self.lang == "zh" else "Sample Rate (Hz)")
		self.lblLang.setText(self.t.labels_language)

	def _init_plot(self) -> None:
		self.history = 360
		self.x = list(range(self.history))
		self.y_fx: List[float] = [0.0] * self.history
		self.y_fy: List[float] = [0.0] * self.history
		self.y_fz: List[float] = [0.0] * self.history

		self.curve_fx = self.plotWidget.plot(self.x, self.y_fx, pen=pg.mkPen("#f59e0b", width=2))
		self.curve_fy = self.plotWidget.plot(self.x, self.y_fy, pen=pg.mkPen("#22c55e", width=2))
		self.curve_fz = self.plotWidget.plot(self.x, self.y_fz, pen=pg.mkPen("#8b5cf6", width=2))
		self._apply_plot_range()

	def _apply_plot_range(self) -> None:
		r = float(self.cfg.force_range_n or 20.0)
		self.plotWidget.setYRange(-r, r, padding=0.05)

	def _load_cfg_to_form(self) -> None:
		self.inIp.setText(self.cfg.sensor_ip)
		self.inPort.setText(str(self.cfg.sensor_port))
		self.inAxis.setText(",".join(str(x) for x in self.cfg.axis_device_ids))
		self.inRange.setText(f"{float(self.cfg.force_range_n):g}")
		hz = 1000.0 / float(self.cfg.poll_interval_ms) if self.cfg.poll_interval_ms > 0 else 0.0
		self.inHz.setText(f"{hz:.1f}")
		self._apply_lang_buttons()
		self.ipVal.setText(self.cfg.sensor_ip)

	def _apply_lang_buttons(self) -> None:
		self.langZh.setProperty("active", "true" if self.lang == "zh" else "false")
		self.langEn.setProperty("active", "true" if self.lang == "en" else "false")
		self.langZh.style().unpolish(self.langZh)
		self.langZh.style().polish(self.langZh)
		self.langEn.style().unpolish(self.langEn)
		self.langEn.style().polish(self.langEn)

	def set_language(self, lang: str) -> None:
		self.lang = "en" if lang == "en" else "zh"
		self._apply_text()
		self._apply_lang_buttons()
		self.cfg.language = self.lang

	def set_view(self, view: str) -> None:
		is_monitor = view == "monitor"
		self.btnMonitor.setObjectName("navBtnActive" if is_monitor else "navBtn")
		self.btnSettings.setObjectName("navBtnActive" if not is_monitor else "navBtn")
		self.btnMonitor.style().unpolish(self.btnMonitor)
		self.btnMonitor.style().polish(self.btnMonitor)
		self.btnSettings.style().unpolish(self.btnSettings)
		self.btnSettings.style().polish(self.btnSettings)
		self.panelStack.setCurrentIndex(0 if is_monitor else 1)
		self.panelTitle.setText(self.t.panel_monitor if is_monitor else self.t.panel_settings)
		self.panelMeta.setVisible(is_monitor)
		self.panelFooter.setText(f"{self.t.bias}: 0, 0, 0" if is_monitor else "—")

	def _parse_axis_ids(self, text: str) -> List[int]:
		parts = [p.strip() for p in text.split(",") if p.strip()]
		return [int(p) for p in parts]

	def on_save(self) -> None:
		port = int(self.inPort.text() or "502")
		range_n = float(self.inRange.text() or "20")
		hz = float(self.inHz.text() or "20")
		updates = {
			"sensor_ip": self.inIp.text().strip(),
			"sensor_port": port,
			"axis_device_ids": self._parse_axis_ids(self.inAxis.text()),
			"force_range_n": range_n,
			"poll_hz": hz,
			"language": self.lang,
		}
		try:
			new_cfg = apply_updates(load_config(), updates)
			save_config(new_cfg)
			self.cfg = new_cfg
			self.controller.reconfigure(new_cfg)
			self.poll_timer.setInterval(self.cfg.poll_interval_ms)
			self._apply_plot_range()
			self._load_cfg_to_form()
			self.statusVal.setText("已保存" if self.lang == "zh" else "Saved")
		except Exception as e:
			self.statusVal.setText(str(e))

	def on_sensor_update(self, ft: Tuple[float, float, float, float, float, float], msg: str, ok: bool) -> None:
		fx, fy, fz, *_ = ft
		self.fxVal["val"].setText(f"{fx:+.2f}")
		self.fyVal["val"].setText(f"{fy:+.2f}")
		self.fzVal["val"].setText(f"{fz:+.2f}")

		self.y_fx = self.y_fx[1:] + [fx]
		self.y_fy = self.y_fy[1:] + [fy]
		self.y_fz = self.y_fz[1:] + [fz]
		self.curve_fx.setData(self.x, self.y_fx)
		self.curve_fy.setData(self.x, self.y_fy)
		self.curve_fz.setData(self.x, self.y_fz)

		self.statusVal.setText(msg)
		self.ipVal.setText(self.cfg.sensor_ip)
		self.connText.setText(self.t.connected if ok else self.t.disconnected)
		self.connDot.setStyleSheet(f"background: {'#22c55e' if ok else '#ef4444'}; border-radius: 5px;")

		# Rough Hz from timer interval
		hz = 1000.0 / max(1, self.poll_timer.interval())
		self.panelMeta.setText(f"{hz:.1f} Hz")

	def on_bias_update(self, bias6: Tuple[float, float, float, float, float, float]) -> None:
		fx, fy, fz, *_ = bias6
		if self.panelStack.currentIndex() == 0:
			self.panelFooter.setText(f"{self.t.bias}: {fx:.3f}, {fy:.3f}, {fz:.3f}")


def main() -> int:
	app = QtWidgets.QApplication(sys.argv)
	pg.setConfigOptions(antialias=True)
	w = MainWindow()
	w.show()
	return app.exec()


if __name__ == "__main__":
	raise SystemExit(main())

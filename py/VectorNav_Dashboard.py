"""
VectorNav Dashboard — HSMST Consumer GUI
=========================================
Subscribes to the two UMAA SA topics published by VectorNav_Publisher.py
and renders a live instrument dashboard using PyQt6.

Topics consumed:
  • UMAA::SA::SpeedStatus::SpeedReportType
  • UMAA::SA::GlobalPoseStatus::GlobalPoseReportType

Dashboard panels:
  ┌──────────────────────┬──────────────────────┐
  │   POSITION           │   ORIENTATION        │
  │   Latitude           │   Roll               │
  │   Longitude          │   Pitch              │
  │   Altitude           │   Yaw / Heading      │
  ├──────────────────────┼──────────────────────┤
  │   NAVIGATION         │   SPEED              │
  │   Course (TN)        │   Speed Over Ground  │
  │   Nav Solution       │   Speed Thru Water   │
  │   Timestamp          │   Speed Thru Air     │
  └──────────────────────┴──────────────────────┘
  ┌──────────────────────────────────────────────┐
  │   Compass rose + attitude arc indicators     │
  └──────────────────────────────────────────────┘

Usage:
  python VectorNav_Dashboard.py [domain_id]     (default domain_id = 0)

Prerequisites:
  pip install pyqt6
  source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh
"""

from __future__ import annotations

import math
import os
import sys
import threading
from dataclasses import dataclass
from typing import Optional

import rti.connextdds as dds
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QBrush,
    QLinearGradient, QRadialGradient, QPolygonF,
)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

import vn_constants
import vn_topics
from umaa_types import (
    GlobalPoseReportType,
    GlobalPoseReportTypeTopic,
    SpeedReportType,
    SpeedReportTypeTopic,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DOMAIN_ID: int = int(sys.argv[1]) if len(sys.argv) > 1 else 0
REFRESH_MS: int = 100  # GUI refresh interval


# ---------------------------------------------------------------------------
# Shared state — written by DDS receive thread, read by GUI thread
# ---------------------------------------------------------------------------

@dataclass
class NavState:
    lat:   float = 0.0
    lon:   float = 0.0
    alt:   Optional[float] = None
    course:  float = 0.0          # radians TN
    roll:    float = 0.0          # radians
    pitch:   float = 0.0          # radians
    yaw:     float = 0.0          # radians
    sog:   Optional[float] = None
    stw:   Optional[float] = None
    sta:   Optional[float] = None
    nav_solution: str = "---"
    timestamp: str = "---"
    speed_mode: str = "---"
    data_age_ms: float = 9999.0   # ms since last pose sample

    def __post_init__(self) -> None:
        self._lock = threading.Lock()


_state = NavState()


# ---------------------------------------------------------------------------
# DDS Listeners
# ---------------------------------------------------------------------------

class _Signals(QObject):
    """Qt signals emitted from the DDS receive thread to trigger a GUI repaint."""
    updated = pyqtSignal()


_signals = _Signals()


class SpeedListener(dds.DataReaderListener):
    def on_data_available(self, reader: dds.DataReader) -> None:
        for sample in reader.take():
            if not sample.info.valid:
                continue
            d: SpeedReportType = sample.data
            with _state._lock:
                _state.sog = d.speedOverGround
                _state.stw = d.speedThroughWater
                _state.sta = d.speedThroughAir
                _state.speed_mode = d.mode.name if d.mode is not None else "---"
        _signals.updated.emit()


class PoseListener(dds.DataReaderListener):
    def on_data_available(self, reader: dds.DataReader) -> None:
        for sample in reader.take():
            if not sample.info.valid:
                continue
            d: GlobalPoseReportType = sample.data
            att = d.attitude
            ts  = d.timeStamp
            with _state._lock:
                _state.lat   = d.position.geodeticLatitude
                _state.lon   = d.position.geodeticLongitude
                _state.alt   = d.altitude
                _state.course  = d.course
                _state.roll    = att.roll.roll
                _state.pitch   = att.pitch.pitch
                _state.yaw     = att.yaw.yaw
                _state.nav_solution = d.navigationSolution.name
                _state.timestamp = f"{ts.seconds}.{ts.nanoseconds:09d}"
                _state.data_age_ms = 0.0
        _signals.updated.emit()


# ---------------------------------------------------------------------------
# Palette helpers
# ---------------------------------------------------------------------------

DARK_BG   = QColor(18, 22, 30)
PANEL_BG  = QColor(26, 32, 44)
BORDER    = QColor(55, 65, 85)
ACCENT    = QColor(56, 189, 248)     # sky blue
ACCENT2   = QColor(52, 211, 153)     # emerald
WARN      = QColor(251, 191, 36)     # amber
TEXT_PRI  = QColor(226, 232, 240)
TEXT_SEC  = QColor(100, 116, 139)
RED_IND   = QColor(248, 113, 113)
ROLL_CLR  = QColor(251, 191,  36)
PITCH_CLR = QColor(52,  211, 153)


def _fmt(val: Optional[float], fmt: str = ".3f", unit: str = "") -> str:
    if val is None:
        return "---"
    return f"{val:{fmt}}{unit}"


# ---------------------------------------------------------------------------
# Compass / Attitude widget
# ---------------------------------------------------------------------------

class CompassWidget(QWidget):
    """
    Combined compass rose (heading/course) with roll & pitch arc indicators.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._heading_deg: float = 0.0
        self._roll_deg:    float = 0.0
        self._pitch_deg:   float = 0.0

    def update_state(self, heading_deg: float, roll_deg: float, pitch_deg: float) -> None:
        self._heading_deg = heading_deg
        self._roll_deg    = roll_deg
        self._pitch_deg   = pitch_deg
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 14

        # ---- background circle ----
        bg = QRadialGradient(cx, cy, r)
        bg.setColorAt(0.0, QColor(30, 38, 54))
        bg.setColorAt(1.0, QColor(15, 20, 30))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(BORDER, 1.5))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # ---- cardinal tick marks ----
        cardinals = {0: "N", 90: "E", 180: "S", 270: "W"}
        for deg in range(0, 360, 10):
            rad = math.radians(deg - self._heading_deg)
            inner = r - (10 if deg % 30 == 0 else 5)
            outer = r - 1
            x1 = cx + inner * math.sin(rad)
            y1 = cy - inner * math.cos(rad)
            x2 = cx + outer * math.sin(rad)
            y2 = cy - outer * math.cos(rad)
            colour = ACCENT if deg % 90 == 0 else QColor(70, 85, 105)
            p.setPen(QPen(colour, 1.5 if deg % 30 == 0 else 0.8))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            if deg in cardinals:
                lbl_r = r - 22
                lx = cx + lbl_r * math.sin(rad)
                ly = cy - lbl_r * math.cos(rad)
                p.setPen(QPen(ACCENT))
                fnt = QFont("Helvetica", 9, QFont.Weight.Bold)
                p.setFont(fnt)
                fm = QFontMetrics(fnt)
                txt = cardinals[deg]
                p.drawText(
                    QPointF(lx - fm.horizontalAdvance(txt) / 2, ly + fm.ascent() / 2), txt
                )

        # ---- heading needle ----
        needle_len = r * 0.62
        tip_x = cx + needle_len * math.sin(0)          # always points up (north in frame)
        tip_y = cy - needle_len * math.cos(0)
        tail_x = cx - (r * 0.35) * math.sin(0)
        tail_y = cy + (r * 0.35) * math.cos(0)
        p.setPen(QPen(RED_IND, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(tip_x, tip_y))
        p.setPen(QPen(TEXT_SEC, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(tail_x, tail_y))

        # ---- roll arc (outer ring, ±45° shown) ----
        roll_clamp = max(-45.0, min(45.0, self._roll_deg))
        arc_rect   = QRectF(cx - r + 4, cy - r + 4, (r - 4) * 2, (r - 4) * 2)
        p.setPen(QPen(ROLL_CLR, 3))
        span = -int(roll_clamp * 16)
        p.drawArc(arc_rect, 90 * 16, span)

        # ---- pitch bar (horizontal line displaced vertically) ----
        pitch_clamp = max(-30.0, min(30.0, self._pitch_deg))
        pitch_offset = (pitch_clamp / 30.0) * (r * 0.3)
        bar_half = r * 0.35
        p.setPen(QPen(PITCH_CLR, 2.5))
        p.drawLine(
            QPointF(cx - bar_half, cy - pitch_offset),
            QPointF(cx + bar_half, cy - pitch_offset),
        )

        # ---- centre dot ----
        p.setBrush(QBrush(ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 5, 5)

        # ---- heading readout at bottom ----
        p.setPen(QPen(TEXT_PRI))
        fnt2 = QFont("Helvetica", 10, QFont.Weight.Bold)
        p.setFont(fnt2)
        hdg_txt = f"{self._heading_deg % 360:.1f}°"
        fm2 = QFontMetrics(fnt2)
        p.drawText(
            QPointF(cx - fm2.horizontalAdvance(hdg_txt) / 2, cy + r - 3), hdg_txt
        )

        p.end()


# ---------------------------------------------------------------------------
# Value display card
# ---------------------------------------------------------------------------

class ValueCard(QFrame):
    """A single labelled numeric value card."""

    def __init__(self, label: str, unit: str = "", colour: QColor = ACCENT) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"background-color: {PANEL_BG.name()};"
            f"border: 1px solid {BORDER.name()};"
            f"border-radius: 6px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(1)

        self._lbl = QLabel(label.upper())
        self._lbl.setFont(QFont("Helvetica", 8))
        self._lbl.setStyleSheet(f"color: {TEXT_SEC.name()}; border: none;")
        layout.addWidget(self._lbl)

        self._val = QLabel("---")
        self._val.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        self._val.setStyleSheet(f"color: {colour.name()}; border: none;")
        layout.addWidget(self._val)

        if unit:
            self._unit_lbl = QLabel(unit)
            self._unit_lbl.setFont(QFont("Helvetica", 8))
            self._unit_lbl.setStyleSheet(f"color: {TEXT_SEC.name()}; border: none;")
            layout.addWidget(self._unit_lbl)

    def set_value(self, text: str) -> None:
        self._val.setText(text)


# ---------------------------------------------------------------------------
# Section header
# ---------------------------------------------------------------------------

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Helvetica", 9, QFont.Weight.Bold))
    lbl.setStyleSheet(
        f"color: {TEXT_SEC.name()};"
        f"border-bottom: 1px solid {BORDER.name()};"
        f"padding-bottom: 3px;"
    )
    return lbl


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class Dashboard(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VectorNav  ·  UMAA HSMST Dashboard")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"background-color: {DARK_BG.name()}; color: {TEXT_PRI.name()};")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── title bar ─────────────────────────────────────────────────
        title = QLabel("⬡  VectorNav Navigation Dashboard")
        title.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT.name()};")
        root.addWidget(title)

        self._status = QLabel("● Waiting for data…")
        self._status.setFont(QFont("Helvetica", 9))
        self._status.setStyleSheet(f"color: {WARN.name()};")
        root.addWidget(self._status)

        # ── main grid ─────────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(8)
        root.addLayout(grid)

        # --- Position column ---
        pos_panel = QVBoxLayout()
        pos_panel.addWidget(_section_label("Position"))
        self._c_lat = ValueCard("Latitude",  "°  (N+)",  ACCENT)
        self._c_lon = ValueCard("Longitude", "°  (E+)",  ACCENT)
        self._c_alt = ValueCard("Altitude",  "m  MSL",   ACCENT2)
        for c in (self._c_lat, self._c_lon, self._c_alt):
            pos_panel.addWidget(c)
        pos_panel.addStretch()
        grid.addLayout(pos_panel, 0, 0)

        # --- Orientation column ---
        ori_panel = QVBoxLayout()
        ori_panel.addWidget(_section_label("Orientation"))
        self._c_roll  = ValueCard("Roll",  "°",  ROLL_CLR)
        self._c_pitch = ValueCard("Pitch", "°",  PITCH_CLR)
        self._c_yaw   = ValueCard("Yaw / Heading", "°  (TN)", RED_IND)
        for c in (self._c_roll, self._c_pitch, self._c_yaw):
            ori_panel.addWidget(c)
        ori_panel.addStretch()
        grid.addLayout(ori_panel, 0, 1)

        # --- Speed column ---
        spd_panel = QVBoxLayout()
        spd_panel.addWidget(_section_label("Speed"))
        self._c_sog   = ValueCard("Speed Over Ground",   "m/s", ACCENT2)
        self._c_stw   = ValueCard("Speed Thru Water",    "m/s", ACCENT2)
        self._c_sta   = ValueCard("Speed Thru Air",      "m/s", ACCENT2)
        self._c_smode = ValueCard("Speed Mode",          "",    TEXT_SEC)
        for c in (self._c_sog, self._c_stw, self._c_sta, self._c_smode):
            spd_panel.addWidget(c)
        spd_panel.addStretch()
        grid.addLayout(spd_panel, 0, 2)

        # --- Navigation / status column ---
        nav_panel = QVBoxLayout()
        nav_panel.addWidget(_section_label("Navigation"))
        self._c_course = ValueCard("Course (True North)", "°",  WARN)
        self._c_navsol = ValueCard("Nav Solution",        "",   TEXT_SEC)
        self._c_ts     = ValueCard("Timestamp",           "",   TEXT_SEC)
        for c in (self._c_course, self._c_navsol, self._c_ts):
            nav_panel.addWidget(c)
        nav_panel.addStretch()
        grid.addLayout(nav_panel, 0, 3)

        # --- Compass widget spans full width at bottom ---
        compass_row = QHBoxLayout()
        compass_row.addStretch()
        self._compass = CompassWidget()
        self._compass.setMinimumSize(280, 280)
        self._compass.setMaximumSize(380, 380)
        compass_row.addWidget(self._compass)
        compass_row.addStretch()
        root.addLayout(compass_row)

        # ── ship speed slider (knots) ─────────────────────────────────
        spd_row = QHBoxLayout()
        spd_row.setSpacing(10)

        spd_icon = QLabel("🚢 Ship Speed:")
        spd_icon.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        spd_icon.setStyleSheet(f"color: {ACCENT.name()};")
        spd_row.addWidget(spd_icon)

        slow_lbl = QLabel(f"{vn_constants.SPEED_KNOTS_MIN} kt")
        slow_lbl.setFont(QFont("Helvetica", 9))
        slow_lbl.setStyleSheet(f"color: {TEXT_SEC.name()};")
        spd_row.addWidget(slow_lbl)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setMinimum(vn_constants.SPEED_KNOTS_MIN)
        self._speed_slider.setMaximum(vn_constants.SPEED_KNOTS_MAX)
        self._speed_slider.setValue(vn_constants.SPEED_KNOTS_DEFAULT)
        self._speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._speed_slider.setTickInterval(5)
        self._speed_slider.setMinimumWidth(300)
        self._speed_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px; background: #334155; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #38bdf8; width: 18px; height: 18px;
                margin: -6px 0; border-radius: 9px;
            }
            QSlider::sub-page:horizontal {
                background: #38bdf8; border-radius: 3px;
            }
        """)
        spd_row.addWidget(self._speed_slider)

        fast_lbl = QLabel(f"{vn_constants.SPEED_KNOTS_MAX} kt")
        fast_lbl.setFont(QFont("Helvetica", 9))
        fast_lbl.setStyleSheet(f"color: {TEXT_SEC.name()};")
        spd_row.addWidget(fast_lbl)

        self._speed_val_lbl = QLabel(f"{vn_constants.SPEED_KNOTS_DEFAULT} kt")
        self._speed_val_lbl.setFont(QFont("Courier New", 14, QFont.Weight.Bold))
        self._speed_val_lbl.setStyleSheet(f"color: {WARN.name()}; min-width: 54px;")
        spd_row.addWidget(self._speed_val_lbl)

        spd_row.addStretch()
        root.addLayout(spd_row)

        self._speed_slider.valueChanged.connect(self._on_speed_changed)

        # ── orbit toggle button ───────────────────────────────────────
        orbit_row = QHBoxLayout()
        orbit_row.setSpacing(10)

        self._orbit_btn = QPushButton("🔄  Orbit: OFF")
        self._orbit_btn.setCheckable(True)
        self._orbit_btn.setChecked(False)
        self._orbit_btn.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        self._orbit_btn.setMinimumWidth(150)
        self._orbit_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {PANEL_BG.name()};"
            f"  color: {TEXT_PRI.name()};"
            f"  border: 1px solid {BORDER.name()};"
            f"  border-radius: 6px;"
            f"  padding: 5px 14px;"
            f"}}"
            f"QPushButton:checked {{"
            f"  background-color: {ACCENT2.name()};"
            f"  color: {DARK_BG.name()};"
            f"  border: 1px solid {ACCENT2.name()};"
            f"}}"
        )
        orbit_row.addWidget(self._orbit_btn)

        orbit_hint = QLabel("— press to begin clockwise orbit around home at current position")
        orbit_hint.setFont(QFont("Helvetica", 9))
        orbit_hint.setStyleSheet(f"color: {TEXT_SEC.name()};")
        orbit_row.addWidget(orbit_hint)

        orbit_row.addStretch()
        root.addLayout(orbit_row)

        self._orbit_btn.toggled.connect(self._on_orbit_toggled)

        # ── refresh timer ─────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        # Connect DDS signal
        _signals.updated.connect(self._refresh)

        # ── age tracking ──────────────────────────────────────────────
        self._age_timer = QTimer(self)
        self._age_timer.setInterval(100)
        self._age_timer.timeout.connect(self._tick_age)
        self._age_timer.start()

    # ------------------------------------------------------------------

    def _on_speed_changed(self, value: int) -> None:
        """Slider moved — publish new speed in knots to VectorNav_Publisher."""
        self._speed_val_lbl.setText(f"{value} kt")
        _publish_speed_command(float(value))

    def _on_orbit_toggled(self, checked: bool) -> None:
        """Orbit button toggled — publish orbit enable/disable command."""
        self._orbit_btn.setText("🔄  Orbit: ON" if checked else "🔄  Orbit: OFF")
        _publish_orbit_command(checked)

    def _tick_age(self) -> None:
        with _state._lock:
            _state.data_age_ms += 100.0

    def _refresh(self) -> None:
        with _state._lock:
            lat   = _state.lat
            lon   = _state.lon
            alt   = _state.alt
            course_r = _state.course
            roll_r   = _state.roll
            pitch_r  = _state.pitch
            yaw_r    = _state.yaw
            sog   = _state.sog
            stw   = _state.stw
            sta   = _state.sta
            nav   = _state.nav_solution
            ts    = _state.timestamp
            smode = _state.speed_mode
            age   = _state.data_age_ms

        roll_d  = math.degrees(roll_r)
        pitch_d = math.degrees(pitch_r)
        yaw_d   = math.degrees(yaw_r) % 360
        course_d = math.degrees(course_r) % 360

        # Status bar
        if age < 2500:
            self._status.setText("● Live  —  data flowing")
            self._status.setStyleSheet(f"color: {ACCENT2.name()};")
        else:
            self._status.setText(f"● No data  ({age/1000:.1f}s ago)")
            self._status.setStyleSheet(f"color: {WARN.name()};")

        # Position
        self._c_lat.set_value(f"{lat:+.6f}")
        self._c_lon.set_value(f"{lon:+.7f}")
        self._c_alt.set_value(_fmt(alt, ".2f"))

        # Orientation
        self._c_roll.set_value(f"{roll_d:+.2f}")
        self._c_pitch.set_value(f"{pitch_d:+.2f}")
        self._c_yaw.set_value(f"{yaw_d:.1f}")

        # Speed
        self._c_sog.set_value(_fmt(sog, ".3f"))
        self._c_stw.set_value(_fmt(stw, ".3f"))
        self._c_sta.set_value(_fmt(sta, ".3f"))
        self._c_smode.set_value(smode)

        # Navigation
        self._c_course.set_value(f"{course_d:.1f}")
        self._c_navsol.set_value(nav)
        self._c_ts.set_value(ts[-13:] if ts != "---" else "---")  # last 13 chars

        # Compass — driven by yaw (heading)
        self._compass.update_state(yaw_d, roll_d, pitch_d)


# ---------------------------------------------------------------------------
# DDS setup (runs once, readers stay alive for the app lifetime)
# ---------------------------------------------------------------------------

# Speed command writer — initialised in _start_dds(), used by Dashboard slider
_speed_writer = None
_speed_sample = None

# Orbit command writer — initialised in _start_dds(), used by orbit button
_orbit_writer = None
_orbit_sample = None


def _publish_speed_command(knots: float) -> None:
    """Write a SpeedCommand sample (knots) to the DDS bus."""
    if _speed_writer is None or _speed_sample is None:
        return
    _speed_sample.knots = knots
    _speed_writer.write(_speed_sample)


def _publish_orbit_command(enabled: bool) -> None:
    """Write an OrbitCommand sample to the DDS bus."""
    if _orbit_writer is None or _orbit_sample is None:
        return
    _orbit_sample.enabled = enabled
    _orbit_writer.write(_orbit_sample)

def _start_dds() -> None:
    global _speed_writer, _speed_sample, _orbit_writer, _orbit_sample
    qos = dds.DomainParticipantQos()
    qos.participant_name.name = "VectorNav_Dashboard"
    participant = dds.DomainParticipant(domain_id=DOMAIN_ID, qos=qos)
    subscriber  = dds.Subscriber(participant)

    speed_topic = dds.Topic(participant, SpeedReportTypeTopic, SpeedReportType)
    speed_reader = dds.DataReader(subscriber, speed_topic)
    speed_reader.set_listener(SpeedListener(), dds.StatusMask.DATA_AVAILABLE)

    pose_topic  = dds.Topic(participant, GlobalPoseReportTypeTopic, GlobalPoseReportType)
    pose_reader = dds.DataReader(subscriber, pose_topic)
    pose_reader.set_listener(PoseListener(), dds.StatusMask.DATA_AVAILABLE)

    # Speed command writer — published when slider moves (knots)
    speed_cmd_topic  = dds.Topic(participant, vn_constants.SPEED_COMMAND_TOPIC,
                                 vn_topics.SpeedCommand)
    _speed_writer    = dds.DataWriter(dds.Publisher(participant), speed_cmd_topic)
    _speed_sample    = vn_topics.SpeedCommand()

    # Orbit command writer — published when orbit button is toggled
    orbit_cmd_topic  = dds.Topic(participant, vn_constants.ORBIT_COMMAND_TOPIC,
                                 vn_topics.OrbitCommand)
    _orbit_writer    = dds.DataWriter(dds.Publisher(participant), orbit_cmd_topic)
    _orbit_sample    = vn_topics.OrbitCommand()

    # Keep references alive for the process lifetime
    _start_dds._refs = (participant, subscriber, speed_reader, pose_reader,
                        _speed_writer, _orbit_writer)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    _start_dds()

    win = Dashboard()

    # Optional: position the Qt window via WINDOW_POS="x,y" env var
    # set by start_all_python.zsh so the dashboard lands in the upper-right quadrant.
    _pos_env = os.environ.get("WINDOW_POS", "")
    if _pos_env:
        try:
            _wx, _wy = _pos_env.split(",")
            win.move(int(_wx), int(_wy))
        except (ValueError, AttributeError):
            pass

    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
 Ship Defense – Command & Control  (Python / pygame / RTI Connext DDS)

 Python GUI equivalent of apps/command_control/main.cpp.

 Window: 1060 × 600
   Left 800 px  – tactical map  (left-click to spawn inbound threats)
   Right 250 px – status panel  (sensors / effectors / active threats)

 Visual elements match the C++ SDL app:
   • ArleighBurke-class.png at waterline (drawn fallback if absent)
   • Green dotted radar rings every 100 px centred on ship
   • Dashed red SPY-1D detection ring at 412 px (220 nm)
   • Typed threat shapes (ballistic / drone / ASCM)
   • VLS launch plumes, interceptor missiles, kill-blast effects
   • Dotted sensor-track lines from detection point to ship bow
   • Status panel: sensor tracks, weapon engagements, threat table

 Mouse: left-click map → spawn threat    ESC / window-close → quit

 DDS roles:
   PUBLISHES  → ThreatTopic          (mouse-spawned threats + position updates)
   SUBSCRIBES → SensorDetectionTopic (from sensor.py  → panel + dotted track lines)
   SUBSCRIBES → EffectorActionTopic  (from effector.py → interceptor/blast visuals)

 Requires sensor.py and effector.py to be running on the same DDS domain.

 Usage:  ~/.venv/bin/python3 command_control.py [-d <domain_id>]
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# VectorNav GPS integration (optional – gracefully disabled if not available)
_VN_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'vector_nav_py'))
if os.path.isdir(_VN_DIR) and _VN_DIR not in sys.path:
    sys.path.append(_VN_DIR)   # append so local ship_ddsEntities.py takes precedence
try:
    from umaa_types import GlobalPoseReportType, GlobalPoseReportTypeTopic  # type: ignore
    import vn_constants as _vn                                               # type: ignore
    _HAVE_VN = True
except ImportError:
    _HAVE_VN = False

import pygame
import rti.connextdds as dds

import application
import shipConstants
import ship_ddsEntities as ddsEntities
import ship_topics


# ---------------------------------------------------------------------------
# Window / geometry  (match C++ exactly)
# ---------------------------------------------------------------------------
WIN_W   = 1060
WIN_H   = 600
MAP_W   = 800
PANEL_X = 810
PANEL_W = 246
CX      = 400           # ship centre x  (C++ SHIP_X) – home position
CY      = 570           # ship waterline y (C++ SHIP_Y) – home position
HULL_SQ = 70 ** 2       # cull when dist² < this

# ---------------------------------------------------------------------------
# Geographic reference for VectorNav GPS positioning
# Maps the VectorNav start position (San Diego Bay) to the ship home pixel.
# GEO_M_PER_PX is exaggerated (5 m/px vs real ~990 m/px) so movement is visible.
# ---------------------------------------------------------------------------
GEO_LAT0     = 32.7157    # reference geodetic latitude  (degrees N)
GEO_LON0     = -117.1611  # reference geodetic longitude (degrees E)
GEO_M_PER_PX = 5.0        # metres per map pixel

REPUBLISH_INTERVAL = 0.5
FPS = 100

EFX_SPEEDS = {1: 150.0, 2: 175.0, 3: 130.0, 4: 210.0, 5: 100.0}
_TTYPE     = {0: "BALST", 1: "DRONE", 2: "ASCM "}


# ---------------------------------------------------------------------------
# Effect dataclasses
# ---------------------------------------------------------------------------
@dataclass
class LaunchPlume:
    x: float; y: float; age: float = 0.0; life: float = 1.4

@dataclass
class KillBlast:
    x: float; y: float; age: float = 0.0; life: float = 1.4

@dataclass
class Interceptor:
    x: float; y: float; target_id: int; speed: float
    age: float = 0.0; life: float = 20.0; will_kill: bool = False; done: bool = False

@dataclass
class EffectEvent:
    lx: float; ly: float; target_id: int; effector_id: int; will_kill: bool


# ---------------------------------------------------------------------------
# Thread-safe shared state
# ---------------------------------------------------------------------------
class GUISharedState:
    def __init__(self) -> None:
        self.lock                = threading.Lock()
        self.sensor_detections:  Dict[int, Any]   = {}
        self.sensor_last_seen:   Dict[int, float]  = {}
        self.effector_actions:   Dict[int, Any]   = {}
        self.effector_last_seen: Dict[int, float]  = {}
        self.pending_effects:    List[EffectEvent] = []
        # VectorNav GPS – ship position updated by GUIPoseRdr thread
        self.ship_px:       float          = float(CX)
        self.ship_py:       float          = float(CY)
        self.ship_lat:      Optional[float] = None
        self.ship_lon:      Optional[float] = None
        self.ship_course_r: float          = 0.0    # radians True North


# ---------------------------------------------------------------------------
# GUI-aware DDS readers
# ---------------------------------------------------------------------------
class GUISensorDetectionRdr(ship_topics.SensorDetectionRdr):
    def __init__(self, subscriber, topic, app_state_obj, gui_state):
        super().__init__(subscriber, topic, app_state_obj)
        self._gui_state = gui_state

    def handler(self, data: Any) -> None:
        with self._gui_state.lock:
            self._gui_state.sensor_detections[data.sensor_id] = data
            self._gui_state.sensor_last_seen[data.sensor_id]  = time.monotonic()


class GUIEffectorActionRdr(ship_topics.EffectorActionRdr):
    def __init__(self, subscriber, topic, app_state_obj, gui_state):
        super().__init__(subscriber, topic, app_state_obj)
        self._gui_state = gui_state

    def handler(self, data: Any) -> None:
        with self._gui_state.lock:
            self._gui_state.effector_actions[data.effector_id]  = data
            self._gui_state.effector_last_seen[data.effector_id] = time.monotonic()
            self._gui_state.pending_effects.append(EffectEvent(
                lx=self._gui_state.ship_px + 40,
                ly=self._gui_state.ship_py - 26,
                target_id=int(data.threat_id),
                effector_id=int(data.effector_id),
                will_kill=bool(data.destroyed),
            ))


# ---------------------------------------------------------------------------
# Geographic coordinate → map pixel conversion
# ---------------------------------------------------------------------------
def latlon_to_px(lat: float, lon: float) -> tuple:
    """Convert geodetic lat/lon to map pixel (x, y).

    North is up (decreasing y), East is right (increasing x).
    Uses GEO_LAT0/LON0 as the map origin pinned to pixel (CX, CY).
    """
    dx_m = (lon - GEO_LON0) * 111_111.0 * math.cos(math.radians(GEO_LAT0))
    dy_m = (lat - GEO_LAT0) * 111_111.0
    px = CX + dx_m / GEO_M_PER_PX
    py = CY - dy_m / GEO_M_PER_PX   # north = up = decreasing y
    return px, py


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _rpt(ox, oy, angle, fwd, rt):
    ca, sa = math.cos(angle), math.sin(angle)
    return (int(ox + ca * fwd - sa * rt), int(oy + sa * fwd + ca * rt))


def draw_threat(surf, x, y, angle, ttype):
    """Port of C++ draw_threat()."""
    if ttype == 0:          # Ballistic missile
        c = (255, 80, 30)
        tip  = _rpt(x, y, angle,  9,  0);  body = _rpt(x, y, angle, -5,  0)
        fl   = _rpt(x, y, angle, -5,  5);  fr   = _rpt(x, y, angle, -5, -5)
        n2   = _rpt(x, y, angle,  7,  2);  n3   = _rpt(x, y, angle,  7, -2)
        pygame.draw.line(surf, c, tip, body)
        pygame.draw.line(surf, c, body, fl);  pygame.draw.line(surf, c, body, fr)
        pygame.draw.line(surf, c, n2, tip);   pygame.draw.line(surf, c, n3, tip)
    elif ttype == 1:        # Drone / UAS
        c = (180, 40, 210)
        for arm in range(4):
            aa  = arm * math.pi / 2 + math.pi / 4
            tip = (x + int(math.cos(aa) * 8), y + int(math.sin(aa) * 8))
            pygame.draw.line(surf, c, (x, y), tip)
            pygame.draw.rect(surf, c, (tip[0] - 2, tip[1] - 2, 4, 4))
        pygame.draw.rect(surf, c, (x - 2, y - 2, 4, 4))
    else:                   # Anti-ship cruise missile
        c = (255, 50, 50)
        tip  = _rpt(x, y, angle,  9,  0);  wl   = _rpt(x, y, angle, -5,  8)
        wr   = _rpt(x, y, angle, -5, -8);  tail = _rpt(x, y, angle, -7,  0)
        pygame.draw.line(surf, c, tip, wl);   pygame.draw.line(surf, c, tip, wr)
        pygame.draw.line(surf, c, wl, tail);  pygame.draw.line(surf, c, wr, tail)


def draw_destroyer(surf, cx, cy):
    """Port of C++ draw_destroyer() – Arleigh Burke side profile, bow right."""
    SL = cx-118; BR = cx+118; DK = cy-16; FDK = DK-6; BK = cy+9
    sp1 = max(BK-cy, 1);  sp2 = max(BK-DK, 1)
    for iy in range(cy, BK+1):
        t = (iy-cy)/sp1
        pygame.draw.line(surf, (50,58,66), (SL+6+int(4*t),iy), (BR-4-int(4*t),iy))
    pygame.draw.rect(surf, (128,138,148), (SL+4,DK,BR-SL-12,cy-DK))
    for iy in range(DK, BK+1):
        t = (iy-DK)/sp2
        tip = BR-2+int(14.0*math.sin(t*math.pi))
        pygame.draw.line(surf, (128,138,148), (BR-12,iy), (tip,iy))
    pygame.draw.rect(surf, (128,138,148), (SL,DK,8,BK-DK))
    pygame.draw.rect(surf, (162,148,98),  (SL+4,DK,BR-SL-12,3))
    pygame.draw.rect(surf, (120,130,140), (cx+8,FDK,BR-cx-20,DK-FDK))
    pygame.draw.rect(surf, (155,142,94),  (cx+8,FDK,BR-cx-20,2))
    pygame.draw.rect(surf, (105,112,122), (cx+80,FDK-8,18,8))
    pygame.draw.line(surf, (88,95,104),   (cx+80,FDK-5),(cx+102,FDK-5))
    pygame.draw.line(surf, (88,95,104),   (cx+80,FDK-4),(cx+102,FDK-4))
    pygame.draw.rect(surf, (110,118,128), (cx+20,FDK-4,50,4))
    for v in range(1,6):
        pygame.draw.line(surf,(85,92,102),(cx+20+v*8,FDK-4),(cx+20+v*8,FDK))
    pygame.draw.rect(surf, (142,152,162), (cx-18,FDK,38,DK-FDK))
    pygame.draw.rect(surf, (142,152,162), (cx-14,DK-32,32,32-(DK-FDK)))
    pygame.draw.rect(surf, (150,160,170), (cx-10,DK-44,26,13))
    pygame.draw.rect(surf, (45,68,95),    (cx-9,DK-43,24,4))
    pygame.draw.rect(surf, (118,126,136), (cx-12,DK-57,22,15))
    pygame.draw.line(surf, (95,102,112),  (cx-1,DK-57),(cx-1,DK-42))
    pygame.draw.line(surf, (95,102,112),  (cx-12,DK-49),(cx+10,DK-49))
    pygame.draw.line(surf, (168,174,182), (cx-5,DK-44),(cx-5,DK-90))
    pygame.draw.line(surf, (168,174,182), (cx-2,DK-44),(cx-2,DK-82))
    pygame.draw.rect(surf, (148,154,162), (cx-10,DK-96,14,8))
    pygame.draw.line(surf, (158,164,172), (cx-20,DK-74),(cx+14,DK-74))
    pygame.draw.line(surf, (158,164,172), (cx-17,DK-64),(cx+11,DK-64))
    pygame.draw.line(surf, (128,134,142), (cx-20,DK-74),(cx-5,DK-90))
    pygame.draw.line(surf, (128,134,142), (cx+14,DK-74),(cx-2,DK-82))
    pygame.draw.rect(surf, (106,114,122), (cx-48,FDK,18,DK-FDK+20))
    pygame.draw.rect(surf, (88,95,104),   (cx-50,FDK-6,22,7))
    pygame.draw.rect(surf, (32,36,40),    (cx-49,FDK-5,20,4))
    pygame.draw.rect(surf, (136,146,156), (cx-78,FDK,26,DK-FDK))
    pygame.draw.rect(surf, (136,146,156), (cx-76,DK-26,22,26-(DK-FDK)))
    pygame.draw.rect(surf, (136,146,156), (cx-74,DK-32,18,7))
    pygame.draw.line(surf, (158,164,172), (cx-66,DK-32),(cx-66,DK-56))
    pygame.draw.line(surf, (158,164,172), (cx-74,DK-48),(cx-58,DK-48))
    pygame.draw.line(surf, (158,164,172), (cx-72,DK-40),(cx-60,DK-40))
    pygame.draw.rect(surf, (108,116,126), (cx-15,DK-3,28,3))
    for v in range(1,4):
        pygame.draw.line(surf,(82,89,99),(cx-15+v*7,DK-3),(cx-15+v*7,DK))
    hxl = SL+6;  hw = cx-79-SL-6
    pygame.draw.rect(surf, (112,122,132), (hxl,FDK,hw,DK-FDK))
    hx = hxl + hw//2
    pygame.draw.line(surf,(80,90,100),(hx-7,FDK+3),(hx-7,FDK+10))
    pygame.draw.line(surf,(80,90,100),(hx+7,FDK+3),(hx+7,FDK+10))
    pygame.draw.line(surf,(80,90,100),(hx-7,FDK+6),(hx+7,FDK+6))
    oc = (65,75,84)
    pygame.draw.line(surf,oc,(SL+4,DK),(BR-12,DK))
    pygame.draw.line(surf,oc,(BR-12,DK),(BR+12,cy-5))
    pygame.draw.line(surf,oc,(BR+12,cy-5),(BR+10,BK-2))
    pygame.draw.line(surf,oc,(BR+10,BK-2),(BR-12,BK))
    pygame.draw.line(surf,oc,(BR-12,BK),(SL+6,BK))
    pygame.draw.line(surf,oc,(SL+4,DK),(SL+4,BK+1))
    wc = (28,72,120)
    pygame.draw.line(surf,wc,(SL+4,cy),(SL-10,cy+3))
    pygame.draw.line(surf,wc,(SL+4,cy+2),(SL-18,cy+5))
    pygame.draw.line(surf,wc,(SL+4,cy-1),(SL-14,cy+2))


def draw_plume(surf, p):
    frac = p.age / p.life
    r    = max(1, int(4 + 18 * frac))
    bright = int(230 * (1 - frac));  alpha = int(220 * (1 - frac))
    if alpha <= 0: return
    ps = pygame.Surface((r*2+2, r*2+2), pygame.SRCALPHA)
    pygame.draw.circle(ps, (bright, bright, bright, alpha), (r+1, r+1), r)
    if r > 6:
        d = max(0, bright - 40)
        pygame.draw.circle(ps, (d, d, d, alpha//2), (r+1, r+1), r*2//3)
    surf.blit(ps, (int(p.x)-r-1, int(p.y)-r-1))


def draw_interceptor(surf, x, y, angle):
    tip = _rpt(x, y, angle, 6, 0);  bl = _rpt(x, y, angle, -3, 3)
    br  = _rpt(x, y, angle,-3,-3);  e1 = _rpt(x, y, angle, -4, 0)
    e2  = _rpt(x, y, angle,-9, 0)
    pygame.draw.line(surf, (200,255,200), tip, bl)
    pygame.draw.line(surf, (200,255,200), tip, br)
    pygame.draw.line(surf, (200,255,200), bl,  br)
    pygame.draw.line(surf, (255,220,80),  e1,  e2)


def draw_blast(surf, b):
    frac = b.age / b.life;  r = 4 + 24 * frac
    bx, by = int(b.x), int(b.y)
    if frac < 0.35:
        fr = max(1, int(8*(1 - frac/0.35)))
        fs = pygame.Surface((fr*2+1, fr*2+1), pygame.SRCALPHA)
        fs.fill((255, 255, 210, 200))
        surf.blit(fs, (bx-fr, by-fr))
    rg = int(160*(1 - frac*0.5));  ir = max(1, int(r))
    pygame.draw.circle(surf, (255, rg, 0), (bx, by), ir,   1)
    pygame.draw.circle(surf, (255, rg, 0), (bx, by), ir+1, 1)
    for s in range(8):
        a  = s * math.pi / 4
        p1 = (int(bx+r*0.6*math.cos(a)), int(by+r*0.6*math.sin(a)))
        p2 = (int(bx+(r+5)*math.cos(a)), int(by+(r+5)*math.sin(a)))
        pygame.draw.line(surf, (255,220,50), p1, p2)


# ---------------------------------------------------------------------------
# VectorNav GPS reader  (updates ship position from GlobalPoseReportType)
# ---------------------------------------------------------------------------
if _HAVE_VN:
    class GUIPoseRdr(ddsEntities.Reader):
        """Subscribes to VectorNav GlobalPoseReportType and updates ship position.

        Converts incoming geodetic lat/lon to map pixel coordinates via
        latlon_to_px() and stores the result in GUISharedState for the
        render loop to consume each frame.
        """

        def __init__(self, subscriber: dds.Subscriber, topic: dds.Topic,
                     gui_state: GUISharedState) -> None:
            ddsEntities.Reader.__init__(
                self, subscriber, topic, GlobalPoseReportType)
            self._gui_state = gui_state

        def handler(self, data: Any) -> None:
            lat = data.position.geodeticLatitude
            lon = data.position.geodeticLongitude
            px, py = latlon_to_px(lat, lon)
            crs = data.course if data.course is not None else 0.0
            print(f"[C2][GPS] Lat={lat:+.6f}°  Lon={lon:+.7f}°  "
                  f"Crs={math.degrees(crs):.1f}°TN  → px=({px:.1f},{py:.1f})")
            logging.info("[C2] Pose Lat=%.6f Lon=%.7f → px=(%.1f,%.1f)",
                         lat, lon, px, py)
            with self._gui_state.lock:
                self._gui_state.ship_lat      = lat
                self._gui_state.ship_lon      = lon
                self._gui_state.ship_course_r = crs
                self._gui_state.ship_px       = px
                self._gui_state.ship_py       = py


# ---------------------------------------------------------------------------
# Pre-rendered radar ring surface
# ---------------------------------------------------------------------------
def _build_radar_surf() -> pygame.Surface:
    s = pygame.Surface((MAP_W, WIN_H), pygame.SRCALPHA)
    for ring in range(100, 500, 100):
        for deg in range(0, 360, 3):
            a = math.radians(deg)
            rx = CX + int(ring*math.cos(a));  ry = CY + int(ring*math.sin(a))
            if 0 <= rx < MAP_W and 0 <= ry < WIN_H:
                s.set_at((rx, ry), (20, 55, 30, 255))
    for deg in range(0, 360):
        if deg % 6 >= 3: continue
        a = math.radians(deg)
        rx = CX + int(412*math.cos(a));  ry = CY + int(412*math.sin(a))
        if 0 <= rx < MAP_W and 0 <= ry < WIN_H:
            s.set_at((rx, ry), (180, 45, 45, 255))
    return s


# ---------------------------------------------------------------------------
# Status panel
# ---------------------------------------------------------------------------
_SNAMES = {s.sensor_id:  s.name for s in shipConstants.SENSOR_DEFS}
_ENAMES = {e.effector_id: e.name for e in shipConstants.EFFECTOR_DEFS}


def draw_status_panel(surf, fsm, fhd, threats, gui, ship_cx=CX, ship_cy=CY):
    now = time.monotonic()
    pygame.draw.rect(surf, (22, 22, 32), (PANEL_X, 0, PANEL_W, WIN_H))
    pygame.draw.line(surf, (65, 65, 85), (PANEL_X, 0), (PANEL_X, WIN_H-1))

    def txt(font, x, y, text, col):
        surf.blit(font.render(text, True, col), (x, y))

    def sep(y):
        pygame.draw.line(surf, (65,65,85), (PANEL_X+2, y), (PANEL_X+PANEL_W-4, y))
        return y + 5

    CN = PANEL_X+3;  CT = PANEL_X+68;  CC = PANEL_X+116
    LH = 13;  LHD = 21;  pcy = 8

    # ── SENSORS ──────────────────────────────────────────────────────────
    txt(fhd, CN, pcy, "SENSORS", (240,210,60));   pcy += LHD;  pcy = sep(pcy)
    txt(fsm, CN, pcy, "SENSOR    ", (100,100,120))
    txt(fsm, CT, pcy, "THREAT",    (100,100,120))
    txt(fsm, CC, pcy, "CONF",      (100,100,120))
    pcy += LH;  pcy = sep(pcy)
    with gui.lock:
        sd = dict(gui.sensor_detections);  st = dict(gui.sensor_last_seen)
    if sd:
        for sid in sorted(sd):
            d = sd[sid];  active = (now - st.get(sid,0)) < 5.0
            col = (80,220,80) if active else (110,110,110)
            txt(fsm, CN, pcy, f"{_SNAMES.get(sid,f'SEN-{sid}'):<12}", col)
            if active:
                txt(fsm, CT, pcy, f"T#{d.threat_id:<5}", col)
                txt(fsm, CC, pcy, f"{d.confidence:3}%", col)
            else:
                txt(fsm, CT, pcy, "IDLE   ", col);  txt(fsm, CC, pcy, " --", col)
            pcy += LH
    else:
        txt(fsm, CN, pcy, "none", (80,80,80));  pcy += LH

    # ── EFFECTORS ─────────────────────────────────────────────────────────
    pcy += 4;  pcy = sep(pcy)
    txt(fhd, CN, pcy, "EFFECTORS", (60,200,240));  pcy += LHD;  pcy = sep(pcy)
    txt(fsm, CN, pcy, "WEAPON    ", (100,100,120))
    txt(fsm, CT, pcy, "TARGET",    (100,100,120))
    txt(fsm, CC, pcy, "STATUS",    (100,100,120))
    pcy += LH;  pcy = sep(pcy)
    with gui.lock:
        ed = dict(gui.effector_actions);  et = dict(gui.effector_last_seen)
    if ed:
        for eid in sorted(ed):
            a = ed[eid];  active = (now - et.get(eid,0)) < 5.0
            col = ((110,110,110) if not active
                   else (255,160,0) if a.destroyed else (80,220,80))
            txt(fsm, CN, pcy, f"{_ENAMES.get(eid,f'EFX-{eid}'):<10}", col)
            if active:
                txt(fsm, CT, pcy, f"T#{a.threat_id:<5}", col)
                txt(fsm, CC, pcy, "KILL  " if a.destroyed else "FIRING", col)
            else:
                txt(fsm, CT, pcy, " --   ", col);  txt(fsm, CC, pcy, "IDLE  ", col)
            pcy += LH
    else:
        txt(fsm, CN, pcy, "none", (80,80,80));  pcy += LH

    # ── THREATS ───────────────────────────────────────────────────────────
    pcy += 4;  pcy = sep(pcy)
    txt(fhd, CN, pcy, "THREATS", (230,80,80));  pcy += LHD;  pcy = sep(pcy)
    C2 = CN+44;  C3 = CN+84;  C4 = CN+124
    txt(fsm, CN, pcy, "ID",   (100,100,120));  txt(fsm, C2, pcy, "TYPE", (100,100,120))
    txt(fsm, C3, pcy, "SPD",  (100,100,120));  txt(fsm, C4, pcy, "TTI",  (100,100,120))
    pcy += LH;  pcy = sep(pcy)
    if not threats:
        txt(fsm, CN, pcy, "NO CONTACTS", (80,80,80))
    else:
        for t in sorted(threats.values(), key=lambda x: x.id):
            if pcy + LH > WIN_H - 6: break
            dx = t.x-ship_cx;  dy = t.y-ship_cy;  dst = math.sqrt(dx*dx+dy*dy)
            tti = dst/t.speed if t.speed > 0.01 else 99.0
            col = (220,90,90)
            txt(fsm, CN, pcy, f"T#{t.id}",                col)
            txt(fsm, C2, pcy, _TTYPE.get(t.id%3,"UNK"),   col)
            txt(fsm, C3, pcy, f"{int(t.speed*30)}kt",     col)
            txt(fsm, C4, pcy, f"{tti:3.0f}s",             col)
            pcy += LH

    # ── GPS POSITION (VectorNav) ──────────────────────────────────────────
    pcy += 4;  pcy = sep(pcy)
    txt(fhd, CN, pcy, "GPS POSITION", (80,200,255));  pcy += LHD;  pcy = sep(pcy)
    with gui.lock:
        lat = gui.ship_lat;  lon = gui.ship_lon;  crs = gui.ship_course_r
    if lat is not None:
        txt(fsm, CN, pcy, f"Lat: {lat:+.5f}\u00b0",          (120,220,255));  pcy += LH
        txt(fsm, CN, pcy, f"Lon: {lon:+.6f}\u00b0",          (120,220,255));  pcy += LH
        txt(fsm, CN, pcy, f"Crs: {math.degrees(crs):05.1f}\u00b0TN",  (120,220,255));  pcy += LH
    else:
        txt(fsm, CN, pcy, "NO FIX  (VectorNav_Publisher", (80,80,80));  pcy += LH
        txt(fsm, CN, pcy, "not running)",                 (80,80,80));  pcy += LH


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def command_control_main(domain_id: int) -> None:
    print("Command & Control (GUI) Powering Up")
    logging.info("C&C GUI starting on domain %d", domain_id)

    # pygame ─────────────────────────────────────────────────────────────
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Ship Defense – Command & Control")
    clock  = pygame.time.Clock()
    try:
        fsm = pygame.font.SysFont("monospace", 11)
        fhd = pygame.font.SysFont("monospace", 14, bold=True)
    except Exception:
        fsm = pygame.font.Font(None, 14)
        fhd = pygame.font.Font(None, 18)

    # Ship photo ─────────────────────────────────────────────────────────
    _here = os.path.dirname(os.path.realpath(__file__))
    ship_img: Optional[pygame.Surface] = None
    ship_iw = 160
    for candidate in [
        os.path.join(_here, "..", "ArleighBurke-class.png"),
        os.path.join(_here, "ArleighBurke-class.png"),
    ]:
        try:
            raw = pygame.image.load(candidate).convert_alpha()
            DISP_H = 48
            ship_iw = max(1, DISP_H * raw.get_width() // raw.get_height())
            ship_img = pygame.transform.smoothscale(raw, (ship_iw, DISP_H))
            print(f"[C2] Loaded {candidate} ({ship_iw}×{DISP_H})")
            break
        except Exception:
            pass
    if not ship_img:
        print("[C2] Ship image not found – using drawn destroyer")

    # Pre-render radar rings ─────────────────────────────────────────────
    print("[C2] Building radar ring surface…")
    radar_surf = _build_radar_surf()
    print("[C2] Ready")

    # DDS ────────────────────────────────────────────────────────────────
    ddsEntities.register_ship_types()
    _qos = dds.DomainParticipantQos()
    _qos.participant_name.name = "command_control"
    participant  = dds.DomainParticipant(domain_id, _qos)
    thr_topic    = dds.Topic(participant, shipConstants.THREAT_TOPIC,           shipConstants.Threat)
    det_topic    = dds.Topic(participant, shipConstants.SENSOR_DETECTION_TOPIC, shipConstants.SensorDetection)
    efx_topic    = dds.Topic(participant, shipConstants.EFFECTOR_ACTION_TOPIC,  shipConstants.EffectorAction)
    pub          = dds.Publisher(participant)
    sub          = dds.Subscriber(participant)
    app_state    = ship_topics.ApplicationStateObj("command_control")
    gui_state    = GUISharedState()
    threat_w     = ship_topics.ThreatWtr(pub, thr_topic, app_state)
    detection_r  = GUISensorDetectionRdr(sub, det_topic, app_state, gui_state)
    effector_r   = GUIEffectorActionRdr(sub,  efx_topic, app_state, gui_state)
    threat_w.writer.set_listener(ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)
    detection_r.start();  effector_r.start()

    # VectorNav GPS subscriber (optional – gracefully absent if publisher not running)
    pose_r: Optional[Any] = None
    if _HAVE_VN:
        pose_topic = dds.Topic(participant, _vn.POSE_TOPIC, GlobalPoseReportType)
        pose_r = GUIPoseRdr(sub, pose_topic, gui_state)
        pose_r.start()
        print("[C2] VectorNav GPS subscriber active – ship will follow Lat/Lon")
    else:
        print("[C2] VectorNav GPS not available – ship at fixed position")

    # Sim state ──────────────────────────────────────────────────────────
    threats:      Dict[int, Any]    = {}
    plumes:       List[LaunchPlume] = []
    blasts:       List[KillBlast]   = []
    interceptors: List[Interceptor] = []
    next_id = 1;  last_rep = time.monotonic();  prev_t = time.monotonic()

    print("[C2] GUI running – left-click map to spawn threat, ESC to quit")

    running = True
    while running and application.run_flag:
        now = time.monotonic()
        dt  = min(now - prev_t, 0.05)
        prev_t = now

        # VectorNav GPS – thread-safe snapshot of current ship pixel position
        with gui_state.lock:
            ship_cx = gui_state.ship_px
            ship_cy = gui_state.ship_py

        # Events ─────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False; application.run_flag = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False; application.run_flag = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if mx < MAP_W and my < WIN_H - 10:
                    t = shipConstants.Threat()
                    t.id = next_id; next_id += 1
                    t.x = float(mx); t.y = float(my)
                    t.heading = 180.0; t.speed = 22.0
                    t.severity = (t.id % 3) + 1   # cycles 1 → 2 → 3
                    threats[t.id] = t; threat_w.write_threat(t)
                    logging.info("Threat id=%d at (%.0f,%.0f)", t.id, t.x, t.y)

        # Move threats ───────────────────────────────────────────────────
        for t in threats.values():
            dx = ship_cx - t.x; dy = (ship_cy-16) - t.y; d = math.sqrt(dx*dx+dy*dy)
            if d > 1e-6: t.x += (dx/d)*t.speed*dt; t.y += (dy/d)*t.speed*dt

        # Republish ──────────────────────────────────────────────────────
        if now - last_rep >= REPUBLISH_INTERVAL:
            for t in threats.values(): threat_w.write_threat(t)
            last_rep = now

        # Cull hull hits ──────────────────────────────────────────────────
        for tid in [k for k,t in threats.items()
                    if (ship_cx-t.x)**2+(ship_cy-t.y)**2 < HULL_SQ]:
            print(f"\n[C2] *** IMPACT: T#{tid} reached the hull! ***")
            threats.pop(tid, None)

        # DDS effects  (driven entirely by EffectorActionTopic from effector.py)
        with gui_state.lock:
            evs = gui_state.pending_effects[:]; gui_state.pending_effects.clear()
        for ev in evs:
            plumes.append(LaunchPlume(ev.lx, ev.ly))
            interceptors.append(Interceptor(ev.lx, ev.ly, ev.target_id,
                EFX_SPEEDS.get(ev.effector_id, 150.0), will_kill=ev.will_kill))

        # Age effects ─────────────────────────────────────────────────────
        for p in plumes: p.age += dt
        for b in blasts: b.age += dt
        plumes = [p for p in plumes if p.age < p.life]
        blasts = [b for b in blasts if b.age < b.life]

        # Update interceptors ─────────────────────────────────────────────
        kills: List[int] = []
        for ic in interceptors:
            if ic.done: continue
            ic.age += dt
            tgt = threats.get(ic.target_id)
            if not tgt: ic.done = True; continue
            dx = tgt.x-ic.x; dy = tgt.y-ic.y; d = math.sqrt(dx*dx+dy*dy)
            if d < 10.0:
                ic.done = True
                blasts.append(KillBlast(ic.x, ic.y, life=1.4 if ic.will_kill else 0.7))
                if ic.will_kill and ic.target_id not in kills:
                    kills.append(ic.target_id)
            else:
                ic.x += (dx/d)*ic.speed*dt; ic.y += (dy/d)*ic.speed*dt
        interceptors = [ic for ic in interceptors if not ic.done and ic.age < ic.life]
        for kid in kills: threats.pop(kid, None)

        # ════════════════════════════════════════════════════════════════
        # RENDER
        # ════════════════════════════════════════════════════════════════
        screen.fill((10, 20, 40))
        for wy in range(60, WIN_H, 18):
            pygame.draw.line(screen, (15,30,55), (0,wy), (MAP_W-1,wy))
        pygame.draw.rect(screen, (8,16,32), (0,int(ship_cy)-2,MAP_W,WIN_H-(int(ship_cy)-2)))

        # Radar rings follow the ship (pre-built surface centred on CX,CY → offset)
        screen.blit(radar_surf, (int(ship_cx - CX), int(ship_cy - CY)))

        for p in plumes: draw_plume(screen, p)

        if ship_img:
            screen.blit(ship_img, (int(ship_cx) - ship_iw//2, int(ship_cy) + 5 - 48))
        else:
            draw_destroyer(screen, int(ship_cx), int(ship_cy))

        for t in threats.values():
            angle = math.atan2((ship_cy-16)-t.y, ship_cx-t.x)
            draw_threat(screen, int(t.x), int(t.y), angle, t.id%3)
            tx, ty = int(t.x), int(t.y)
            pygame.draw.rect(screen, (245,220,70), (tx-6,ty-6,12,12), 1)
            screen.blit(fsm.render(f"T#{t.id}", True, (245,220,70)), (tx+8,ty-8))

        screen.blit(fsm.render("Click map to spawn inbound threat  |  ESC to quit",
                               True, (180,190,210)), (10, 8))
        screen.blit(fsm.render(f"Active threats: {len(threats)}",
                               True, (180,190,210)), (10, 22))

        # Dotted sensor track lines
        with gui_state.lock:
            dsnap = dict(gui_state.sensor_detections)
            dtimes = dict(gui_state.sensor_last_seen)
        now2 = time.monotonic()
        for sid, d in dsnap.items():
            if (now2 - dtimes.get(sid,0)) > 5.0: continue
            x1,y1 = int(d.x),int(d.y); x2,y2 = int(ship_cx),int(ship_cy)-16
            ln = math.sqrt((x2-x1)**2+(y2-y1)**2); steps = max(1,int(ln))
            for s in range(0, steps, 8):
                fr = s/steps; px_ = x1+int((x2-x1)*fr); py_ = y1+int((y2-y1)*fr)
                if 0 <= px_ < MAP_W and 0 <= py_ < WIN_H:
                    screen.set_at((px_,py_), (150,145,25))

        for ic in interceptors:
            if ic.done: continue
            angle = -math.pi/2
            tgt = threats.get(ic.target_id)
            if tgt: angle = math.atan2(tgt.y-ic.y, tgt.x-ic.x)
            draw_interceptor(screen, ic.x, ic.y, angle)

        for b in blasts: draw_blast(screen, b)

        draw_status_panel(screen, fsm, fhd, threats, gui_state, ship_cx, ship_cy)

        pygame.display.flip()
        clock.tick(FPS)

    application.run_flag = False
    if pose_r:
        pose_r.join()
    pygame.quit()
    print("Command & Control GUI Exiting")
    logging.info("C&C GUI exiting")


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./command_control.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T", level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="RTI Connext DDS: Ship Threat Defense – Command & Control GUI")
    parser.add_argument("-d","--domain", type=int, default=0,
                        help="DDS Domain ID (0-232)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233
    command_control_main(args.domain)

"""
vn_topics.py — UMAA VectorNav topic Writers and Readers
=========================================================
Mirrors the role of pyCompiledTypes/topics.py in the TMS example.

Contains:
  VectorNavState          — simulation / sensor state object (shared by writers)
  SpeedReport_Wtr         — periodic writer for SpeedReportType   (1 Hz)
  GlobalPoseReport_Wtr    — periodic writer for GlobalPoseReportType (1 Hz)
  SpeedReport_Rdr         — WaitSet reader for SpeedReportType
  GlobalPoseReport_Rdr    — WaitSet reader for GlobalPoseReportType

Each Writer / Reader inherits from ddsEntities.Writer / ddsEntities.Reader and
overrides only the methods that are topic-specific:
  Writer  →  write()      (update dynamic fields then write sample)
  Reader  →  handler()    (process one received typed sample)

Key differences from TMS topics.py:
  - No ApplicationStateObj state machine — just a lightweight VectorNavState
    that drives a simulated USV sensor.
  - Static sample fields are set in __init__; dynamic fields in write().
  - VectorNavState is time-based (uses time.monotonic()) so that both writer
    threads always produce consistent, synchronised values without locking.
"""

import logging
import math
import time

import rti.types as idl
import ddsEntities
import vn_constants
from umaa_types import (
    GlobalPoseReportType,
    GlobalPoseReportTypeTopic,
    GUIDUtil,
    GeoPosition2D,
    NavigationSolutionEnumType,
    Orientation3DNEDType,
    PitchYNEDType,
    RollXNEDType,
    SpeedReportType,
    SpeedReportTypeTopic,
    VehicleSpeedModeEnumType,
    YawZNEDType,
    set_timestamp,
)


# ---------------------------------------------------------------------------
# Timestamp formatting helper
# ---------------------------------------------------------------------------

def _fmt_ts(ts) -> str:
    """Format a UMAA DateTimeType timestamp as 'seconds.nanoseconds'.

    Normalises the (seconds, nanoseconds) pair before formatting.
    The IDL field ``nanoseconds`` is ``uint32`` (0–4 294 967 295), which is
    wider than the valid sub-second range (0–999 999 999).  Connext does NOT
    guarantee the value is normalised on receive, so we always compute:

        total_ns = seconds * 1_000_000_000 + nanoseconds
        sec, ns  = divmod(total_ns, 1_000_000_000)

    before formatting, making it safe for both locally-set and externally-
    received timestamps.
    """
    sec, ns = divmod(ts.seconds * 1_000_000_000 + ts.nanoseconds, 1_000_000_000)
    return f"{sec}.{ns:09d}"



@idl.struct
class SpeedCommand:
    """Speed command in knots.  Published by Dashboard slider, subscribed by Publisher."""
    knots: float = 5.0


@idl.struct
class OrbitCommand:
    """Orbit enable/disable command.  Published by Dashboard button, subscribed by Publisher."""
    enabled: bool = False


# ===========================================================================
# VectorNavState  —  equivalent of ApplicationStateObj in TMS
# ===========================================================================

class VectorNavState:
    """
    Shared simulation state for the VectorNav component.

    Motion profile (two phases, controlled by Dashboard orbit button):
      Phase 'straight': Ship steams in a fixed heading from a checkpoint.
                        Initially 045° True North from home.
      Phase 'orbit':    Ship circles clockwise around HOME at the radius
                        it had when orbit was enabled.

    Phase transitions:
      set_orbit(True)  → snapshot current position, compute orbit radius /
                         angle from home, reset clock, enter 'orbit'.
      set_orbit(False) → snapshot current position and heading, reset clock,
                         enter 'straight' (continues in tangent direction).
      set_speed(knots) → snapshot current position/angle, reset clock,
                         keep current phase.

    Starting position: San Diego Bay, heading 045° True North.
    """

    _HOME_LAT: float = 32.7157     # degrees N  — orbit centre
    _HOME_LON: float = -117.1611   # degrees E

    def __init__(self):
        self._t0 = time.monotonic()

        # Static values
        self.alt = 0.3                            # m MSL (antenna height)

        # Speed in knots — updated live by SpeedCommand_Rdr from Dashboard slider
        self.speed_knots: float = float(vn_constants.SPEED_KNOTS_DEFAULT)

        # IdentifierType source field — set once, shared by all writers
        self.source = GUIDUtil.make_source_id(vn_constants.VECNAV_GUID)

        # Phase — 'straight' or 'orbit'
        self._phase: str = 'straight'

        # Straight-phase state (initial: home position, heading 045°)
        self._str_lat0: float  = self._HOME_LAT
        self._str_lon0: float  = self._HOME_LON
        self._str_hdg_r: float = math.radians(45.0)

        # Orbit-phase state (populated when set_orbit(True) is called)
        self._orb_radius_m: float = 1.0   # metres; computed at orbit entry
        self._orb_theta0: float   = 0.0   # orbit angle (radians) at phase entry

    # ------------------------------------------------------------------
    # Internal elapsed time helper
    # ------------------------------------------------------------------

    def _t(self) -> float:
        return time.monotonic() - self._t0

    # ------------------------------------------------------------------
    # Dynamic sensor properties (computed from elapsed time)
    # ------------------------------------------------------------------

    @property
    def course_r(self) -> float:
        """Heading in radians (True North).

        Straight: fixed heading stored at last checkpoint.
        Orbit:    tangent to the clockwise circle at current position.
        """
        if self._phase == 'straight':
            return self._str_hdg_r
        v = self.speed_knots * 0.5144
        omega = v / self._orb_radius_m
        theta = self._orb_theta0 + omega * self._t()
        return theta + math.pi / 2                 # clockwise tangent

    @property
    def sog(self) -> float:
        """Speed Over Ground  m/s  — commanded knots converted to m/s with small wave variation."""
        return (self.speed_knots + 0.2 * math.sin(0.08 * self._t())) * 0.5144

    @property
    def stw(self) -> float:
        """Speed Through Water  m/s  (SOG + small current offset)."""
        return self.sog + 0.05

    @property
    def roll_r(self) -> float:
        """Roll  radians  (±2.5° wave-induced)."""
        return math.radians(2.5 * math.sin(0.20 * self._t()))

    @property
    def pitch_r(self) -> float:
        """Pitch  radians  (±1.2° wave-induced)."""
        return math.radians(1.2 * math.sin(0.13 * self._t()))

    @property
    def lat(self) -> float:
        """Geodetic latitude  degrees."""
        t = self._t()
        v = self.speed_knots * 0.5144
        if self._phase == 'straight':
            return self._str_lat0 + (v * t / 111_111.0) * math.cos(self._str_hdg_r)
        omega = v / self._orb_radius_m
        theta = self._orb_theta0 + omega * t
        return self._HOME_LAT + (self._orb_radius_m / 111_111.0) * math.cos(theta)

    @property
    def lon(self) -> float:
        """Geodetic longitude  degrees."""
        t = self._t()
        v = self.speed_knots * 0.5144
        if self._phase == 'straight':
            lat_cos = math.cos(math.radians(self._str_lat0))
            return self._str_lon0 + (v * t / (111_111.0 * lat_cos)) * math.sin(self._str_hdg_r)
        lat_cos = math.cos(math.radians(self._HOME_LAT))
        omega = v / self._orb_radius_m
        theta = self._orb_theta0 + omega * t
        return self._HOME_LON + (self._orb_radius_m / (111_111.0 * lat_cos)) * math.sin(theta)

    # ------------------------------------------------------------------
    # Phase control
    # ------------------------------------------------------------------

    def set_orbit(self, enabled: bool) -> None:
        """Enable or disable clockwise orbit around home.

        Position is always continuous — no jumps on transition.
        """
        # Snapshot current state BEFORE resetting _t0
        cur_lat   = self.lat
        cur_lon   = self.lon
        cur_hdg_r = self.course_r

        if enabled and self._phase == 'straight':
            # Compute orbit radius = current distance from home
            dlat = (cur_lat - self._HOME_LAT) * 111_111.0
            dlon = (cur_lon - self._HOME_LON) * 111_111.0 * math.cos(math.radians(self._HOME_LAT))
            self._orb_radius_m = max(math.hypot(dlat, dlon), 5.0)
            self._orb_theta0   = math.atan2(dlon, dlat)   # bearing from home
            self._t0           = time.monotonic()
            self._phase        = 'orbit'
            print(f'[VN] Orbit ENABLED  radius={self._orb_radius_m:.1f}m'
                  f'  θ={math.degrees(self._orb_theta0):.1f}°', flush=True)

        elif not enabled and self._phase == 'orbit':
            # Exit orbit: go straight on current tangent heading
            self._str_lat0  = cur_lat
            self._str_lon0  = cur_lon
            self._str_hdg_r = cur_hdg_r
            self._t0        = time.monotonic()
            self._phase     = 'straight'
            print(f'[VN] Orbit DISABLED  heading={math.degrees(cur_hdg_r) % 360:.1f}°TN',
                  flush=True)

    def set_speed(self, knots: float) -> None:
        """Change commanded speed without a position jump.

        During orbit:   advances the orbit angle to now, then resets clock.
        During straight: snapshots current position, then resets clock.
        """
        if self._phase == 'orbit':
            v_old = self.speed_knots * 0.5144
            self._orb_theta0 += (v_old / self._orb_radius_m) * self._t()
        else:
            self._str_lat0 = self.lat
            self._str_lon0 = self.lon
        self._t0 = time.monotonic()
        self.speed_knots = knots



# ===========================================================================
# SpeedStatus — Writer
# ===========================================================================

class SpeedReport_Wtr(ddsEntities.Writer):
    """
    Periodic writer for UMAA::SA::SpeedStatus::SpeedReportType.

    Static fields (set in __init__):
        mode, source

    Dynamic fields (updated each write() call from VectorNavState):
        speedOverGround, speedThroughWater, timeStamp
    """

    def __init__(self, participant, vn_state: VectorNavState):
        ddsEntities.Writer.__init__(
            self,
            participant,
            True,                          # periodic
            vn_constants.PUBLISH_RATE_HZ,  # period (seconds)
            SpeedReportType,               # compiled type class
            SpeedReportTypeTopic)          # DDS topic name

        self._vn_state = vn_state

        # *** Set static sample fields (handler() pattern from TMS) ***
        self._sample.mode   = VehicleSpeedModeEnumType.MRC
        self._sample.source = vn_state.source

    def write(self):
        """Update dynamic fields and write one SpeedReportType sample."""
        s = self._vn_state

        self._sample.speedOverGround   = s.sog
        self._sample.speedThroughWater = s.stw
        set_timestamp(self._sample)

        self._writer.write(self._sample)

        ts = self._sample.timeStamp
        print(
            f'[VN][Speed ][{_fmt_ts(ts)}]'
            f'  SOG={s.sog:.3f} m/s'
            f'  STW={s.stw:.3f} m/s'
            f'  Mode={self._sample.mode.name}',
            flush=True)
        logging.info('SpeedReport  SOG=%.3f  STW=%.3f', s.sog, s.stw)


# ===========================================================================
# GlobalPoseStatus — Writer
# ===========================================================================

class GlobalPoseReport_Wtr(ddsEntities.Writer):
    """
    Periodic writer for UMAA::SA::GlobalPoseStatus::GlobalPoseReportType.

    Static fields (set in __init__):
        navigationSolution, source

    Dynamic fields (updated each write() call from VectorNavState):
        position, altitude, attitude, course, timeStamp
    """

    def __init__(self, participant, vn_state: VectorNavState):
        ddsEntities.Writer.__init__(
            self,
            participant,
            True,
            vn_constants.PUBLISH_RATE_HZ,
            GlobalPoseReportType,
            GlobalPoseReportTypeTopic)

        self._vn_state = vn_state

        # *** Set static sample fields ***
        self._sample.navigationSolution = NavigationSolutionEnumType.MEASURED
        self._sample.source             = vn_state.source

    def write(self):
        """Update dynamic fields and write one GlobalPoseReportType sample."""
        s = self._vn_state

        self._sample.position = GeoPosition2D(
            geodeticLatitude=s.lat,
            geodeticLongitude=s.lon)

        self._sample.altitude = s.alt
        self._sample.course   = s.course_r

        self._sample.attitude = Orientation3DNEDType(
            pitch=PitchYNEDType(pitch=s.pitch_r),
            roll=RollXNEDType(roll=s.roll_r),
            yaw=YawZNEDType(yaw=s.course_r))

        set_timestamp(self._sample)

        self._writer.write(self._sample)

        ts = self._sample.timeStamp
        print(
            f'[VN][Pose  ][{_fmt_ts(ts)}]'
            f'  Lat={s.lat:+.6f}°'
            f'  Lon={s.lon:+.7f}°'
            f'  Alt={s.alt:.1f}m'
            f'  Course={math.degrees(s.course_r):.1f}°TN'
            f'  Roll={math.degrees(s.roll_r):+.2f}°'
            f'  Pitch={math.degrees(s.pitch_r):+.2f}°',
            flush=True)
        logging.info('GlobalPose  Lat=%.6f  Lon=%.7f  Alt=%.1f',
                     s.lat, s.lon, s.alt)


# ===========================================================================
# SpeedStatus — Reader
# ===========================================================================

class SpeedReport_Rdr(ddsEntities.Reader):
    """
    WaitSet-based reader for UMAA::SA::SpeedStatus::SpeedReportType.

    handler() is called once per valid received sample by the reader thread.
    """

    def __init__(self, participant):
        ddsEntities.Reader.__init__(
            self,
            participant,
            SpeedReportType,
            SpeedReportTypeTopic)

    def handler(self, data: SpeedReportType):
        ts       = data.timeStamp
        mode_str = data.mode.name if data.mode is not None else 'N/A'
        sog = f'{data.speedOverGround:.3f} m/s'    if data.speedOverGround   is not None else '---'
        stw = f'{data.speedThroughWater:.3f} m/s'  if data.speedThroughWater is not None else '---'
        sta = f'{data.speedThroughAir:.3f} m/s'    if data.speedThroughAir   is not None else '---'

        print(
            f'[HSMST][Speed ] t={_fmt_ts(ts)}'
            f'  SOG={sog:>14}  STW={stw:>14}  STA={sta:>14}'
            f'  Mode={mode_str}',
            flush=True)
        logging.info('SpeedReport rx  SOG=%s  STW=%s  Mode=%s', sog, stw, mode_str)


# ===========================================================================
# GlobalPoseStatus — Reader
# ===========================================================================

class GlobalPoseReport_Rdr(ddsEntities.Reader):
    """
    WaitSet-based reader for UMAA::SA::GlobalPoseStatus::GlobalPoseReportType.

    handler() is called once per valid received sample by the reader thread.
    """

    def __init__(self, participant):
        ddsEntities.Reader.__init__(
            self,
            participant,
            GlobalPoseReportType,
            GlobalPoseReportTypeTopic)

    def handler(self, data: GlobalPoseReportType):
        ts        = data.timeStamp
        att       = data.attitude
        roll_deg  = math.degrees(att.roll.roll)
        pitch_deg = math.degrees(att.pitch.pitch)
        yaw_deg   = math.degrees(att.yaw.yaw) % 360
        alt_str   = f'{data.altitude:.2f}m' if data.altitude is not None else '---'

        print(
            f'[HSMST][Pose  ] t={_fmt_ts(ts)}'
            f'  Lat={data.position.geodeticLatitude:+.6f}°'
            f'  Lon={data.position.geodeticLongitude:+.7f}°'
            f'  Alt={alt_str:>8}'
            f'  Course={math.degrees(data.course):.1f}°TN'
            f'  Roll={roll_deg:+.2f}°'
            f'  Pitch={pitch_deg:+.2f}°'
            f'  Yaw={yaw_deg:.1f}°'
            f'  Nav={data.navigationSolution.name}',
            flush=True)
        logging.info('GlobalPose rx  Lat=%.6f  Lon=%.7f',
                     data.position.geodeticLatitude,
                     data.position.geodeticLongitude)


# ===========================================================================
# SpeedMultiplierCommand  —  Reader (used by VectorNav_Publisher)
#                            Writer (used by VectorNav_Dashboard)
# ===========================================================================

class SpeedCommand_Rdr(ddsEntities.Reader):
    """Receives speed multiplier commands from the Dashboard slider.

    handler() updates vn_state.speed_knots so that the next
    write() call from SpeedReport_Wtr / GlobalPoseReport_Wtr picks
    up the new value immediately.
    """

    def __init__(self, participant, vn_state: VectorNavState) -> None:
        ddsEntities.Reader.__init__(
            self,
            participant,
            SpeedCommand,
            vn_constants.SPEED_COMMAND_TOPIC)
        self._vn_state = vn_state

    def handler(self, data: SpeedCommand) -> None:
        knots = max(float(vn_constants.SPEED_KNOTS_MIN),
                    min(float(vn_constants.SPEED_KNOTS_MAX), data.knots))
        self._vn_state.set_speed(knots)
        print(f'[VN] Speed → {knots:.0f} kt  ({knots * 0.5144:.2f} m/s)', flush=True)
        logging.info('SpeedCommand rx  knots=%.1f', knots)


# ===========================================================================
# OrbitCommand  —  Reader (used by VectorNav_Publisher)
#                  Writer (used by VectorNav_Dashboard orbit button)
# ===========================================================================

class OrbitCommand_Rdr(ddsEntities.Reader):
    """Receives orbit enable/disable commands from the Dashboard orbit button.

    handler() calls vn_state.set_orbit() to immediately start or stop the
    clockwise orbit pattern.
    """

    def __init__(self, participant, vn_state: VectorNavState) -> None:
        ddsEntities.Reader.__init__(
            self,
            participant,
            OrbitCommand,
            vn_constants.ORBIT_COMMAND_TOPIC)
        self._vn_state = vn_state

    def handler(self, data: OrbitCommand) -> None:
        self._vn_state.set_orbit(bool(data.enabled))
        logging.info('OrbitCommand rx  enabled=%s', data.enabled)

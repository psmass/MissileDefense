"""
vn_constants.py — VectorNav / HSMST application constants
===========================================================
Mirrors the role of pyCompiledTypes/constants.py in the TMS example.

Contains only application-level constants (not data-model types).
Data-model types and topic-name strings live in umaa_types.py,
which is the equivalent of tmsConstants.py.
"""

# ---------------------------------------------------------------------------
# DDS domain
# ---------------------------------------------------------------------------

DOMAIN_ID: int = 0

# ---------------------------------------------------------------------------
# Publisher timing
# ---------------------------------------------------------------------------

PUBLISH_RATE_HZ: float = 1.0   # samples per second written by VectorNav writers

# ---------------------------------------------------------------------------
# VectorNav source identity
# Fixed GUID string for the VectorNav participant's IdentifierType.
# Use a real uuid4 hex string in production deployments.
# ---------------------------------------------------------------------------

VECNAV_GUID: str = "AA010000-0000-0000-0000-000000000000"

# ---------------------------------------------------------------------------
# UMAA SA topic name strings
# Duplicated here from umaa_types so that main apps can print them without
# importing the full UMAA type library.
# These MUST match the IDL const string values in SpeedReportType.idl /
# GlobalPoseReportType.idl exactly.
# ---------------------------------------------------------------------------

SPEED_TOPIC: str = "UMAA::SA::SpeedStatus::SpeedReportType"
POSE_TOPIC:  str = "UMAA::SA::GlobalPoseStatus::GlobalPoseReportType"

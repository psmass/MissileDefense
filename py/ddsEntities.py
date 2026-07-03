"""
 * (c) Copyright, Real-Time Innovations, 2022.  All rights reserved.
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the software solely for use with RTI Connext DDS. Licensee may
 * redistribute copies of the software provided that all such copies are subject
 * to this license. The software is provided "as is", with no warranty of any
 * type, including any warranty for fitness for any purpose. RTI is under no
 * obligation to maintain or support the software. RTI shall not be liable for
 * any incidental or consequential damages arising out of the use or inability
 * to use the software.

ddsEntities.py — Unified DDS infrastructure base classes
=========================================================
Single module used by ALL applications in this project:
  Ship defense apps  : sensor.py, effector.py, command_control.py
  VectorNav apps     : VectorNav_Publisher.py, HSMST_Subscriber.py,
                       VectorNav_Dashboard.py (via vn_topics.py)

Provides:
  register_ship_types()   – registers Ship IDL types with the DDS runtime
                            (ship apps only; safe to import but not call
                            in VectorNav context)
  DefaultWriterListener   – logs publication-matched events
  Writer (Thread)         – WaitSet-driven periodic DataWriter thread
  Reader (Thread)         – WaitSet-driven DataReader thread

Both calling conventions are supported via argument-type detection:

  Ship style  — caller creates Publisher / Subscriber / Topic externally:
    Writer(publisher:dds.Publisher,   topic:dds.Topic, type_class,
           periodic=False, period=1.0)
    Reader(subscriber:dds.Subscriber, topic:dds.Topic, type_class)

  VectorNav style — Writer / Reader create their own DDS entities internally:
    Writer(participant:dds.DomainParticipant, periodic:bool, period:float,
           type_class, topic_name:str)
    Reader(participant:dds.DomainParticipant, type_class, topic_name:str)

Detection rule:
  Writer – second arg is bool   → VectorNav style
           second arg is Topic  → Ship style
  Reader – second arg is Topic  → Ship style
           otherwise            → VectorNav style

GENERALLY, CODE IN THIS FILE SHOULD NOT BE MODIFIED.
Topic-specific logic belongs in ship_topics.py / vn_topics.py.
"""

from __future__ import annotations

import logging
from threading import Thread
from typing import Any

import application
import shipConstants
import rti.connextdds as dds


# ---------------------------------------------------------------------------
# Type registration  (ship defense apps only)
# ---------------------------------------------------------------------------

def register_ship_types() -> None:
    """Register all ship compiled IDL types with the DDS runtime.

    Must be called before creating the DomainParticipant in ship apps.
    Not required by VectorNav apps.
    """
    dds.DomainParticipant.register_idl_type(
        shipConstants.Threat,          "ship::Threat")
    dds.DomainParticipant.register_idl_type(
        shipConstants.SensorDetection, "ship::SensorDetection")
    dds.DomainParticipant.register_idl_type(
        shipConstants.EffectorAction,  "ship::EffectorAction")


# ---------------------------------------------------------------------------
# Writer listener
# ---------------------------------------------------------------------------

class DefaultWriterListener(dds.NoOpDataWriterListener):
    """Logs publication-matched events for any DataWriter."""

    def on_publication_matched(
        self,
        writer: dds.DataWriter,
        status: dds.PublicationMatchedStatus,
    ) -> None:
        logging.info("%s  on_publication_matched  subs: current=%d  change=%d",
                     writer.topic_name,
                     status.current_count,
                     status.current_count_change)


# ---------------------------------------------------------------------------
# Writer base class
# ---------------------------------------------------------------------------

class Writer(Thread):
    """Generic periodic DataWriter thread.

    Supports two calling conventions (detected automatically):

    Ship style — caller supplies a pre-created Publisher and Topic:
        Writer(publisher, topic, topic_type_class,
               periodic=False, period=1.0)

    VectorNav style — Writer creates Publisher and Topic internally:
        Writer(participant, periodic, period,
               topic_type_class, topic_name)

    Subclass overrides:
        write()   – update dynamic sample fields, then write the sample.
        handler() – set static sample fields once (called from concrete
                    __init__, not from run()).
    """

    def __init__(
        self,
        pub_or_part,
        topic_or_periodic,
        type_class_or_period,
        periodic_or_type=None,
        period_or_name=None,
    ) -> None:
        super().__init__(daemon=True)

        if isinstance(topic_or_periodic, bool):
            # ── VectorNav style ──────────────────────────────────────────
            # (participant, periodic:bool, period:float, type_class, topic_name)
            participant      = pub_or_part
            periodic         = topic_or_periodic
            period           = float(type_class_or_period)
            topic_type_class = periodic_or_type
            topic_name       = period_or_name
            _topic           = dds.Topic(participant, topic_name, topic_type_class)
            self._writer     = dds.DataWriter(dds.Publisher(participant), _topic)
        else:
            # ── Ship style ────────────────────────────────────────────────
            # (publisher, topic:dds.Topic, type_class, periodic=False, period=1.0)
            publisher        = pub_or_part
            _topic           = topic_or_periodic
            topic_type_class = type_class_or_period
            periodic         = bool(periodic_or_type) if periodic_or_type is not None else False
            period           = float(period_or_name)  if period_or_name   is not None else 1.0
            self._writer     = dds.DataWriter(publisher, _topic)

        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__
        self._topic_name       = _topic.name
        self._periodic         = periodic
        self._period           = period
        self._sample: Any      = topic_type_class()

        self._status_condition = dds.StatusCondition(self._writer)
        self._status_condition.enabled_statuses = dds.StatusMask.PUBLICATION_MATCHED
        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition
        self._wait_duration = dds.Duration(
            seconds=int(self._period),
            nanoseconds=int((self._period % 1) * 1_000_000_000))

        logging.info("Writer created  topic=%s  type=%s",
                     self._topic_name, self._topic_type_name)

    def run(self) -> None:
        logging.info("Writer thread started  topic=%s", self._topic_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)
            if self._status_condition in conditions:
                st = self._writer.publication_matched_status
                if dds.StatusMask.PUBLICATION_MATCHED in self._writer.status_changes:
                    logging.info("%s  subscribers: current=%d  change=%d",
                                 self._topic_type_name,
                                 st.current_count,
                                 st.current_count_change)
            elif self._periodic:
                self.write()
        logging.info("Writer thread exiting  topic=%s", self._topic_name)

    def write(self) -> None:
        """Write the current sample.  Override to update dynamic fields first."""
        logging.info("Writing (default)  topic=%s", self._topic_type_name)
        self._writer.write(self._sample)

    def handler(self) -> None:
        """One-time static field init hook — override in concrete subclass."""
        logging.warning("DEFAULT WRITER HANDLER NOT OVERRIDDEN  topic=%s",
                        self._topic_name)

    @property
    def writer(self) -> dds.DataWriter:
        """Direct access to the underlying dds.DataWriter."""
        return self._writer


# ---------------------------------------------------------------------------
# Reader base class
# ---------------------------------------------------------------------------

class Reader(Thread):
    """Generic DataReader thread using a WaitSet + ReadCondition.

    Supports two calling conventions (detected automatically):

    Ship style — caller supplies a pre-created Subscriber and Topic:
        Reader(subscriber, topic, topic_type_class)

    VectorNav style — Reader creates Subscriber and Topic internally:
        Reader(participant, topic_type_class, topic_name)

    Subclass override:
        handler(data) – process one received typed sample.
                        MUST be overridden in the concrete subclass.
    """

    def __init__(
        self,
        sub_or_part,
        topic_or_type,
        type_class_or_name,
    ) -> None:
        super().__init__(daemon=True)

        if isinstance(topic_or_type, dds.Topic):
            # ── Ship style ───────────────────────────────────────────────
            # (subscriber, topic:dds.Topic, type_class)
            subscriber       = sub_or_part
            _topic           = topic_or_type
            topic_type_class = type_class_or_name
            self._reader     = dds.DataReader(subscriber, _topic)
        else:
            # ── VectorNav style ──────────────────────────────────────────
            # (participant, type_class, topic_name:str)
            participant      = sub_or_part
            topic_type_class = topic_or_type
            topic_name       = type_class_or_name
            _topic           = dds.Topic(participant, topic_name, topic_type_class)
            self._reader     = dds.DataReader(dds.Subscriber(participant), _topic)

        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__
        self._topic_name       = _topic.name

        self._read_condition = dds.ReadCondition(
            self._reader, dds.DataState.any_data)
        self._status_condition = dds.StatusCondition(self._reader)
        self._status_condition.enabled_statuses = dds.StatusMask.SUBSCRIPTION_MATCHED

        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition
        self._waitset += self._read_condition
        self._wait_duration = dds.Duration(seconds=4)

        logging.info("Reader created  topic=%s  type=%s",
                     self._topic_name, self._topic_type_name)

    def run(self) -> None:
        logging.info("Reader thread started  topic=%s", self._topic_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)
            if self._status_condition in conditions:
                st = self._reader.subscription_matched_status
                if dds.StatusMask.SUBSCRIPTION_MATCHED in self._reader.status_changes:
                    logging.info("%s  publishers: current=%d  change=%d",
                                 self._topic_type_name,
                                 st.current_count,
                                 st.current_count_change)
            if self._read_condition in conditions:
                for data, info in self._reader.take():
                    if info.valid:
                        self.handler(data)
        logging.info("Reader thread exiting  topic=%s", self._topic_name)

    def handler(self, data: Any) -> None:
        """Process one received typed sample.  MUST be overridden."""
        logging.warning("DEFAULT READER HANDLER NOT OVERRIDDEN  topic=%s",
                        self._topic_name)
        logging.info(data)

    @property
    def reader(self) -> dds.DataReader:
        """Direct access to the underlying dds.DataReader."""
        return self._reader

    def get_reader_handle(self) -> dds.DataReader:
        """Alias for .reader — kept for VectorNav backward compatibility."""
        return self._reader

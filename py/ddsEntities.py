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

 Ship Threat Defense – DDS infrastructure base classes.

 This module provides:
   - register_ship_types()  – registers compiled IDL types with the DDS runtime
   - DefaultWriterListener  – logs publication-matched events
   - Writer (Thread)        – base writer with WaitSet-driven periodic write loop
   - Reader (Thread)        – base reader with WaitSet-driven receive loop

 The Writer and Reader classes use the raw RTI Connext DDS Python API
 (dds.Publisher / dds.Subscriber / dds.Topic) rather than XML App Creation,
 because the C++ source apps also use the raw DDS API with default QoS.

 GENERALLY, CODE IN THIS FILE SHOULD NOT BE MODIFIED.
 User (topic-specific) code belongs in ship_topics.py, which inherits these
 base classes and overrides handler() with application business logic.

 Validated with RTI Connext Python API mypy checker (2026-07-02).
"""

from __future__ import annotations

from threading import Thread
from typing import Any
import logging

import application
import shipConstants
import rti.connextdds as dds


# ---------------------------------------------------------------------------
# Type registration helper
# ---------------------------------------------------------------------------

def register_ship_types() -> None:
    """Register all ship compiled types with the DDS runtime.

    Mirrors ddsEntities.register_tms_types() in the TMS app.

    For XML App Creation this must be called BEFORE
    qos_provider.create_participant_from_config().  For raw-API usage (no XML)
    registration is optional but kept here for consistency with the TMS
    pattern so these apps can be switched to XML App Creation if required.
    """
    dds.DomainParticipant.register_idl_type(
        shipConstants.Threat, "ship::Threat")
    dds.DomainParticipant.register_idl_type(
        shipConstants.SensorDetection, "ship::SensorDetection")
    dds.DomainParticipant.register_idl_type(
        shipConstants.EffectorAction, "ship::EffectorAction")


# ---------------------------------------------------------------------------
# Writer listener
# ---------------------------------------------------------------------------

class DefaultWriterListener(dds.NoOpDataWriterListener):
    """Logs publication-matched events.  Identical to ddsEntities version."""

    def on_publication_matched(
        self,
        writer: dds.DataWriter,
        status: dds.PublicationMatchedStatus,
    ) -> None:
        logging.info("%s Listener Callback On Publication Match", writer.topic_name)
        logging.info(
            "%s Writer Subs: %d %d",
            writer.topic_name,
            status.current_count,
            status.current_count_change,
        )


# ---------------------------------------------------------------------------
# Writer base class
# ---------------------------------------------------------------------------

class Writer(Thread):
    """Base writer thread (raw DDS API version).

    Mirrors ddsEntities.Writer but receives a dds.Publisher + dds.Topic
    instead of looking them up via participant.find_datawriter().

    Parameters
    ----------
    publisher        : dds.Publisher        – created by the calling app
    topic            : dds.Topic            – created by the calling app
    topic_type_class : type                 – compiled @idl.struct class
    periodic         : bool                 – True → write on a timer
    period           : float                – seconds between writes
    """

    def __init__(
        self,
        publisher: dds.Publisher,
        topic: dds.Topic,
        topic_type_class: type,
        periodic: bool = False,
        period: float = 1.0,
    ) -> None:
        super().__init__(daemon=True)
        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__
        self._periodic         = periodic
        self._period           = period

        # Instantiate a typed sample using the compiled type class
        self._sample: Any = topic_type_class()

        # Create the DataWriter against the supplied publisher/topic
        self._writer = dds.DataWriter(publisher, topic)

        self._status_condition = dds.StatusCondition(self._writer)
        self._status_condition.enabled_statuses = dds.StatusMask.PUBLICATION_MATCHED
        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition
        self._wait_duration = dds.Duration(
            seconds=int(self._period),
            nanoseconds=int((self._period % 1) * 1_000_000_000),
        )
        logging.info("Writer created for type %s", self._topic_type_name)

    def run(self) -> None:
        """Thread of execution – mirrors ddsEntities.Writer.run()."""
        logging.info("Writer Thread running for %s", self._topic_type_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)
            if self._status_condition in conditions:
                st = self._writer.publication_matched_status
                if dds.StatusMask.PUBLICATION_MATCHED in self._writer.status_changes:
                    logging.info(
                        "%s Writer Subs: %d %d",
                        self._topic_type_name,
                        st.current_count,
                        st.current_count_change,
                    )
            elif self._periodic:
                self.write()

    # Override in concrete topic class to set topic-specific fields
    def write(self) -> None:
        logging.info("Writing (Default Writer) - %s", self._topic_type_name)
        self._writer.write(self._sample)

    @property
    def writer(self) -> dds.DataWriter:
        return self._writer

    def handler(self) -> None:
        logging.info(
            "DEFAULT WRITER HANDLER FOR %s NOT SET – OVERRIDE TO SET STATIC TOPIC VALUES",
            self._topic_type_name,
        )


# ---------------------------------------------------------------------------
# Reader base class
# ---------------------------------------------------------------------------

class Reader(Thread):
    """Base reader thread (raw DDS API version).

    Mirrors ddsEntities.Reader but receives a dds.Subscriber + dds.Topic
    instead of looking them up via participant.find_datareader().

    Parameters
    ----------
    subscriber       : dds.Subscriber       – created by the calling app
    topic            : dds.Topic            – created by the calling app
    topic_type_class : type                 – compiled @idl.struct class
    """

    def __init__(
        self,
        subscriber: dds.Subscriber,
        topic: dds.Topic,
        topic_type_class: type,
    ) -> None:
        super().__init__(daemon=True)
        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__

        # Create the DataReader against the supplied subscriber/topic
        self._reader = dds.DataReader(subscriber, topic)

        # ReadCondition fires on any new data
        self._read_condition = dds.ReadCondition(
            self._reader, dds.DataState.any_data)

        self._status_condition = dds.StatusCondition(self._reader)
        self._status_condition.enabled_statuses = dds.StatusMask.SUBSCRIPTION_MATCHED

        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition
        self._waitset += self._read_condition
        self._wait_duration = dds.Duration(seconds=4)   # 4-second receive timeout
        logging.info("Reader created for type %s", self._topic_type_name)

    def run(self) -> None:
        """Thread of execution – mirrors ddsEntities.Reader.run()."""
        logging.info("Reader Thread running for %s", self._topic_type_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)
            if self._status_condition in conditions:
                st = self._reader.subscription_matched_status
                if dds.StatusMask.SUBSCRIPTION_MATCHED in self._reader.status_changes:
                    logging.info(
                        "%s Reader Pubs: %d %d",
                        self._topic_type_name,
                        st.current_count,
                        st.current_count_change,
                    )
            if self._read_condition in conditions:
                for data, info in self._reader.take():
                    if info.valid:
                        self.handler(data)

    # *** MUST OVERRIDE IN CONCRETE TOPIC CLASS TO HANDLE RECEIVED SAMPLES ***
    def handler(self, data: Any) -> None:
        logging.info(
            "DEFAULT READER HANDLER FOR %s – OVERRIDE TO READ SPECIFIC TOPIC VALUES",
            self._topic_type_name,
        )
        logging.info(data)

    @property
    def reader(self) -> dds.DataReader:
        return self._reader

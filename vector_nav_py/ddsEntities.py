"""
ddsEntities.py — Generic DDS infrastructure for VectorNav / HSMST
===================================================================
Adapted from pyCompiledTypes/ddsEntities.py (TMS compiled-types version).

Key differences from the TMS version:
  - No XML Application Creation — DDS entities (Topic, Publisher, DataWriter,
    Subscriber, DataReader) are created directly from the DomainParticipant.
  - No TMS-specific imports (no tmsConstants, constants).
  - Writer accepts ``topic_name`` (DDS topic string) instead of
    ``writer_name`` (XML entity path).
  - Reader accepts ``topic_name`` instead of ``reader_name``.
  - No register_tms_types() — typed Topics are created directly using the
    compiled @idl.struct class; no XML <register_type> binding required.

GENERALLY, CODE IN THIS FILE SHOULD NOT BE MODIFIED.
It provides the generic DDS thread infrastructure.

User topic classes in vn_topics.py inherit Writer or Reader and override
  - Writer: write() to update dynamic fields and write the sample
  - Reader: handler(data) to process received typed samples
"""

import logging
from threading import Thread

import application
import rti.connextdds as dds


# ---------------------------------------------------------------------------
# Writer listener
# ---------------------------------------------------------------------------

class DefaultWriterListener(dds.NoOpDataWriterListener):
    """Logs publication-match events for any DataWriter."""

    def on_publication_matched(self, writer, status):
        logging.info('%s  on_publication_matched', writer.topic_name)
        logging.info('%s  Writer subscribers: current=%d  change=%d',
                     writer.topic_name,
                     status.current_count,
                     status.current_count_change)


# ---------------------------------------------------------------------------
# Writer base class
# ---------------------------------------------------------------------------

class Writer(Thread):
    """
    Generic periodic DataWriter thread.

    Parameters
    ----------
    participant      : dds.DomainParticipant
    periodic         : bool   – True  → write on timer; False → write on
                                         explicit call only
    period           : float  – seconds between writes (only used when
                                periodic=True)
    topic_type_class : type   – compiled @idl.struct class for the topic
                                (e.g. SpeedReportType)
    topic_name       : str    – DDS topic name string
                                (e.g. "UMAA::SA::SpeedStatus::SpeedReportType")

    Subclass usage
    --------------
    Override write() to update dynamic sample fields before calling
    self._writer.write(self._sample).

    Override handler() to perform one-time static field initialisation
    (called by the concrete __init__, not by run()).
    """

    def __init__(self, participant, periodic, period, topic_type_class, topic_name):
        Thread.__init__(self)
        self._topic_name       = topic_name
        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__
        self._periodic         = periodic
        self._period           = period

        # Pre-allocated typed sample — concrete class sets static fields
        self._sample = topic_type_class()

        # Create DDS entities directly (no XML App Creation)
        topic          = dds.Topic(participant, topic_name, topic_type_class)
        self._writer   = dds.DataWriter(dds.Publisher(participant), topic)

        # WaitSet fires on PUBLICATION_MATCHED or times out for periodic writes
        self._status_condition = dds.StatusCondition(self._writer)
        self._status_condition.enabled_statuses = dds.StatusMask.PUBLICATION_MATCHED

        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition

        # Wait duration = write period for periodic writers; 4 s for manual writers
        if periodic and period > 0:
            secs  = int(period)
            nanos = int((period % 1) * 1_000_000_000)
        else:
            secs, nanos = 4, 0
        self._wait_duration = dds.Duration(seconds=secs, nanoseconds=nanos)

        logging.info('Writer created  topic=%s', self._topic_name)

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self):
        """Thread body: WaitSet loop driving periodic writes."""
        logging.info('Writer thread started  topic=%s', self._topic_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)

            if self._status_condition in conditions:
                # Publication-matched status change
                st = self._writer.publication_matched_status
                if dds.StatusMask.PUBLICATION_MATCHED in self._writer.status_changes:
                    logging.info('%s  subscribers: current=%d  change=%d',
                                 self._topic_type_name,
                                 st.current_count,
                                 st.current_count_change)
            elif self._periodic:
                # Timeout with no active condition → time to write
                self.write()

        logging.info('Writer thread exiting  topic=%s', self._topic_name)

    # ------------------------------------------------------------------
    # Overridable methods
    # ------------------------------------------------------------------

    def write(self):
        """Write the current sample.  Override to update dynamic fields first."""
        logging.info('Writing (default)  topic=%s', self._topic_type_name)
        self._writer.write(self._sample)

    def handler(self):
        """One-time static field initialisation hook.
        Override to set fields that never change (e.g. source ID, mode enum).
        Called from the concrete subclass __init__, not from run().
        """
        logging.warning('DEFAULT WRITER HANDLER NOT OVERRIDDEN  topic=%s',
                        self._topic_name)

    # ------------------------------------------------------------------
    # Properties / helpers
    # ------------------------------------------------------------------

    @property
    def writer(self):
        """Direct access to the underlying dds.DataWriter."""
        return self._writer


# ---------------------------------------------------------------------------
# Reader base class
# ---------------------------------------------------------------------------

class Reader(Thread):
    """
    Generic DataReader thread using a WaitSet + ReadCondition.

    Parameters
    ----------
    participant      : dds.DomainParticipant
    topic_type_class : type  – compiled @idl.struct class for the topic
    topic_name       : str   – DDS topic name string

    Subclass usage
    --------------
    Override handler(data) to process each received typed sample.
    ``data`` is a fully-typed Python instance of topic_type_class.
    """

    def __init__(self, participant, topic_type_class, topic_name):
        Thread.__init__(self)
        self._participant      = participant   # kept for subclass use
        self._topic_name       = topic_name
        self._topic_type_class = topic_type_class
        self._topic_type_name  = topic_type_class.__name__

        # Create DDS entities directly
        topic          = dds.Topic(participant, topic_name, topic_type_class)
        self._reader   = dds.DataReader(dds.Subscriber(participant), topic)

        # ReadCondition: triggers when any new data arrives
        self._read_condition = dds.ReadCondition(
            self._reader, dds.DataState.any_data)

        # StatusCondition: triggers on SUBSCRIPTION_MATCHED
        self._status_condition = dds.StatusCondition(self._reader)
        self._status_condition.enabled_statuses = dds.StatusMask.SUBSCRIPTION_MATCHED

        self._waitset = dds.WaitSet()
        self._waitset += self._status_condition
        self._waitset += self._read_condition

        # 4-second receive timeout (consistent with TMS reader)
        self._wait_duration = dds.Duration(seconds=4)

        logging.info('Reader created  topic=%s', self._topic_name)

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self):
        """Thread body: WaitSet loop dispatching received samples."""
        logging.info('Reader thread started  topic=%s', self._topic_name)
        while application.run_flag:
            conditions = self._waitset.wait(self._wait_duration)

            if self._status_condition in conditions:
                st = self._reader.subscription_matched_status
                if dds.StatusMask.SUBSCRIPTION_MATCHED in self._reader.status_changes:
                    logging.info('%s  publishers: current=%d  change=%d',
                                 self._topic_type_name,
                                 st.current_count,
                                 st.current_count_change)

            if self._read_condition in conditions:
                for sample in self._reader.take():
                    if sample.info.valid:
                        self.handler(sample.data)

        logging.info('Reader thread exiting  topic=%s', self._topic_name)

    # ------------------------------------------------------------------
    # Override in concrete topic class
    # ------------------------------------------------------------------

    def handler(self, data):
        """Process one received typed sample.
        ``data`` is a fully-typed instance of the topic's compiled @idl.struct.
        MUST be overridden in the concrete subclass.
        """
        logging.warning('DEFAULT READER HANDLER NOT OVERRIDDEN  topic=%s',
                        self._topic_name)
        logging.info(data)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_reader_handle(self):
        """Return the underlying dds.DataReader."""
        return self._reader

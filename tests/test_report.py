import logging
from pathlib import Path
from textwrap import dedent

import pytest

from docstub._report import ContextReporter, ReportHandler


class Test_ContextReporter:
    @pytest.mark.parametrize("level", ["debug", "info", "warn", "error"])
    def test_basic(self, level, caplog):
        caplog.set_level(logging.DEBUG)
        logger = logging.getLogger(__name__)
        rep = ContextReporter(logger=logger)

        func = getattr(rep, level)

        func("Message")
        assert len(caplog.records) == 1

        record = caplog.records[0]
        assert record.message == "Message"
        assert record.details is None
        assert not hasattr(record, "src_location")
        assert record.levelname.startswith(level.upper())

    def test_details(self, caplog):
        logger = logging.getLogger(__name__)
        rep = ContextReporter(logger=logger)

        rep.info("Message", details="More\nmultiline details.")
        assert len(caplog.records) == 1

        record = caplog.records[0]
        assert record.message == "Message"
        assert record.details == "More\nmultiline details."
        assert not hasattr(record, "src_location")

    def test_src_location(self, caplog):
        logger = logging.getLogger(__name__)
        rep = ContextReporter(logger=logger, path=Path("foo.py"), line=3)

        rep.info("Message")
        assert len(caplog.records) == 1

        record = caplog.records[0]
        assert record.message == "Message"
        assert record.details is None
        assert record.src_location == "foo.py:3"

    def test_copy_with(self, caplog):
        logger = logging.getLogger(__name__)

        rep = ContextReporter(logger=logger, path=Path("foo.py"), line=3)
        rep_new_path = rep.copy_with(path=Path("bar.py"))
        rep_new_line = rep.copy_with(line=7)
        rep_line_offset = rep.copy_with(line_offset=8)

        rep_new_path.info("Message")
        rep_new_line.info("Message")
        rep_line_offset.info("Message")
        assert len(caplog.records) == 3

        assert caplog.records[0].src_location == "bar.py:3"
        assert caplog.records[1].src_location == "foo.py:7"
        assert caplog.records[2].src_location == "foo.py:11"


@pytest.fixture
def log_record():
    record = logging.LogRecord(
        name="testing",
        level=logging.ERROR,
        pathname=__file__,
        lineno=0,
        msg="The actual log message",
        args=(),
        exc_info=None,
    )
    return record


class Test_ReportHandler:
    def test_format(self, log_record):
        log_record.details = "Multiline\ndetails"
        log_record.src_location = "foo.py:42"
        log_record.log_id = "E321"

        handler = ReportHandler()
        result = handler.format(log_record)

        expected = dedent(
            """
            E321 The actual log message
                Multiline
                details
                foo.py:42
            """
        ).strip()
        assert result == expected

    def test_format_multiple_locations(self, log_record):
        log_record.details = "Some details"
        log_record.src_location = ["foo.py:42", "bar.py", "a/path.py:100"]
        log_record.log_id = "E321"

        handler = ReportHandler()
        result = handler.format(log_record)

        expected = dedent(
            """
            E321 The actual log message (3x)
                Some details
                a/path.py:100
                bar.py
                foo.py:42
            """
        ).strip()
        assert result == expected

    def test_format_details_with_args(self, log_record):
        log_record.details = ("Details with args: %i, %f", 3, 0.5)
        log_record.log_id = "E321"

        handler = ReportHandler()
        result = handler.format(log_record)

        expected = dedent(
            """
            E321 The actual log message
                Details with args: 3, 0.500000
            """
        ).strip()
        assert result == expected

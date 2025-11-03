"""Report errors and information to the user."""

import dataclasses
import logging
from pathlib import Path
from textwrap import indent

import click

from ._cli_help import should_strip_ansi

logger: logging.Logger = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextReporter:
    """Log messages in context of a file path and line number.

    This is basically a custom :class:`logging.LoggingAdapter`.

    Attributes
    ----------
    logger
    path :
        Path to a file for the current context.
    line :
        The line in the given file.

    Examples
    --------
    Setup logging for doctest, note the use of :cls:`ErrorHandler`

    >>> import sys
    >>> import logging
    >>> logger = logging.getLogger(__name__)
    >>> logger.setLevel(logging.INFO)
    >>> logger.addHandler(ReportHandler(sys.stdout))

    >>> rep = ContextReporter(logger=logger)
    >>> rep.info("Message")
    I Message

    >>> rep = rep.copy_with(path=Path("file/with/problems.py"))
    >>> rep.copy_with(line=3).error("Message with line info")
    E Message with line info
        file...problems.py:3

    >>> rep.copy_with(line=4).warn("With details", details="More details")
    W With details
        More details
        file...problems.py:4
    """

    logger: logging.Logger
    path: Path | None = None
    line: int | None = None

    def copy_with(self, *, logger=None, path=None, line=None, line_offset=None):
        """Return a new copy with the modified attributes.

        Parameters
        ----------
        logger : logging.Logger
        path : Path, optional
        line : int, optional
        line_offset : int, optional

        Returns
        -------
        new : Self
        """
        kwargs = dataclasses.asdict(self)
        if logger:
            kwargs["logger"] = logger
        if path:
            kwargs["path"] = path
        if line:
            kwargs["line"] = line
        if line_offset:
            kwargs["line"] += line_offset
        new = type(self)(**kwargs)
        return new

    def report(self, short, *args, log_level, details=None, **log_kw):
        """Log a report in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        log_level : int
            The logging level.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        extra = {"details": details}

        if self.path is not None:
            location = self.path
            if self.line is not None:
                location = f"{location}:{self.line}"
            extra["src_location"] = location

        self.logger.log(log_level, short, *args, extra=extra, **log_kw)

    def debug(self, short, *args, details=None, **log_kw):
        """Log information with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        return self.report(
            short, *args, log_level=logging.DEBUG, details=details, **log_kw
        )

    def info(self, short, *args, details=None, **log_kw):
        """Log information with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        return self.report(
            short, *args, log_level=logging.INFO, details=details, **log_kw
        )

    def warn(self, short, *args, details=None, **log_kw):
        """Log a warning with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        return self.report(
            short, *args, log_level=logging.WARNING, details=details, **log_kw
        )

    def error(self, short, *args, details=None, **log_kw):
        """Log an error with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        return self.report(
            short, *args, log_level=logging.ERROR, details=details, **log_kw
        )

    def critical(self, short, *args, details=None, **log_kw):
        """Log a critical error with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        *args : Any
            Optional formatting arguments for `short`.
        details : str, optional
            An optional multiline report with more details.
        **log_kw : Any
        """
        return self.report(
            short, *args, log_level=logging.CRITICAL, details=details, **log_kw
        )

    def __post_init__(self):
        if self.path is not None and not isinstance(self.path, Path):
            msg = f"expected `path` to be of type `Path`, got {type(self.path)!r}"
            raise TypeError(msg)

    @staticmethod
    def underline(line, *, char="^"):
        """Underline `line` with the given `char`.

        Parameters
        ----------
        line : str
        char : str

        Returns
        -------
        underlined : str
        """
        assert len(char) == 1
        underlined = f"{line}\n{click.style(char * len(line), fg='red', bold=True)}"
        return underlined


class ReportHandler(logging.StreamHandler):
    """Custom handler to group and style reports from :cls:`ContextReporter`.

    Attributes
    ----------
    group_errors : bool
        If ``True``, hold errors until :func:`emit_grouped` is called.
    error_count : int
    warning_count : int
    level_to_color : ClassVar[dict[int, str]]
    """

    level_to_color = {
        logging.DEBUG: "bright_black",
        logging.INFO: "cyan",
        logging.WARNING: "yellow",
        logging.ERROR: "red",
        logging.CRITICAL: "red",
        logging.FATAL: "red",
    }

    def __init__(self, stream=None, group_errors=False):
        """
        Parameters
        ----------
        stream : TextIO
        group_errors : bool, optional
        """
        super().__init__(stream=stream)
        self.group_errors = group_errors
        self._records = []

        self.strip_ansi = should_strip_ansi(self.stream)

    def format(self, record):
        """Format a log record.

        Parameters
        ----------
        record : logging.LogRecord

        Returns
        -------
        formatted : str
        """
        msg = super().format(record)

        # Except for INFO level, style message
        if record.levelno >= logging.WARNING:
            msg = click.style(msg, bold=True)
        if record.levelno == logging.DEBUG:
            msg = click.style(msg, fg=self.level_to_color[record.levelno])

        # Prefix with a colored log ID, fallback to first char of level name
        log_id = getattr(record, "log_id", record.levelname[0])
        if log_id:
            log_id = click.style(
                log_id,
                bold=True,
                fg=self.level_to_color.get(record.levelno),
            )
            msg = f"{log_id} {msg}"

        # Normalize `src_location` to `list[str]`
        # (may also be missing or a single `str`)
        src_locations = getattr(record, "src_location", [])
        if not isinstance(src_locations, list):
            src_locations = [src_locations]

        # and append number if multiple locations exist
        if len(src_locations) > 1:
            msg = f"{msg} ({len(src_locations)}x)"

        # Append `details` with indent if present
        details = getattr(record, "details", None)
        if details:
            # Allow same %-based formatting as for general log messages
            if isinstance(details, tuple):
                details = details[0] % details[1:]
            indented = indent(details, prefix="    ").rstrip()
            msg = f"{msg}\n{indented}"

        # Append locations
        for location in sorted(src_locations):
            location_styled = click.style(location, fg="magenta")
            msg = f"{msg}\n    {location_styled}"

        if self.strip_ansi:
            msg = click.unstyle(msg)

        return msg

    def handle(self, record):
        """Handle a log record.

        Parameters
        ----------
        record : logging.LogRecord

        Returns
        -------
        out : bool
        """
        if self.group_errors and logging.WARNING <= record.levelno <= logging.ERROR:
            self._records.append(record)
        else:
            self.emit(record)
        return True

    def emit_grouped(self):
        """Emit all saved log records in groups.

        Saved log records that were not yet emitted will be emitted. Records
        whose "message" including an optional "details" field are identical
        will be grouped together.
        """
        # Group by report
        # TODO use itertools.groupby here?
        groups = {}
        for record in self._records:
            group_id = record.getMessage(), getattr(record, "details", "")
            groups[group_id] = groups.get(group_id, [])
            groups[group_id].append(record)

        # Show largest groups last
        groups_by_size = sorted(groups.values(), key=lambda x: len(x))

        # Emit by group
        for records in groups_by_size:
            merged_record = records[0]
            merged_record.src_location = [
                getattr(r, "src_location", "<unknown location?>") for r in records
            ]
            super().emit(merged_record)

        # Clear now emitted records
        self._records = []


class LogCounter(logging.NullHandler):
    """Logging handler that counts warnings, errors and critical records.

    Attributes
    ----------
    critical_count : int
    error_count : int
    warning_count : int
    """

    def __init__(self):
        super().__init__()
        self.critical_count = 0
        self.error_count = 0
        self.warning_count = 0

    def handle(self, record):
        """Count the log record if is a warning or more severe.

        Parameters
        ----------
        record : logging.LogRecord

        Returns
        -------
        out : bool
        """
        if record.levelno >= logging.CRITICAL:
            self.critical_count += 1
        elif record.levelno >= logging.ERROR:
            self.error_count += 1
        elif record.levelno >= logging.WARNING:
            self.warning_count += 1
        return True


def setup_logging(*, verbosity, group_errors):
    """Setup logging to stderr for docstub's main process.

    Parameters
    ----------
    verbosity : {-2, -1, 0, 1, 2, 3}
    group_errors : bool

    Returns
    -------
    output_handler : ReportHandler
    log_counter : LogCounter
    """
    _VERBOSITY_LEVEL = {
        -2: logging.CRITICAL,
        -1: logging.ERROR,
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
        3: logging.DEBUG,
    }

    output_level = _VERBOSITY_LEVEL[verbosity]
    report_level = min(logging.WARNING, output_level)

    format_ = "%(message)s"
    if verbosity >= 3:
        debug_info = (
            "logger = '%(name)s'",
            "loc    = '%(pathname)s:%(lineno)d'",
            "func   = '%(funcName)s'",
            "proc   = '%(processName)s'",
            "thread = '%(threadName)s'",
            "time   = '%(asctime)s'",
        )
        debug_info = indent(",\n".join(debug_info), prefix="    ")
        format_ = f"{format_}\n  [\n{debug_info}\n  ]"

    reporter = ReportHandler(group_errors=group_errors)
    reporter.setLevel(_VERBOSITY_LEVEL[verbosity])

    log_counter = LogCounter()
    log_counter.setLevel(report_level)

    # Only allow logging by docstub itself
    reporter.addFilter(logging.Filter("docstub"))
    log_counter.addFilter(logging.Filter("docstub"))

    logging.basicConfig(
        format=format_,
        level=report_level,
        handlers=[reporter, log_counter],
    )
    logging.captureWarnings(True)

    return reporter, log_counter

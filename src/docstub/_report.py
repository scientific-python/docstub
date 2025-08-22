"""Report errors and information to the user."""

import dataclasses
import logging
from pathlib import Path
from textwrap import indent

import click

logger = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ContextReporter:
    """Log error messages in context of a location in a file.

    Attributes
    ----------
    path :
        Path to a file for the current context.
    line :
        The line in the given file.
    column :
        The column in the given line.

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
        file/with/problems.py:3

    >>> rep.copy_with(line=4).warn("With details", details="More details")
    W With details
        More details
        file/with/problems.py:4
    """

    logger: logging.Logger
    path: Path | None = None
    line: int | None = None
    column: int | None = None

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

    def report(self, short, *, log_level, details=None, **log_kw):
        """Log a report in context of the saved location.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        log_level : int
            The logging level.
        details : str, optional
            An optional multiline report with more details.
        """
        extra = {"details": details}

        if self.path is not None:
            location = self.path
            if self.line is not None:
                location = f"{location}:{self.line}"
            extra["src_location"] = location

        self.logger.log(log_level, msg=short, extra=extra, **log_kw)

    def info(self, short, *, details=None):
        """Log information with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline report with more details.
        """
        return self.report(short, log_level=logging.INFO, details=details)

    def warn(self, short, *, details=None):
        """Log a warning with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline report with more details.
        """
        return self.report(short, log_level=logging.WARNING, details=details)

    def error(self, short, *, details=None, **log_kw):
        """Log an error with context of the relevant source.

        Parameters
        ----------
        short : str
            A short summarizing report that shouldn't wrap over multiple lines.
        details : str, optional
            An optional multiline report with more details.
        """
        return self.report(short, log_level=logging.ERROR, details=details, **log_kw)

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
    """Custom handler to group and style reports from :cls:`ContextReporter`."""

    char_to_color = {  # noqa: RUF012
        "I": "cyan",
        "E": "red",
        "C": "red",
        "F": "red",
        "D": "white",
        "W": "yellow",
    }

    def __init__(self, stream=None, group_errors=False):
        """
        Parameters
        ----------
        stream : TextIO
        group_errors : bool, optional
        """
        super().__init__(stream=stream)
        self.group_errors = False
        self.group_errors = group_errors
        self._records = []

        # Be defensive about using click's non-public `should_strip_ansi`
        try:
            from click._compat import should_strip_ansi

            self.strip_ansi = should_strip_ansi(self.stream)
        except (SystemExit, KeyboardInterrupt):
            raise
        except:  # noqa: E722
            self.strip_ansi = True
            logger.exception("Unexpected error while using click's `should_strip_ansi`")

    @staticmethod
    def format_location(location):
        """
        Parameters
        ----------
        location : str or tuple of (str, None or str) or None

        Returns
        -------
        formatted : str
        """

    def format(self, record):
        msg = super().format(record)

        if record.levelno >= logging.WARNING:
            msg = click.style(msg, bold=True)
        if record.levelno == logging.DEBUG:
            msg = click.style(msg, fg="white")

        # Add a colored character for the error level
        levelchar = record.levelname[0]
        levelchar = click.style(
            levelchar,
            bold=True,
            fg=self.char_to_color[levelchar],
        )
        msg = f"{levelchar} {msg}"

        src_locations = getattr(record, "src_location", [])
        if not isinstance(src_locations, list):
            src_locations = [src_locations]

        if len(src_locations) > 1:
            msg = f"{msg} ({len(src_locations)}x)"

        details = getattr(record, "details", None)
        if details:
            indented = indent(details, prefix="    ").rstrip()
            msg = f"{msg}\n{indented}"

        for location in sorted(src_locations):
            location_styled = click.style(location, fg="magenta")
            msg = f"{msg}\n    {location_styled}"

        if self.strip_ansi:
            msg = click.unstyle(msg)

        return msg

    def emit(self, record):
        if self.group_errors and logging.WARNING <= record.levelno <= logging.ERROR:
            self._records.append(record)
        else:
            super().emit(record)

    def emit_grouped(self):
        # Group by report
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


def setup_logging(*, verbosity, group_errors):
    """

    Parameters
    ----------
    verbosity : int
    group_errors : bool

    Returns
    -------
    handler : ReportHandler
    """
    _VERBOSITY_LEVEL = {
        -2: logging.CRITICAL + 1,  # never print anything
        -1: logging.ERROR,
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }

    format_ = "%(message)s"
    if verbosity >= 2:
        format_ += (
            "\n    loc:     %(pathname)s:%(lineno)d"
            "\n    func:    %(funcName)s"
            "\n    asctime: %(asctime)s"
            "\n    --"
        )

    formatter = logging.Formatter(format_)
    handler = ReportHandler(group_errors=group_errors)
    handler.setLevel(_VERBOSITY_LEVEL[verbosity])
    handler.setFormatter(formatter)

    # Make sure to filter out
    handler.addFilter(logging.Filter("docstub"))

    logging.basicConfig(
        level=_VERBOSITY_LEVEL[verbosity],
        handlers=[handler],
    )
    return handler

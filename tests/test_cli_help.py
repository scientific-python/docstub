from functools import partial

import click

from docstub._cli_help import HelpFormatter

bold = partial(click.style, bold=True)
bold_red = partial(click.style, bold=True, fg="red")
bold_magenta = partial(click.style, bold=True, fg="magenta")
magenta = partial(click.style, fg="magenta")


class Test_HelpFormatter:
    def test_write_dl_options(self):
        formatter = HelpFormatter()
        formatter.strip_ansi = False
        rows = [
            ("-v, --verbose", "verbose option -vv "),
            ("--out-file PATH", "file to write to. this-should-not-be-colored"),
        ]
        formatter.current_indent = 2
        formatter.write_dl(rows)
        dl = formatter.getvalue()

        assert click.unstyle(dl) == (
            "  -v, --verbose\n"
            "          verbose option -vv\n"
            "      --out-file PATH\n"
            "          file to write to. this-should-not-be-colored\n"
        )
        assert dl == (
            f" {bold_red(' -v')},{bold_magenta(' --verbose')}\n"
            "          verbose option -vv\n"
            f"     {bold_magenta(' --out-file')} {magenta('PATH')}\n"
            "          file to write to. this-should-not-be-colored\n"
        )

    def test_write_dl_commands(self):
        formatter = HelpFormatter()
        formatter.strip_ansi = False
        rows = [
            ("run", "Run something"),
            ("clean-cache", "Remove the cache"),
        ]
        formatter.current_indent = 2
        formatter.write_dl(rows)
        dl = formatter.getvalue()

        assert click.unstyle(dl) == (
            "  run          Run something\n"
            "  clean-cache  Remove the cache\n"
        )  # fmt: skip
        assert dl == (
            f"  {bold_magenta('run')}          Run something\n"
            f"  {bold_magenta('clean-cache')}  Remove the cache\n"
        )

    def test_heading(self):
        formatter = HelpFormatter()
        formatter.strip_ansi = False
        formatter.write_heading("Other options")
        heading = formatter.getvalue()
        assert click.unstyle(heading) == "Other options:\n"
        assert heading == bold("Other options:") + "\n"

    def test_usage(self):
        formatter = HelpFormatter()
        formatter.strip_ansi = False
        formatter.write_usage(
            prog="some command", args="[OPTIONS] COMMAND [ARGS]", prefix="Benutzung: "
        )
        usage = formatter.getvalue()
        assert (
            click.unstyle(usage) == "Benutzung: some command [OPTIONS] COMMAND [ARGS]\n"
        )
        assert usage == (
            f"{bold('Benutzung: ')}"
            f"{bold_magenta('some command')} "
            f"{magenta('[OPTIONS] COMMAND [ARGS]')}\n"
        )

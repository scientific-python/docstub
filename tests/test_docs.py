"""Test documentation in docs/."""

import re
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from docstub import _cli

PROJECT_ROOT = Path(__file__).parent.parent


def test_introduction_example(tmp_path):
    # Load introduction
    md_file = PROJECT_ROOT / "docs/introduction.md"
    with md_file.open("r") as io:
        md_content = io.read()

    # Extract code block for example.py
    regex_py = (
        r"<!--- begin example.py --->"
        r"\n+```{code-block} python(.*)```\n+"
        r"<!--- end example.py --->"
    )
    matches_py = re.findall(regex_py, md_content, flags=re.DOTALL)
    assert len(matches_py) == 1
    py_source = matches_py[0]

    # Create example.py and run docstub on it
    py_file = tmp_path / "example.py"
    with py_file.open("x") as io:
        io.write(py_source)
    runner = CliRunner()
    run_result = runner.invoke(_cli.run, [str(py_file)])  # noqa: F841

    # Load created PYI file, this is what we expect to find in the introduction's
    # code block for example.pyi
    pyi_file = py_file.with_suffix(".pyi")
    assert pyi_file.is_file()
    with pyi_file.open("r") as io:
        expected_pyi = io.read().strip()

    # Extract code block for example.pyi from guide
    regex_pyi = (
        r"<!--- begin example.pyi --->"
        r"\n+```{code-block} python(.*)```\n+"
        r"<!--- end example.pyi --->"
    )
    matches_pyi = re.findall(regex_pyi, md_content, flags=re.DOTALL)
    assert len(matches_pyi) == 1
    actual_pyi = matches_pyi[0].strip()

    assert expected_pyi == actual_pyi


@pytest.mark.parametrize(
    ("command", "name"),
    [(_cli.cli, "docstub"), (_cli.run, "docstub run"), (_cli.clean, "docstub clean")],
)
def test_command_line_reference(command, name):
    ctx = click.Context(command, info_name=name)
    expected_help = f"""
```none
{command.get_help(ctx)}
```
""".strip()
    md_file = PROJECT_ROOT / "docs/command_line.md"
    with md_file.open("r") as io:
        md_content = io.read()

    guard_name = f"cli-{name.replace(' ', '-')}"
    regex = rf"<!--- begin {guard_name} --->(.*)<!--- end {guard_name} --->"
    matches = re.findall(regex, md_content, flags=re.DOTALL)
    assert len(matches) == 1

    actual_help = matches[0].strip()
    assert actual_help == expected_help

"""Test documentation in doc/."""

import re
from pathlib import Path

import click

from docstub._cli import main

PROJECT_ROOT = Path(__file__).parent.parent


def test_command_line_help():
    ctx = click.Context(main, info_name="docstub")
    expected_help = f"""

```plain
{main.get_help(ctx)}
```

"""
    md_file = PROJECT_ROOT / "doc/command_line_reference.md"
    with md_file.open("r") as io:
        md_content = io.read()

    regex = r"<!--- begin command-line-help --->(.*)<!--- end command-line-help --->"
    match = re.findall(regex, md_content, flags=re.DOTALL)
    assert len(match) == 1

    actual_help = match[0]
    assert actual_help == expected_help

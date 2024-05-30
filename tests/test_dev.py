
from pathlib import Path

from docstub._stubs import create_stub
from docstub._docstrings import doc2pytype


def test_type_descriptions(descr):



def test_create_stub():
    path = Path(__file__).parent.parent / "example/example_pkg/__init__.py"
    target = path.parent.parent / "example_pkg-stubs/__init__.pyi"
    with path.open() as file:
        py_source = file.read()
    stub_source = create_stub(py_source)
    with target.open("w") as file:
        file.write(stub_source)

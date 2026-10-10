import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "make_examples", Path(__file__).parents[1] / "examples" / "make_examples.py"
)
make_examples = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_examples)


@pytest.fixture(scope="session")
def examples(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("examples")
    paths = {"svg": d / "logo.svg", "pdf": d / "document.pdf", "photo": d / "handwriting.jpg"}
    make_examples.make_svg(paths["svg"])
    make_examples.make_pdf(paths["pdf"])
    make_examples.make_handwriting_photo(paths["photo"])
    return paths

"""LivingLit: each paper parsed into an audited record (README)."""
from pathlib import Path

def _root() -> Path:
    """The repository: the nearest folder above the package holding pyproject.toml (src layout, 07-building, Files)."""
    for d in Path(__file__).resolve().parents:
        if (d / "pyproject.toml").is_file():
            return d
    return Path.cwd()


import os

ROOT = _root()
PAPERS_DIR = ROOT / "papers_dont_ever_commit"
RECORDS_DIR = ROOT / "records"
FIELDS_DIR = ROOT / "fields"
ONTOLOGY_DIR = ROOT / "ontologies_dont_commit"
RELEASES_DIR = ROOT / "releases"
DEFAULT_FIELD = os.environ.get("LIVINGLIT_FIELD", "lepidoptera")


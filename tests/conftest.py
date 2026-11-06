import pytest

from backend.audit import AuditStore
from backend.config import REGULATIONS_DIR, RULES_DIR
from backend.pipeline import Pipeline, load_rules
from backend.rag import RegulatoryIndex


@pytest.fixture(scope="session")
def rules():
    return load_rules(RULES_DIR)


@pytest.fixture(scope="session")
def rule_by_id(rules):
    return {rule.id: rule for rule in rules}


@pytest.fixture(scope="session")
def index(tmp_path_factory):
    return RegulatoryIndex(tmp_path_factory.mktemp("chroma"), REGULATIONS_DIR)


@pytest.fixture
def audit(tmp_path):
    return AuditStore(tmp_path / "inspections.sqlite3")


@pytest.fixture
def pipeline(rules, index, audit):
    return Pipeline(rules, index, audit)

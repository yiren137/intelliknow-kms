"""Shared fixtures for all tests."""
import json
import os
import pytest
from fastapi.testclient import TestClient

# Ensure project root is on the path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def test_cases():
    path = os.path.join(os.path.dirname(__file__), "test_cases.json")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def hr_doc_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "test_hr_handbook.pdf")


@pytest.fixture(scope="session")
def legal_doc_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "test_legal_compliance.pdf")


@pytest.fixture(scope="session")
def finance_doc_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "test_finance_policies.docx")


@pytest.fixture(scope="session")
def general_doc_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "test_general_handbook.docx")

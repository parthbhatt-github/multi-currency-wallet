import os
import tempfile

import pytest
from fastapi.testclient import TestClient

db_fd, db_path = tempfile.mkstemp()
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["JWT_SECRET"] = "test-secret"

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


def signup(client: TestClient, email: str = "a@example.com", currency: str = "USD") -> str:
    response = client.post(
        "/auth/signup",
        json={
            "email": email,
            "password": "very-secure-password",
            "full_name": "Test User",
            "default_currency": currency,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]

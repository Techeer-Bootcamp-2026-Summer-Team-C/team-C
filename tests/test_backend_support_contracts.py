from datetime import UTC, datetime, timedelta

import boto3
import jwt
import pytest
from botocore.stub import Stubber

from backend.archive_service import BotoRestoreObjectClient
from backend.auth import decode_access_token, hash_password, issue_access_token, verify_password
from backend.contracts.enums import UserRole
from backend.errors import ApplicationError
from backend.storage.postgres import EndpointRepository

NOW = datetime(2026, 7, 12, tzinfo=UTC)
JWT_SECRET = "backend-unit-test-jwt-secret-32-bytes-minimum"


def test_argon2id_and_hs256_claim_contract() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "wrong") is False
    token = issue_access_token(user_id=7, role=UserRole.ADMIN, secret=JWT_SECRET, now=NOW)
    claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert set(claims) == {"sub", "role", "iat", "exp"}
    assert claims["sub"] == "7"
    assert claims["role"] == "ADMIN"
    assert claims["exp"] - claims["iat"] == 3600


def test_expired_and_tampered_jwt_are_rejected() -> None:
    expired = issue_access_token(
        user_id=7,
        role=UserRole.VIEWER,
        secret=JWT_SECRET,
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    with pytest.raises(ApplicationError) as expired_error:
        decode_access_token(expired, secret=JWT_SECRET)
    with pytest.raises(ApplicationError) as tampered_error:
        decode_access_token(expired + "tampered", secret=JWT_SECRET)
    assert expired_error.value.status_code == 401
    assert tampered_error.value.status_code == 401


def test_restore_object_sdk_contract_uses_days_7_standard() -> None:
    client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    with Stubber(client) as stubber:
        stubber.add_response(
            "restore_object",
            {},
            {
                "Bucket": "archive-bucket",
                "Key": "archives/endpoint-1.parquet",
                "RestoreRequest": {"Days": 7, "GlacierJobParameters": {"Tier": "Standard"}},
            },
        )
        BotoRestoreObjectClient(client, bucket="archive-bucket").restore("archives/endpoint-1.parquet")


def test_endpoint_risk_snapshot_uses_one_query_not_endpoint_n_plus_one() -> None:
    class Cursor:
        calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, parameters):
            self.calls += 1

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self, **kwargs):
            return self.cursor_instance

    connection = Connection()
    assert EndpointRepository(connection).risk_snapshot() == []
    assert connection.cursor_instance.calls == 1

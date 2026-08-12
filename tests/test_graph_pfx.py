from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from control import HaltError
from control.transport import GraphTransport

MAILBOX = "control@ubcsis.com"


def _make_pfx(tmp_path, password=b"secret123"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UBCSIS-Control")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(
        b"control", key, cert, None,
        serialization.BestAvailableEncryption(password),
    )
    path = tmp_path / "control-graph.pfx"
    path.write_bytes(pfx)
    expected_thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()
    return path, expected_thumbprint


def test_from_pfx_builds_authenticating_transport(tmp_path):
    path, _thumb = _make_pfx(tmp_path)
    t = GraphTransport.from_pfx(
        MAILBOX, tenant_id="tid", client_id="cid",
        pfx_path=path, pfx_password="secret123",
    )
    assert t.mailbox == MAILBOX
    assert callable(t._token_provider)   # MSAL app constructed, no network yet


def test_from_pfx_wrong_password_halts(tmp_path):
    path, _ = _make_pfx(tmp_path)
    with pytest.raises(HaltError, match="cannot open PFX"):
        GraphTransport.from_pfx(MAILBOX, tenant_id="t", client_id="c",
                                pfx_path=path, pfx_password="wrong")


def test_from_env_reports_missing_variables():
    with pytest.raises(HaltError, match="GRAPH_TENANT_ID"):
        GraphTransport.from_env(environ={})


def test_from_env_complete(tmp_path):
    path, _ = _make_pfx(tmp_path)
    env = {
        "GRAPH_TENANT_ID": "tid", "GRAPH_CLIENT_ID": "cid",
        "CONTROL_MAILBOX": MAILBOX, "GRAPH_PFX_PATH": str(path),
        "GRAPH_PFX_PASSWORD": "secret123",
    }
    t = GraphTransport.from_env(environ=env)
    assert t.mailbox == MAILBOX

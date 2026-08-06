from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cert_service import parse_certificates


def _make_cert_pem(domain: str, issuer_cn: str, days_until_expiry: int) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days_until_expiry))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def test_parse_certificates_extracts_domain_issuer_and_expiry() -> None:
    pem = _make_cert_pem("app.home.arpa", "litethaus internal CA", 30)
    certs = parse_certificates(pem)

    assert len(certs) == 1
    assert certs[0]["domains"] == ["app.home.arpa"]
    assert certs[0]["issuer"] == "litethaus internal CA"
    expires = datetime.fromisoformat(certs[0]["expires_at"])
    assert 29 <= (expires - datetime.now(timezone.utc)).days <= 30


def test_parse_certificates_handles_multiple_concatenated_pem_blocks() -> None:
    combined = _make_cert_pem("a.example.com", "CA", 10) + _make_cert_pem("b.example.com", "CA", 20)
    certs = parse_certificates(combined)
    assert [c["domains"] for c in certs] == [["a.example.com"], ["b.example.com"]]


def test_parse_certificates_skips_unparseable_blocks_without_raising() -> None:
    garbage = b"-----BEGIN CERTIFICATE-----\nnotarealcert\n-----END CERTIFICATE-----\n"
    assert parse_certificates(garbage) == []


def test_parse_certificates_returns_empty_list_for_empty_input() -> None:
    assert parse_certificates(b"") == []


if __name__ == "__main__":
    test_parse_certificates_extracts_domain_issuer_and_expiry()
    test_parse_certificates_handles_multiple_concatenated_pem_blocks()
    test_parse_certificates_skips_unparseable_blocks_without_raising()
    test_parse_certificates_returns_empty_list_for_empty_input()
    print("ok")

import logging
import re
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

_PEM_BLOCK = re.compile(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL)

# Where Caddy's file storage module keeps ACME/internal-CA-issued leaf certs
# inside its container - see caddy/Dockerfile and docker-compose's caddy_data
# volume. Not configurable; it's Caddy's own fixed layout.
CADDY_CERT_DIR = "/data/caddy/certificates"


def parse_certificates(pem_data: bytes) -> list[dict[str, Any]]:
    """Parse one or more concatenated PEM certificates (as returned by `find
    ... -exec cat {} +` inside the Caddy container) into summary dicts. A
    block that fails to parse is logged and skipped rather than raising, so
    one corrupt file doesn't blank out the whole certificate list."""
    results = []
    for block in _PEM_BLOCK.findall(pem_data):
        try:
            cert = x509.load_pem_x509_certificate(block)
        except Exception:
            logger.exception("Failed to parse a certificate block, skipping")
            continue
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            domains = san.value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            domains = []
        issuer_cn = next(
            (attr.value for attr in cert.issuer if attr.oid == NameOID.COMMON_NAME),
            cert.issuer.rfc4514_string(),
        )
        results.append(
            {
                "domains": domains,
                "issuer": issuer_cn,
                "expires_at": cert.not_valid_after_utc.isoformat(),
            }
        )
    return results

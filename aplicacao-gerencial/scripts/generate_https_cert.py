from __future__ import annotations

import ipaddress
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = ROOT / "data" / "certs"
CERT_PATH = CERT_DIR / "negociadores-local.crt"
KEY_PATH = CERT_DIR / "negociadores-local.key"


def collect_ip_addresses() -> list[str]:
    addresses = {"127.0.0.1"}
    extra_ips = os.environ.get("NEGOCIADORES_CERT_IPS", "")
    for value in extra_ips.split(","):
        value = value.strip()
        if value:
            addresses.add(value)
    try:
        hostname = socket.gethostname()
        for value in socket.gethostbyname_ex(hostname)[2]:
            addresses.add(value)
    except OSError:
        pass

    valid_addresses = []
    for value in sorted(addresses):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            continue
        valid_addresses.append(value)
    return valid_addresses


def collect_dns_names() -> list[str]:
    names = {"localhost"}
    hostname = socket.gethostname().strip()
    if hostname:
        names.add(hostname)
        try:
            names.add(socket.getfqdn(hostname))
        except OSError:
            pass
    extra_names = os.environ.get("NEGOCIADORES_CERT_DNS", "")
    names.update(value.strip() for value in extra_names.split(",") if value.strip())
    return sorted(name for name in names if name)


def certificate_matches(addresses: list[str], dns_names: list[str]) -> bool:
    if not CERT_PATH.exists() or not KEY_PATH.exists():
        return False
    try:
        cert = x509.load_pem_x509_certificate(CERT_PATH.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        cert_ips = {str(value) for value in san.get_values_for_type(x509.IPAddress)}
        cert_dns = set(san.get_values_for_type(x509.DNSName))
        return set(addresses).issubset(cert_ips) and set(dns_names).issubset(cert_dns)
    except (ValueError, x509.ExtensionNotFound):
        return False


def main() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ip_addresses = collect_ip_addresses()
    dns_names = collect_dns_names()
    if certificate_matches(ip_addresses, dns_names):
        print(CERT_PATH)
        print(KEY_PATH)
        return

    common_name = next((value for value in ip_addresses if value != "127.0.0.1"), "localhost")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Monitor de Negociadores Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    alternative_names: list[x509.GeneralName] = [x509.DNSName(value) for value in dns_names]
    alternative_names.extend(
        x509.IPAddress(ipaddress.ip_address(value))
        for value in ip_addresses
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(alternative_names),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(CERT_PATH)
    print(KEY_PATH)


if __name__ == "__main__":
    main()

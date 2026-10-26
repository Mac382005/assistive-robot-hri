from __future__ import annotations

import argparse
import ipaddress
import socket
import plistlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_private_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def load_or_create_ca(certs: Path):
    ca_key_path = certs / "hri_local_ca_key.pem"
    ca_pem_path = certs / "hri_local_ca.pem"
    ca_crt_path = certs / "hri_local_ca.crt"

    if ca_key_path.exists() and ca_pem_path.exists():
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(ca_pem_path.read_bytes())
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HRI Robot Development"),
                x509.NameAttribute(NameOID.COMMON_NAME, "HRI Robot Local CA"),
            ]
        )
        now = utcnow()
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        write_private_key(ca_key_path, ca_key)
        ca_pem_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    # DER is convenient for installation on iPad/iPhone.
    ca_der = ca_cert.public_bytes(serialization.Encoding.DER)
    ca_crt_path.write_bytes(ca_der)

    # Unsigned local configuration profile: convenient for installing the root CA
    # on a personal iPad. The user still explicitly enables full trust afterward.
    mobileconfig_path = certs / "hri_robot_ca.mobileconfig"
    cert_uuid = str(uuid.uuid4()).upper()
    profile = {
        "PayloadContent": [
            {
                "PayloadCertificateFileName": "hri_local_ca.crt",
                "PayloadContent": ca_der,
                "PayloadDescription": "Trust the local HRI robot HTTPS server.",
                "PayloadDisplayName": "HRI Robot Local CA",
                "PayloadIdentifier": "edu.uc.hri.robot.localca.certificate",
                "PayloadType": "com.apple.security.root",
                "PayloadUUID": cert_uuid,
                "PayloadVersion": 1,
            }
        ],
        "PayloadDisplayName": "HRI Robot Local CA",
        "PayloadDescription": "Local development certificate for the HRI assistive robot tablet interface.",
        "PayloadIdentifier": "edu.uc.hri.robot.localca",
        "PayloadOrganization": "HRI Robot Development",
        "PayloadRemovalDisallowed": False,
        "PayloadType": "Configuration",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
    }
    mobileconfig_path.write_bytes(plistlib.dumps(profile, fmt=plistlib.FMT_XML, sort_keys=False))
    return ca_key, ca_cert, ca_crt_path, mobileconfig_path


def generate_server_cert(certs: Path, host: str, ca_key, ca_cert):
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise SystemExit(f"--host must be an IPv4/IPv6 address, got: {host}") from exc

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    hostname = socket.gethostname().strip() or "hri-robot"
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "HRI Robot Development"),
            x509.NameAttribute(NameOID.COMMON_NAME, str(ip)),
        ]
    )
    now = utcnow()
    san = x509.SubjectAlternativeName(
        [
            x509.IPAddress(ip),
            x509.DNSName("localhost"),
            x509.DNSName(hostname),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(san, critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    key_path = certs / "hri_server_key.pem"
    cert_path = certs / "hri_server.pem"
    write_private_key(key_path, server_key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a local CA and HTTPS certificate for the HRI tablet UI.")
    parser.add_argument("--host", required=True, help="Laptop/Raspberry Pi LAN IP, e.g. 192.168.0.103")
    parser.add_argument("--output", default="certs", help="Certificate output directory")
    args = parser.parse_args()

    certs = Path(args.output).resolve()
    certs.mkdir(parents=True, exist_ok=True)

    ca_key, ca_cert, ca_crt, mobileconfig = load_or_create_ca(certs)
    cert_path, key_path = generate_server_cert(certs, args.host, ca_key, ca_cert)

    print("HRI tablet HTTPS certificate ready.")
    print(f"Host: {args.host}")
    print(f"CA certificate: {ca_crt}")
    print(f"iPad install profile: {mobileconfig}")
    print(f"Server certificate: {cert_path}")
    print(f"Server private key: {key_path}")
    print()
    print("Keep hri_local_ca_key.pem and hri_server_key.pem private. Do not commit certs/ to Git.")


if __name__ == "__main__":
    main()

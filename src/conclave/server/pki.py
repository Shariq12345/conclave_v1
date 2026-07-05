import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

CONCLAVE_DIR = os.path.expanduser("~/.conclave")

def get_or_create_ca():
    """Gets or creates the Root CA key and certificate."""
    os.makedirs(CONCLAVE_DIR, exist_ok=True)
    ca_key_path = os.path.join(CONCLAVE_DIR, "ca_key.pem")
    ca_cert_path = os.path.join(CONCLAVE_DIR, "ca_cert.pem")

    if os.path.exists(ca_key_path) and os.path.exists(ca_cert_path):
        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        return ca_key, ca_cert

    # Generate CA key pair
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    # Generate self-signed CA cert
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Conclave FL Network CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Conclave Root CA"),
    ])
    
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650)) # 10 years
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Save
    with open(ca_key_path, "wb") as f:
        f.write(ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(ca_cert_path, "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

    return ca_key, ca_cert

def get_or_create_server_certs():
    """Gets or creates the server key and certificate for HTTPS."""
    ca_key, ca_cert = get_or_create_ca()
    
    server_key_path = os.path.join(CONCLAVE_DIR, "server_key.pem")
    server_cert_path = os.path.join(CONCLAVE_DIR, "server_cert.pem")

    if os.path.exists(server_key_path) and os.path.exists(server_cert_path):
        return server_key_path, server_cert_path

    # Generate server private key
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Conclave FL Network"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    
    # SAN for localhost & 127.0.0.1
    import ipaddress
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))
    ])

    server_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    with open(server_key_path, "wb") as f:
        f.write(server_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(server_cert_path, "wb") as f:
        f.write(server_cert.public_bytes(serialization.Encoding.PEM))

    return server_key_path, server_cert_path

def sign_node_cert(node_id: str, public_key_pem: str) -> str:
    """Signs a node public key with the Root CA to generate a client certificate."""
    ca_key, ca_cert = get_or_create_ca()

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
    except Exception as e:
        raise ValueError(f"Invalid public key: {e}")

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Conclave FL Network"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"node-{node_id}"),
    ])

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )

    return cert.public_bytes(serialization.Encoding.PEM).decode()

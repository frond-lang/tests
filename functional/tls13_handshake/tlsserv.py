#!/usr/bin/env python3
# tlsserv.py — TLS 1.3 echo server oracle for the tls13_handshake suite.
# Usage: tlsserv.py <port>
# Uses the committed fixed cert (cert.pem/key.pem, SPKI pin is asserted
# by the suite) when present; generates a throwaway one otherwise.
# Echoes every received line back. Prints "READY" once listening.
import ssl
import socket
import sys
import threading
import os
import datetime

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def make_cert(dirpath):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certp = os.path.join(dirpath, "cert.pem")
    keyp = os.path.join(dirpath, "key.pem")
    with open(certp, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(keyp, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    return certp, keyp


def main():
    port = int(sys.argv[1])
    here = os.path.dirname(os.path.abspath(__file__))
    certp = os.path.join(here, "cert.pem")
    keyp = os.path.join(here, "key.pem")
    if not (os.path.exists(certp) and os.path.exists(keyp)):
        certp, keyp = make_cert(here)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certp, keyp)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    print("READY", flush=True)

    def serve_conn(conn):
        # timeout the raw socket too — a client that vanishes mid-handshake
        # must not wedge this thread forever
        conn.settimeout(10)
        try:
            with ctx.wrap_socket(conn, server_side=True) as tls:
                tls.settimeout(30)
                buf = b""
                while True:
                    data = tls.recv(4096)
                    if not data:
                        break
                    buf += data
                    NL = bytes([10])
                    while NL in buf:
                        idx = buf.index(NL)
                        line = buf[:idx+1]
                        buf = buf[idx+1:]
                        tls.sendall(line)
        except Exception as e:
            print("SERV", e, file=sys.stderr, flush=True)

    while True:
        conn, _ = srv.accept()
        threading.Thread(target=serve_conn, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()

"""Generate a private lab CA and localhost/LAN server certificate; never install OS trust."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import shutil
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

def server_names(hosts, legacy_ip_dns_san=False):
    names=[]
    for host in dict.fromkeys(['localhost','127.0.0.1',*hosts]):
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
            # mbedTLS 2.28 only checks dNSName SANs. Retain the proper IP SAN as well.
            if legacy_ip_dns_san: names.append(x509.DNSName(host))
        except ValueError: names.append(x509.DNSName(host))
    return names

def reissue_server(directory,args):
    paths=[directory/name for name in ('ca.key','ca.crt','server.key','server.crt')]
    if not all(path.is_file() for path in paths): raise SystemExit('An existing complete CA/server key set is required')
    ca=x509.load_pem_x509_certificate(paths[1].read_bytes())
    ca_key=serialization.load_pem_private_key(paths[0].read_bytes(),password=None)
    server_key=serialization.load_pem_private_key(paths[2].read_bytes(),password=None)
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]))
        .issuer_name(ca.subject).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectAlternativeName(server_names(args.host,args.legacy_ip_dns_san)),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .sign(ca_key,hashes.SHA256()))
    backup=directory/'previous'/now.strftime('%Y%m%dT%H%M%S%fZ');backup.mkdir(parents=True)
    shutil.copy2(paths[3],backup/'server.crt')
    paths[3].write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print('Reissued server certificate. Existing CA, private keys and OS trust preserved.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',action='append',default=[],help='Additional laptop LAN IP or hostname')
    parser.add_argument('--renew',action='store_true',help='Back up existing files and generate a new lab CA/server pair')
    parser.add_argument('--reissue-server',action='store_true',help='Reissue only the server certificate with the existing CA and key')
    parser.add_argument('--legacy-ip-dns-san',action='store_true',help='Also include literal IP dNSName SANs for mbedTLS 2.28 clients')
    args=parser.parse_args()
    directory=Path(__file__).resolve().parent/'certs'
    directory.mkdir(parents=True,exist_ok=True)
    if args.reissue_server:
        if args.renew: raise SystemExit('Choose either --renew or --reissue-server')
        reissue_server(directory,args);return
    paths=[directory/name for name in ('ca.key','ca.crt','server.key','server.crt')]
    if any(path.exists() for path in paths):
        if not all(path.exists() for path in paths): raise SystemExit('Incomplete existing certificate set; inspect manually instead of overwriting')
        if not args.renew:
            print('Existing private certificates preserved. OS trust was not changed.')
            return
        backup=directory/'previous'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True)
        for path in paths: shutil.copy2(path,backup/path.name)
    names=server_names(args.host,args.legacy_ip_dns_san)
    now=datetime.now(timezone.utc)
    ca_key=ec.generate_private_key(ec.SECP256R1())
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Driver AIoT Local Demo CA')])
    ca=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True,key_cert_sign=True,crl_sign=True,
            content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,
            encipher_only=False,decipher_only=False),critical=True).sign(ca_key,hashes.SHA256()))
    key=ec.generate_private_key(ec.SECP256R1())
    server=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]))
        .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .add_extension(x509.SubjectAlternativeName(names),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .sign(ca_key,hashes.SHA256()))
    for filename,private in (('ca.key',ca_key),('server.key',key)):
        path=directory/filename
        path.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        path.chmod(0o600)
    for filename,certificate in (('ca.crt',ca),('server.crt',server)):
        (directory/filename).write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    print('Private lab TLS files ready. No OS trust or firewall settings changed; no keys printed.')


if __name__=='__main__': main()

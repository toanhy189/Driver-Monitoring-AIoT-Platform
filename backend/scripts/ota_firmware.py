"""Initialize local signing material, configure public device trust, or sign an app image."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.schemas.ota import FirmwareManifest, signing_bytes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    init=sub.add_parser("init-key")
    init.add_argument("--private-key",required=True,type=Path)
    init.add_argument("--public-key",required=True,type=Path)
    configure=sub.add_parser("configure-device")
    configure.add_argument("--public-key",required=True,type=Path)
    configure.add_argument("--origin",required=True)
    configure.add_argument("--ca",required=True,type=Path)
    configure.add_argument("--header",required=True,type=Path)
    sign=sub.add_parser("sign")
    sign.add_argument("--private-key",required=True,type=Path)
    sign.add_argument("--image",required=True,type=Path)
    sign.add_argument("--version",required=True)
    sign.add_argument("--hardware",default="esp32doit-devkit-v1")
    sign.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    if args.command=="init-key":
        if args.private_key.exists() or args.public_key.exists(): raise SystemExit("Key files already exist; preserved")
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        args.private_key.parent.mkdir(parents=True,exist_ok=True)
        args.public_key.parent.mkdir(parents=True,exist_ok=True)
        with args.private_key.open("xb") as out:
            out.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        args.private_key.chmod(0o600)
        args.public_key.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        print("Created local private key and public verification key. No key data printed.")
    elif args.command=="configure-device":
        from urllib.parse import urlsplit
        origin=args.origin.rstrip('/')
        parsed=urlsplit(origin)
        if parsed.scheme!="https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise SystemExit("An HTTPS origin without path or credentials is required")
        public=args.public_key.read_text(encoding="ascii").strip()
        serialization.load_pem_public_key(public.encode())
        ca=args.ca.read_text(encoding="ascii").strip()
        if "BEGIN CERTIFICATE" not in ca: raise SystemExit("CA certificate required")
        args.header.parent.mkdir(parents=True,exist_ok=True)
        args.header.write_text('#pragma once\nconstexpr char OTA_PUBLIC_KEY_PEM[] = R"OTAKEY('+public+')OTAKEY";\n'
            +'constexpr char OTA_TRUSTED_ORIGIN[] = '+json.dumps(origin)+';\n'
            +'constexpr char OTA_TLS_CA[] = R"OTACA('+ca+')OTACA";\n',encoding="ascii")
        print("Configured public key, HTTPS origin and CA in local firmware header.")
    else:
        data=args.image.read_bytes()
        manifest={"format":"driver-ota-v1","key_id":"ota-key-v1","version":args.version,
            "hardware_version":args.hardware,"size_bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"signature":"x"*344}
        FirmwareManifest.model_validate(manifest)
        key=serialization.load_pem_private_key(args.private_key.read_bytes(),password=None)
        if not isinstance(key,rsa.RSAPrivateKey) or key.key_size!=2048: raise SystemExit("RSA-2048 key required")
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).strip()
        if b"driver-ota-capable-v1;bootloader-rollback;RSA2048-SHA256" not in data or public not in data:
            raise SystemExit("Build an OTA-capable image with this public key before signing. Legacy/wrong-key image rejected.")
        manifest["signature"]=base64.b64encode(key.sign(signing_bytes(manifest),padding.PKCS1v15(),hashes.SHA256())).decode()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        print("Signed firmware manifest:",args.output)

if __name__=="__main__": main()

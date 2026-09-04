#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

SITE_DOMAIN = "amykellam.com"
FILEBASE_BUCKET = "YOUR_BUCKET_NAME"  # Replace with your Filebase bucket name
FILEBASE_ACCESS_KEY = os.environ.get("FILEBASE_ACCESS_KEY", "")
FILEBASE_SECRET_KEY = os.environ.get("FILEBASE_SECRET_KEY", "")
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]

def get_current_cid():
    """Get the CID of your website root from Filebase API or S3"""
    try:
        # Option 1: Use Filebase S3 API to list objects and get the bucket's CID
        import boto3
        from botocore.client import Config
        
        s3 = boto3.client('s3',
            endpoint_url='https://s3.filebase.com',
            aws_access_key_id=FILEBASE_ACCESS_KEY,
            aws_secret_access_key=FILEBASE_SECRET_KEY,
            config=Config(signature_version='s3v4')
        )
        
        # The CID of a folder can be retrieved via the S3 API
        # by listing the bucket and getting the bucket's metadata
        # Alternatively, if you know your website's root CID, you can hardcode it.
        # Let's try to get the bucket's default CID.
        # Note: Filebase S3 doesn't directly give you the bucket CID.
        # If you know the CID, you can set it here.
        
        # For now, try to get it from the bucket's metadata
        # This is a placeholder – we'll use the gateway fallback.
        raise Exception("S3 method not implemented yet.")
    except Exception as e:
        print(f"S3 method failed: {e}")
        # Fallback: use public gateway that returns headers
        try:
            # Try the public Filebase gateway (using your bucket name)
            gateway_url = f"https://ipfs.io/ipns/{SITE_DOMAIN}"
            print(f"Trying gateway: {gateway_url}")
            resp = requests.head(gateway_url, timeout=10)
            cid = resp.headers.get("X-IPFS-Hash") or resp.headers.get("Ipfs-Hash")
            if cid:
                print(f"Resolved CID from gateway: {cid}")
                return cid
            else:
                # Another attempt: use DNSLink
                import dns.resolver
                answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
                for rdata in answers:
                    txt = rdata.to_text().strip('"')
                    if "dnslink=" in txt:
                        parts = txt.split("/ipfs/")
                        if len(parts) > 1:
                            return parts[1]
                raise Exception("Could not resolve CID")
        except Exception as e2:
            print(f"Gateway resolution failed: {e2}")
            raise

def sign_attestation(data_dict):
    account = Account.from_key(PRIVATE_KEY)
    message = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    signed = account.sign_message(encode_defunct(text=message))
    return signed.signature.hex()

def main():
    print("Starting heartbeat...")
    current_cid = get_current_cid()
    now_iso = datetime.now(timezone.utc).isoformat()
    agent_address = Account.from_key(PRIVATE_KEY).address

    attestation = {
        "type": "heartbeat",
        "site": SITE_DOMAIN,
        "cid": current_cid,
        "timestamp": now_iso,
        "agentAddress": agent_address
    }
    attestation["signature"] = sign_attestation(attestation)

    # Load existing log.json
    log = []
    if os.path.exists('log.json'):
        with open('log.json', 'r') as f:
            try:
                log = json.load(f)
                print(f"Loaded {len(log)} existing entries.")
            except json.JSONDecodeError:
                print("Existing log.json is corrupted, starting fresh.")
    else:
        print("No existing log.json, starting fresh.")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Write to log.json
    with open('log.json', 'w') as f:
        json.dump(log, f, indent=2)
    print(f"Successfully wrote log.json with {len(log)} entries.")
    print(f"Last entry CID: {current_cid}")

if __name__ == "__main__":
    main()

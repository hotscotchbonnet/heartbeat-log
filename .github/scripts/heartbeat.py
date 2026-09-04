#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
FILEBASE_ACCESS_KEY = os.environ.get("FILEBASE_ACCESS_KEY", "")
FILEBASE_SECRET_KEY = os.environ.get("FILEBASE_SECRET_KEY", "")

def get_current_cid():
    """Get the current CID of your site from Filebase Platform API"""
    try:
        # Base64 encode the access key:secret key for basic auth
        import base64
        auth_string = f"{FILEBASE_ACCESS_KEY}:{FILEBASE_SECRET_KEY}"
        auth_bytes = auth_string.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        auth_header = base64_bytes.decode('ascii')

        # Call Filebase Platform API to get site info
        # The endpoint for getting site CID depends on your setup
        # Since you're using Filebase Sites, the CID is stored in your bucket
        # Let's use the S3-compatible API via Filebase (simpler than Platform API)
        
        # Option 1: Use the public Filebase gateway for your site
        # Your site is accessible via: https://akwebsite.myfilebase.site
        # The CID is in the HTTP headers
        
        gateway_url = "https://akwebsite.myfilebase.site"
        print(f"Trying gateway: {gateway_url}")
        resp = requests.head(gateway_url, timeout=10)
        
        # Try different header names
        cid = resp.headers.get("X-IPFS-Hash") or resp.headers.get("Ipfs-Hash")
        if cid:
            print(f"Resolved CID from gateway: {cid}")
            return cid
        
        # Option 2: If the gateway doesn't return headers, try a direct IPFS gateway
        # Using your domain via ipfs.io (which uses DNSLink)
        # But since you removed DNSLink, this will fail.
        # Instead, let's try the Filebase public gateway with your bucket
        # You need to replace YOUR_BUCKET_NAME with your actual bucket name
        
        # For now, let's raise an exception with instructions
        raise Exception("Could not resolve CID from gateway. Please check the script.")
        
    except Exception as e:
        print(f"Resolution failed: {e}")
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

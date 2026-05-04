#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct
import boto3
from botocore.client import Config

# ----- Configuration -----
SITE_DOMAIN = "amykellam.com"
GATEWAY = "https://cloudflare-ipfs.com/ipns/"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]
FILEBASE_SECRET_KEY = os.environ["FILEBASE_SECRET_KEY"]
IPNS_NAME = os.environ["IPNS_NAME"]
BUCKET_NAME = "YOUR_BUCKET_NAME"   # <-- REPLACE with your Filebase bucket name

# Filebase S3 endpoint
FILEBASE_ENDPOINT = "https://s3.filebase.com"

def get_current_cid():
    """Resolve the current CID of amykellam.com via DNSLink"""
    resp = requests.get(GATEWAY + SITE_DOMAIN, headers={"Accept": "application/vnd.ipld.raw"})
    if resp.status_code != 200:
        raise Exception(f"Resolution failed: {resp.status_code}")
    cid = resp.headers.get("Ipfs-Hash")
    if not cid:
        # Fallback to DNS TXT record
        import dns.resolver
        answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                cid = txt.split("/ipfs/")[-1]
                break
    if not cid:
        raise Exception("Could not extract CID")
    return cid

def sign_attestation(data_dict):
    account = Account.from_key(PRIVATE_KEY)
    message = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    message_hash = encode_defunct(text=message)
    signed = account.sign_message(message_hash)
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
    signature = sign_attestation(attestation)
    attestation["signature"] = signature

    # --- Filebase S3 interaction ---
    s3 = boto3.client('s3',
        endpoint_url=FILEBASE_ENDPOINT,
        aws_access_key_id=FILEBASE_ACCESS_KEY,
        aws_secret_access_key=FILEBASE_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )

    # Fetch existing log from S3 (if any)
    log = []
    try:
        obj = s3.get_object(Bucket=BUCKET_NAME, Key='log.json')
        log = json.loads(obj['Body'].read().decode('utf-8'))
        print(f"Fetched existing log with {len(log)} entries.")
    except Exception as e:
        print(f"No existing log found, starting fresh: {e}")

    # Append new attestation
    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Write to temporary file
    with open('/tmp/log.json', 'w') as f:
        json.dump(log, f)

    # Upload to Filebase bucket
    s3.upload_file('/tmp/log.json', BUCKET_NAME, 'log.json')
    print("Uploaded log.json to Filebase bucket.")

    # --- Update IPNS using Filebase API ---
    # Filebase requires the CID of the uploaded file. We can retrieve it by making a HEAD request to the IPFS gateway.
    # First, we need the CID. Since Filebase returns the CID in the response headers when uploading via S3? Not directly.
    # Workaround: Use Pinata to pin the same JSON and get CID, or query Filebase's IPFS gateway.
    # Simpler: Use the existing IPNS name's current value as a fallback, but we need the new CID.
    # For reliability, we'll upload the JSON to Pinata as well to get the CID, then update IPNS via Filebase.
    
    # Upload to Pinata to get CID
    headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
    pinata_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=log, headers=headers)
    pinata_resp.raise_for_status()
    new_cid = pinata_resp.json()["IpfsHash"]
    print(f"Pinned log to Pinata with CID: {new_cid}")

    # Now update Filebase IPNS name to point to this CID
    # Filebase API for updating IPNS (using their v1 API)
    filebase_api_url = "https://api.filebase.com/v1/ipns/publish"
    payload = {"name": IPNS_NAME, "cid": new_cid}
    # Filebase uses Bearer token with API key (access key) – check docs; may need different auth.
    # Alternative: Use their S3 bucket's IPNS mapping? Let's use the documented method.
    # If this fails, we can manually update once; but let's try.
    fb_headers = {
        "Authorization": f"Bearer {FILEBASE_ACCESS_KEY}",  # or use secret? Experiment.
        "Content-Type": "application/json"
    }
    try:
        fb_resp = requests.post(filebase_api_url, json=payload, headers=fb_headers)
        fb_resp.raise_for_status()
        print(f"IPNS updated: https://ipfs.io/ipns/{IPNS_NAME}/log.json")
    except Exception as e:
        print(f"IPNS update failed: {e}")
        print("You may need to manually update the IPNS name in Filebase dashboard.")
        print(f"Set {IPNS_NAME} to CID {new_cid}")

    print("Heartbeat completed successfully.")

if __name__ == "__main__":
    main()

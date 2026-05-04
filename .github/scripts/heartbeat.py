#!/usr/bin/env python3
import json
import os
import requests
import dns.resolver
import boto3
from botocore.client import Config
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]
FILEBASE_SECRET_KEY = os.environ["FILEBASE_SECRET_KEY"]
IPNS_NAME = os.environ["IPNS_NAME"]

def get_current_cid():
    answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
    for rdata in answers:
        txt = rdata.to_text().strip('"')
        if "dnslink=" in txt:
            parts = txt.split("/ipfs/")
            if len(parts) > 1:
                return parts[1]
    raise Exception("Could not resolve CID")

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

    # Fetch existing log
    log = []
    try:
        resp = requests.get(f"https://ipfs.io/ipns/{IPNS_NAME}", timeout=10)
        if resp.status_code == 200:
            log = resp.json()
            print(f"Fetched {len(log)} existing entries.")
    except Exception as e:
        print(f"Starting fresh log: {e}")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Pin to Pinata
    headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
    pin_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=log, headers=headers)
    pin_resp.raise_for_status()
    new_cid = pin_resp.json()["IpfsHash"]
    print(f"Pinned new log CID: {new_cid}")

    # --- Update IPNS using Filebase S3 API (works reliably) ---
    s3 = boto3.client('s3',
        endpoint_url='https://s3.filebase.com',
        aws_access_key_id=FILEBASE_ACCESS_KEY,
        aws_secret_access_key=FILEBASE_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )
    # IPNS names are stored as objects in the 'ipns' bucket
    s3.put_object(Bucket='ipns', Key=IPNS_NAME, Body=new_cid, ContentType='text/plain')
    print(f"✅ IPNS updated successfully: https://ipfs.io/ipns/{IPNS_NAME}")

if __name__ == "__main__":
    main()

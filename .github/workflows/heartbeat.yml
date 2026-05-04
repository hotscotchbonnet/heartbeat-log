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

# ----- Configuration -----
SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]
FILEBASE_SECRET_KEY = os.environ["FILEBASE_SECRET_KEY"]
IPNS_NAME = os.environ["IPNS_NAME"]

def get_current_cid():
    try:
        answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                parts = txt.split("/ipfs/")
                if len(parts) > 1:
                    cid = parts[1]
                    print(f"Resolved CID from DNS TXT: {cid}")
                    return cid
    except Exception as e:
        print(f"DNS TXT lookup failed: {e}")
    raise Exception("Could not resolve CID for amykellam.com")

def sign_attestation(data_dict):
    account = Account.from_key(PRIVATE_KEY)
    message = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    message_hash = encode_defunct(text=message)
    signed = account.sign_message(message_hash)
    # Convert v to 27 or 28 for ethers compatibility
    v = signed.v
    if v < 27:
        v += 27
    # Build 65-byte signature: r (32) + s (32) + v (1)
    r_bytes = signed.r.to_bytes(32, 'big')
    s_bytes = signed.s.to_bytes(32, 'big')
    signature_bytes = r_bytes + s_bytes + bytes([v])
    return signature_bytes.hex()

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

    # Fetch existing log
    log = []
    try:
        log_url = f"https://ipfs.io/ipns/{IPNS_NAME}"
        resp = requests.get(log_url, timeout=10)
        if resp.status_code == 200:
            log = resp.json()
            print(f"Fetched existing log with {len(log)} entries.")
        else:
            print("No existing log found, starting fresh.")
    except Exception as e:
        print(f"Could not fetch existing log: {e}")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Pin new log to Pinata
    headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
    payload = {"pinataContent": log, "pinataMetadata": {"name": "heartbeat_log.json"}}
    pinata_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=payload, headers=headers)
    pinata_resp.raise_for_status()
    new_cid = pinata_resp.json()["IpfsHash"]
    print(f"Pinned new log to Pinata with CID: {new_cid}")

    # Update IPNS using Filebase S3
    s3 = boto3.client('s3',
        endpoint_url='https://s3.filebase.com',
        aws_access_key_id=FILEBASE_ACCESS_KEY,
        aws_secret_access_key=FILEBASE_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )
    try:
        s3.put_object(Bucket='ipns', Key=IPNS_NAME, Body=new_cid, ContentType='text/plain')
        print(f"IPNS updated successfully: https://ipfs.io/ipns/{IPNS_NAME}")
    except Exception as e:
        print(f"IPNS update via S3 failed: {e}")
        print(f"Please manually set IPNS name {IPNS_NAME} to CID {new_cid}")

    print("Heartbeat completed.")

if __name__ == "__main__":
    main()

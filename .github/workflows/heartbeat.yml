#!/usr/bin/env python3
import json
import os
import requests
import dns.resolver
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

# ----- Configuration -----
SITE_DOMAIN = "amykellam.com"
# Use ipfs.io gateway instead of cloudflare-ipfs.com
GATEWAY = "https://ipfs.io/ipns/"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]
IPNS_NAME = os.environ["IPNS_NAME"]

def get_current_cid():
    """Get current CID via DNS TXT record (most reliable) or fallback to gateway"""
    # Method 1: Direct DNS TXT lookup (no HTTP, works anywhere)
    try:
        answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                # Format: dnslink=/ipfs/Qm... or dnslink=/ipns/...
                parts = txt.split("/ipfs/")
                if len(parts) > 1:
                    cid = parts[1]
                    print(f"Resolved CID from DNS TXT: {cid}")
                    return cid
    except Exception as e:
        print(f"DNS TXT lookup failed: {e}")

    # Method 2: Fallback to IPFS gateway
    try:
        resp = requests.get(GATEWAY + SITE_DOMAIN, headers={"Accept": "application/vnd.ipld.raw"}, timeout=10)
        if resp.status_code == 200:
            cid = resp.headers.get("Ipfs-Hash")
            if cid:
                print(f"Resolved CID from gateway: {cid}")
                return cid
    except Exception as e:
        print(f"Gateway lookup failed: {e}")

    raise Exception("Could not resolve CID for amykellam.com")

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

    # Fetch existing log from current IPNS address (if any)
    log = []
    try:
        log_url = f"https://ipfs.io/ipns/{IPNS_NAME}/log.json"
        resp = requests.get(log_url, timeout=10)
        if resp.status_code == 200:
            log = resp.json()
            print(f"Fetched existing log with {len(log)} entries.")
        else:
            print("No existing log found, starting fresh.")
    except Exception as e:
        print(f"Could not fetch existing log: {e}")

    # Append new attestation
    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Pin new log to Pinata
    headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
    payload = {
        "pinataContent": log,
        "pinataMetadata": {"name": "heartbeat_log.json"}
    }
    pinata_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=payload, headers=headers)
    pinata_resp.raise_for_status()
    new_cid = pinata_resp.json()["IpfsHash"]
    print(f"Pinned new log to Pinata with CID: {new_cid}")

    # Update Filebase IPNS name
    filebase_api_url = "https://api.filebase.com/v1/ipns/publish"
    fb_payload = {"name": IPNS_NAME, "cid": new_cid}
    fb_headers = {
        "Authorization": f"Bearer {FILEBASE_ACCESS_KEY}",
        "Content-Type": "application/json"
    }
    fb_resp = requests.post(filebase_api_url, json=fb_payload, headers=fb_headers)
    if fb_resp.status_code == 200:
        print(f"IPNS updated successfully: https://ipfs.io/ipns/{IPNS_NAME}/log.json")
    else:
        print(f"IPNS update failed: {fb_resp.status_code} - {fb_resp.text}")
        print(f"Please manually set IPNS name {IPNS_NAME} to CID {new_cid} in Filebase dashboard.")

    print("Heartbeat completed.")

if __name__ == "__main__":
    main()

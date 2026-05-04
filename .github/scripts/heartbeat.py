#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

# ----- Configuration -----
SITE_DOMAIN = "amykellam.com"
GATEWAY = "https://cloudflare-ipfs.com/ipns/"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]
IPNS_NAME = os.environ["IPNS_NAME"]

def get_current_cid():
    resp = requests.get(GATEWAY + SITE_DOMAIN, headers={"Accept": "application/vnd.ipld.raw"})
    if resp.status_code != 200:
        raise Exception(f"Resolution failed: {resp.status_code}")
    cid = resp.headers.get("Ipfs-Hash")
    if not cid:
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

    # Update Filebase IPNS name to point to the new CID
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

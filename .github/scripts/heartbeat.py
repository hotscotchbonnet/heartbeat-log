#!/usr/bin/env python3
import json
import os
import requests
import dns.resolver
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
FILEBASE_ACCESS_KEY = os.environ["FILEBASE_ACCESS_KEY"]  # Bearer token
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

    # Fetch existing log from IPNS
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

    # Update IPNS via Filebase REST API (Bearer token)
    fb_url = f"https://api.filebase.com/ipns/{IPNS_NAME}"
    fb_headers = {"Authorization": f"Bearer {FILEBASE_ACCESS_KEY}", "Content-Type": "application/json"}
    fb_payload = {"cid": new_cid}
    fb_resp = requests.put(fb_url, json=fb_payload, headers=fb_headers)
    if fb_resp.status_code == 200:
        print(f"✅ IPNS updated: https://ipfs.io/ipns/{IPNS_NAME}")
    else:
        print(f"❌ IPNS update failed: {fb_resp.status_code} - {fb_resp.text}")
        exit(1)

if __name__ == "__main__":
    main()

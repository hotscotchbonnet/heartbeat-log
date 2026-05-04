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
# IPNS_NAME is used only to fetch existing log (optional)
IPNS_NAME = os.environ.get("IPNS_NAME")

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

    # Try to fetch existing log from previous IPNS pointer (if available)
    log = []
    if IPNS_NAME:
        try:
            resp = requests.get(f"https://ipfs.io/ipns/{IPNS_NAME}", timeout=10)
            if resp.status_code == 200:
                log = resp.json()
                print(f"Fetched {len(log)} existing entries.")
        except Exception as e:
            print(f"No existing log found, starting fresh: {e}")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Pin to Pinata
    headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
    pin_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=log, headers=headers)
    pin_resp.raise_for_status()
    new_cid = pin_resp.json()["IpfsHash"]
    print(f"Pinned new log CID: {new_cid}")

    # Output for GitHub Actions
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        print(f"new_cid={new_cid}", file=f)
        # Also output the full log if needed (optional)
        # print(f"log_json={json.dumps(log)}", file=f)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
import dns.resolver
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]

def get_current_cid():
    # Filebase gateway returns the CID in the response headers
    import requests
    try:
        # Use your Filebase CNAME or the public gateway
        gateway_url = "https://akwebsite.myfilebase.site"
        resp = requests.head(gateway_url)
        # Filebase returns the CID in the 'X-IPFS-Hash' or 'Ipfs-Hash' header
        cid = resp.headers.get("X-IPFS-Hash") or resp.headers.get("Ipfs-Hash")
        if cid:
            print(f"Resolved CID from Filebase gateway: {cid}")
            return cid
        else:
            raise Exception("No CID in headers")
    except Exception as e:
        print(f"Gateway resolution failed: {e}")
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

    # Load existing log.json from the current directory (if it exists)
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

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

    # Load existing log if it exists
    log = []
    if os.path.exists('log.json'):
        with open('log.json', 'r') as f:
            log = json.load(f)
        print(f"Loaded {len(log)} existing entries.")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Write to file
    with open('log.json', 'w') as f:
        json.dump(log, f)
    print(f"Updated log.json with {len(log)} entries.")

if __name__ == "__main__":
    main()

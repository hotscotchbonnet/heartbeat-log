#!/usr/bin/env python3
import json
import os
import subprocess
import time
import requests
import dns.resolver
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

# ----- Configuration -----
SITE_DOMAIN = "amykellam.com"
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ.get("PINATA_JWT", "")  # optional backup
IPFS_PRIVATE_KEY_B64 = os.environ["IPFS_PRIVATE_KEY"]
IPNS_NAME = os.environ.get("IPNS_NAME", "")   # optional, script can read from key

def get_current_cid():
    try:
        answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                parts = txt.split("/ipfs/")
                if len(parts) > 1:
                    cid = parts[1]
                    print(f"Resolved main site CID: {cid}")
                    return cid
    except Exception as e:
        print(f"DNS lookup failed: {e}")
    raise Exception("Could not resolve main site CID")

def sign_attestation(data_dict):
    account = Account.from_key(PRIVATE_KEY)
    message = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
    message_hash = encode_defunct(text=message)
    signed = account.sign_message(message_hash)
    return signed.signature.hex()

def get_ipns_name():
    # Try to read from environment, otherwise derive from key after import
    if IPNS_NAME:
        return IPNS_NAME
    # Fallback: import key temporarily to get the name
    with open("/tmp/key.priv", "w") as f:
        f.write(IPFS_PRIVATE_KEY_B64)
    result = subprocess.run(
        ["ipfs", "key", "import", "temp-key", "-"],
        input=base64.b64decode(IPFS_PRIVATE_KEY_B64),
        capture_output=True, text=True
    )
    # This is messy; better to set IPNS_NAME secret. We'll require it.
    raise Exception("Please set IPNS_NAME secret")

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

    # Fetch existing log from current IPNS (via public gateway)
    log = []
    try:
        resp = requests.get(f"https://ipfs.io/ipns/{IPNS_NAME}", timeout=10)
        if resp.status_code == 200:
            log = resp.json()
            print(f"Fetched existing log: {len(log)} entries")
    except Exception as e:
        print(f"No existing log or fetch failed: {e}")

    log.append(attestation)
    if len(log) > 365:
        log = log[-365:]

    # Optional: Pin to Pinata as backup (keep this, it's reliable)
    if PINATA_JWT:
        headers = {"Authorization": f"Bearer {PINATA_JWT}", "Content-Type": "application/json"}
        payload = {"pinataContent": log, "pinataMetadata": {"name": "heartbeat_log.json"}}
        pinata_resp = requests.post("https://api.pinata.cloud/pinning/pinJSONToIPFS", json=payload, headers=headers)
        pinata_resp.raise_for_status()
        new_cid = pinata_resp.json()["IpfsHash"]
        print(f"Pinned to Pinata (backup): {new_cid}")
    else:
        # If no Pinata, we need to add the file to the local node directly
        new_cid = None

    # --- IPFS local node publishing ---
    # Write log to file
    with open("/tmp/log.json", "w") as f:
        json.dump(log, f)

    # Add file to local node (node must be running)
    add_output = subprocess.check_output(["ipfs", "add", "-Q", "/tmp/log.json"], text=True).strip()
    new_cid = add_output
    print(f"Added log to local node: {new_cid}")

    # Import IPNS private key
    key_import_cmd = f'echo "{IPFS_PRIVATE_KEY_B64}" | base64 -d | ipfs key import heartbeat-key -'
    subprocess.run(key_import_cmd, shell=True, check=True)

    # Publish to IPNS
    pub_output = subprocess.check_output(["ipfs", "name", "publish", "--key=heartbeat-key", f"/ipfs/{new_cid}"], text=True)
    print(f"IPNS published: {pub_output.strip()}")

    print("Heartbeat complete.")
    print(f"Log available at: https://ipfs.io/ipns/{IPNS_NAME}")

if __name__ == "__main__":
    main()

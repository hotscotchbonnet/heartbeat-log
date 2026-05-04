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
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
PINATA_JWT = os.environ["PINATA_JWT"]
CLOUDFLARE_API_TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
CLOUDFLARE_ZONE_ID = os.environ["CLOUDFLARE_ZONE_ID"]
DNS_RECORD_NAME = "_dnslink.log"  # TXT record for log subdomain

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

def update_cloudflare_dnslink(new_cid):
    # Find the existing TXT record
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}", "Content-Type": "application/json"}
    url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"
    resp = requests.get(url, headers=headers, params={"name": DNS_RECORD_NAME, "type": "TXT"})
    resp.raise_for_status()
    records = resp.json()["result"]
    if records:
        record_id = records[0]["id"]
        # Update existing record
        data = {
            "type": "TXT",
            "name": DNS_RECORD_NAME,
            "content": f"dnslink=/ipfs/{new_cid}",
            "ttl": 120
        }
        update_resp = requests.put(f"{url}/{record_id}", headers=headers, json=data)
        update_resp.raise_for_status()
        print(f"Updated DNSLink for {DNS_RECORD_NAME} to /ipfs/{new_cid}")
    else:
        # Create new record
        data = {
            "type": "TXT",
            "name": DNS_RECORD_NAME,
            "content": f"dnslink=/ipfs/{new_cid}",
            "ttl": 120
        }
        create_resp = requests.post(url, headers=headers, json=data)
        create_resp.raise_for_status()
        print(f"Created DNSLink for {DNS_RECORD_NAME} to /ipfs/{new_cid}")

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

    # Fetch existing log from the current DNSLink of log subdomain
    log = []
    try:
        # Resolve log.amykellam.com via DNSLink
        answers = dns.resolver.resolve("_dnslink.log.amykellam.com", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                parts = txt.split("/ipfs/")
                if len(parts) > 1:
                    old_cid = parts[1]
                    resp = requests.get(f"https://ipfs.io/ipfs/{old_cid}", timeout=10)
                    if resp.status_code == 200:
                        log = resp.json()
                        print(f"Fetched existing log with {len(log)} entries.")
                    break
    except Exception as e:
        print(f"No existing log found: {e}")

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

    # Update Cloudflare DNSLink
    update_cloudflare_dnslink(new_cid)

    print("Heartbeat complete. Log available at https://log.amykellam.com")

if __name__ == "__main__":
    main()

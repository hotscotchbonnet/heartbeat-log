#!/usr/bin/env python3
import json
import os
import requests
import base64
from datetime import datetime, timezone
from eth_account import Account
from eth_account.messages import encode_defunct

# ---------- Configuration ----------
SITE_DOMAIN = "amykellam.com"
FILEBASE_BUCKET = "akwebsite"  # <-- REPLACE with your bucket name if different
PRIVATE_KEY = os.environ["AGENT_PRIVATE_KEY"]
FILEBASE_ACCESS_KEY = os.environ.get("FILEBASE_ACCESS_KEY", "")
FILEBASE_SECRET_KEY = os.environ.get("FILEBASE_SECRET_KEY", "")

def clean_cid(cid):
    """Remove W/ prefix, quotes, and whitespace from a CID string."""
    if not cid:
        return cid
    # Remove W/ prefix and quotes
    cid = cid.strip()
    if cid.startswith('W/"'):
        cid = cid[3:]
    elif cid.startswith('"'):
        cid = cid[1:]
    if cid.endswith('"'):
        cid = cid[:-1]
    return cid.strip()

def get_current_cid():
    """
    Resolve the current CID of your website from Filebase.
    Tries: 1) Filebase Platform API, 2) Gateway headers, 3) DNSLink (fallback).
    """
    # ---------- Method 1: Filebase Platform API (most reliable) ----------
    if FILEBASE_ACCESS_KEY and FILEBASE_SECRET_KEY:
        try:
            auth_string = f"{FILEBASE_ACCESS_KEY}:{FILEBASE_SECRET_KEY}"
            auth_bytes = auth_string.encode('ascii')
            base64_bytes = base64.b64encode(auth_bytes)
            auth_header = base64_bytes.decode('ascii')

            url = f"https://api.filebase.io/v1/buckets/{FILEBASE_BUCKET}"
            headers = {"Authorization": f"Basic {auth_header}"}
            print(f"Fetching CID from Filebase API: {url}")
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                cid = data.get("cid") or data.get("ipfs_cid") or data.get("root_cid")
                if cid:
                    cid = clean_cid(cid)
                    print(f"Resolved CID from Filebase API: {cid}")
                    return cid
                else:
                    print("API response did not contain CID. Response:", data)
            else:
                print(f"API call failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"API method failed: {e}")

    # ---------- Method 2: Gateway headers (fallback) ----------
    try:
        gateway_url = "https://akwebsite.myfilebase.site"
        print(f"Trying gateway: {gateway_url}")
        resp = requests.head(gateway_url, timeout=10)
        cid = resp.headers.get("X-IPFS-Hash") or resp.headers.get("Ipfs-Hash") or resp.headers.get("ETag")
        if cid:
            cid = clean_cid(cid)
            print(f"Resolved CID from gateway: {cid}")
            return cid
    except Exception as e:
        print(f"Gateway method failed: {e}")

    # ---------- Method 3: DNSLink (legacy fallback) ----------
    try:
        import dns.resolver
        answers = dns.resolver.resolve(f"_dnslink.{SITE_DOMAIN}", "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "dnslink=" in txt:
                parts = txt.split("/ipfs/")
                if len(parts) > 1:
                    cid = clean_cid(parts[1])
                    print(f"Resolved CID from DNSLink: {cid}")
                    return cid
    except Exception as e:
        print(f"DNSLink method failed: {e}")

    # ---------- If all methods fail ----------
    raise Exception("Could not resolve CID. Please check your Filebase bucket and credentials.")

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

    # Load existing log.json
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

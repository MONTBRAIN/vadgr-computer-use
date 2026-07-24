#!/usr/bin/env python3
"""Upload + publish an extension zip to the Chrome Web Store (API, service-account token).

First-party publisher so no third-party action ever touches the credential.
Auth: expects a short-lived OAuth access token for scope
``https://www.googleapis.com/auth/chromewebstore`` in ``$CWS_TOKEN`` (minted per run
by ``google-github-actions/auth`` via Workload Identity Federation impersonating the
publisher-linked service account). No long-lived secret anywhere.

Usage:
    CWS_TOKEN=... python cws_publish.py --item <ITEM_ID> --zip <store.zip> [--no-publish]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://www.googleapis.com/chromewebstore/v1.1"
UPLOAD = "https://www.googleapis.com/upload/chromewebstore/v1.1"


def _req(method, url, token, data=None, extra_headers=None):
    headers = {"Authorization": f"Bearer {token}", "x-goog-api-version": "2"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True, help="Chrome Web Store item ID")
    ap.add_argument("--zip", required=True, help="path to the key-stripped store zip")
    ap.add_argument("--no-publish", action="store_true", help="upload as draft only")
    ap.add_argument("--target", default="default", choices=["default", "trustedTesters"])
    a = ap.parse_args()

    token = os.environ.get("CWS_TOKEN")
    if not token:
        sys.exit("CWS_TOKEN not set (the auth step must export an access_token).")

    with open(a.zip, "rb") as f:
        payload = f.read()
    print(f"Uploading {a.zip} ({len(payload)} bytes) to item {a.item} ...")
    code, res = _req(
        "PUT",
        f"{UPLOAD}/items/{a.item}?uploadType=media",
        token,
        data=payload,
        extra_headers={"Content-Type": "application/zip"},
    )
    print("upload response:", code, json.dumps(res)[:800])
    state = res.get("uploadState") if isinstance(res, dict) else None
    if code != 200 or state != "SUCCESS":
        sys.exit(f"Upload failed (http {code}, uploadState={state}).")

    if a.no_publish:
        print("Uploaded as draft. --no-publish set; skipping publish.")
        return

    print(f"Publishing item {a.item} (target={a.target}) ...")
    code, res = _req(
        "POST",
        f"{API}/items/{a.item}/publish?publishTarget={a.target}",
        token,
        data=b"",
        extra_headers={"Content-Length": "0"},
    )
    print("publish response:", code, json.dumps(res)[:800])
    if code >= 400:
        sys.exit(f"Publish failed (http {code}).")
    status = res.get("status") if isinstance(res, dict) else None
    # A `debugger`/broad-permission item enters in-depth review; statuses like
    # ITEM_PENDING_REVIEW are expected and not a failure of the pipeline.
    if isinstance(status, list) and any(s != "OK" for s in status):
        print(f"Publish accepted; status={status} (likely pending review).")
    else:
        print("Publish accepted (status OK).")
    print("Done.")


if __name__ == "__main__":
    main()

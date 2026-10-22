"""
Stage 1 storage E2E — the presigned object-storage path against a real
S3-compatible endpoint (moto server on 127.0.0.1:9000).

  upload-url (presigned PUT) -> browser-style PUT -> complete-upload (HEAD)
  -> train (reads bytes back from storage) -> download-url (presigned GET)
  -> workspace delete (object sweep)

Proves the exact flow Cloudflare R2 will use in production.
"""
import asyncio
import os
import sys
import time
import uuid

import boto3
import httpx
from botocore.config import Config

API = os.environ.get("E2E_API", "http://127.0.0.1:8002")
S3_ENDPOINT = os.environ.get("E2E_S3_ENDPOINT", "http://127.0.0.1:9000")
BUCKET = os.environ.get("E2E_S3_BUCKET", "botbase")

PASSED, FAILED = [], []


def check(cond, label, extra=""):
    if cond:
        PASSED.append(label)
        print(f"PASS  {label}", flush=True)
    else:
        FAILED.append(f"{label} {extra}".strip())
        print(f"FAIL  {label} {extra}".strip(), flush=True)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=os.environ.get("E2E_S3_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("E2E_S3_SECRET", "minioadmin"),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


async def main():
    s3 = s3_client()
    tag = uuid.uuid4().hex[:8]
    body = (
        b"BotBase storage test document.\n"
        b"Refund policy: refunds are issued within 14 days of purchase.\n"
        b"Support hours: Monday to Friday, 09:00 to 17:00 EAT.\n"
    )
    filename = "storage-policy.txt"

    async with httpx.AsyncClient(base_url=API, timeout=120) as c:
        r = await c.post(
            "/auth/register",
            json={"email": f"storage-{tag}@example.com", "password": "StrongPass123!"},
        )
        check(r.status_code == 201, "registered for the storage test", r.text[:200])
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post("/workspaces", json={"name": "Storage QA"}, headers=headers)
        check(r.status_code in (200, 201), "workspace created", r.text[:200])
        ws = r.json()["id"]

        # ── step 1: mint a presigned PUT URL ─────────────────────────────
        r = await c.post(
            f"/workspaces/{ws}/documents/upload-url",
            json={
                "filename": filename,
                "content_type": "text/plain",
                "size_bytes": len(body),
            },
            headers=headers,
        )
        check(r.status_code in (200, 201), "presigned upload URL minted", r.text[:300])
        minted = r.json()
        doc_id = minted["doc_id"]
        put_url = minted["url"]
        object_key = minted["object_key"]
        check(put_url.startswith("http"), "presigned URL is absolute", put_url[:60])
        check(S3_ENDPOINT in put_url, "presigned URL points at the configured endpoint")

        # ── step 2: PUT the bytes exactly like a browser would ──────────
        async with httpx.AsyncClient(timeout=120) as browser:
            r = await browser.put(
                put_url,
                content=body,
                headers={"Content-Type": "text/plain"},
            )
        check(r.status_code in (200, 204), "bytes uploaded to object storage", f"{r.status_code} {r.text[:200]}")

        listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=object_key)
        check(listing.get("KeyCount", 0) == 1, "object is in the bucket", str(listing.get("KeyCount")))
        stored = s3.get_object(Bucket=BUCKET, Key=object_key)["Body"].read()
        check(stored == body, "stored bytes match what was uploaded")

        # ── step 3: complete-upload (HEAD verification) ──────────────────
        r = await c.post(
            f"/workspaces/{ws}/documents/{doc_id}/complete-upload", headers=headers
        )
        check(r.status_code == 200, "complete-upload accepted", r.text[:300])
        check(r.json().get("status") == "uploaded", "document marked uploaded", r.text[:200])

        # ── step 4: train (reads the bytes back from storage) ───────────
        r = await c.post(f"/workspaces/{ws}/documents/{doc_id}/train", headers=headers)
        check(r.status_code in (200, 202), "training accepted", r.text[:200])

        status = None
        deadline = time.time() + 240
        while time.time() < deadline:
            r = await c.get(f"/workspaces/{ws}/documents/{doc_id}/status", headers=headers)
            status = r.json().get("status") if r.status_code == 200 else f"http {r.status_code}"
            if status in ("ready", "failed"):
                break
            await asyncio.sleep(2)
        check(status == "ready", "document trained from object storage", f"status={status}")

        # ── step 5: presigned GET back ───────────────────────────────────
        r = await c.get(f"/workspaces/{ws}/documents/{doc_id}/download-url", headers=headers)
        check(r.status_code == 200, "download URL minted", r.text[:200])
        get_url = r.json().get("url") or r.json().get("download_url")
        check(bool(get_url), "download URL present", r.text[:200])
        async with httpx.AsyncClient(timeout=120) as browser:
            r = await browser.get(get_url)
        check(r.status_code == 200, "presigned GET returns the bytes", f"{r.status_code}")
        check(r.content == body, "downloaded bytes match the original")

        # ── step 6: delete the workspace -> object sweep ─────────────────
        r = await c.delete(f"/workspaces/{ws}", headers=headers)
        check(r.status_code in (200, 204), "workspace deleted", r.text[:200])

        listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=object_key)
        check(listing.get("KeyCount", 0) == 0, "object removed from storage", str(listing.get("KeyCount")))

    print(f"\n=== STORAGE E2E: {len(PASSED)} passed, {len(FAILED)} failed ===")
    if FAILED:
        for f in FAILED:
            print("  FAILED:", f)
        sys.exit(1)
    print("STORAGE_E2E_RESULT=PASS")


if __name__ == "__main__":
    asyncio.run(main())

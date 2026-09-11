#!/usr/bin/env python3
"""
scripts/ingest_sample.py
Upload a sample PDF via the API to test the ingestion pipeline.
Usage: python scripts/ingest_sample.py path/to/doc.pdf
"""
import asyncio
import sys
import httpx

API_URL = "http://localhost:8000/api/v1"
API_KEY = "dev-key"

async def upload(pdf_path: str):
    async with httpx.AsyncClient(timeout=120) as client:
        with open(pdf_path, "rb") as f:
            resp = await client.post(
                f"{API_URL}/documents/upload",
                headers={"X-API-Key": API_KEY},
                files={"file": (pdf_path.split("/")[-1], f, "application/pdf")},
            )
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ Ingested: {data['filename']}")
        print(f"  Document ID:  {data['document_id']}")
        print(f"  Pages:        {data['total_pages']}")
        print(f"  Chunks:       {data['chunk_count']}")
        return data["document_id"]

async def query(doc_id: str, question: str):
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_URL}/query/",
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={"question": question, "document_id": doc_id},
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"\nQ: {question}")
        print(f"A: {data['answer']}")
        print(f"   Grounded: {data['grounded']}")
        if data["citations"]:
            pages = [str(c["page"]) for c in data["citations"]]
            print(f"   Pages cited: {', '.join(pages)}")

async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_sample.py <path-to.pdf> [question]")
        sys.exit(1)
    pdf = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else "What is this document about?"
    doc_id = await upload(pdf)
    await query(doc_id, question)

if __name__ == "__main__":
    asyncio.run(main())

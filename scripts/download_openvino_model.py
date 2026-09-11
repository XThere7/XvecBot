#!/usr/bin/env python3
"""Download a pre-quantized OpenVINO INT4 Qwen model from Hugging Face.

Usage:
    python scripts/download_openvino_model.py
    python scripts/download_openvino_model.py --model OpenVINO/Qwen2.5-7B-Instruct-int4-ov
    python scripts/download_openvino_model.py --model OpenVINO/Qwen2.5-3B-Instruct-int4-ov --dest ./models

Recommended IDs (INT4, ready to run — no conversion needed):
    OpenVINO/Qwen2.5-3B-Instruct-int4-ov   ~2 GB RAM   (recommended for 11 GB machines)
    OpenVINO/Qwen2.5-7B-Instruct-int4-ov   ~4-5 GB RAM (max for 11 GB machines)

Do NOT download a 32B IR on this hardware (~18 GB+ even as INT4 — still OOMs).

After download, set in .env:
    LLM_PROVIDER=openvino
    OPENVINO_MODEL_ID=./models/qwen2.5-3b-instruct-int4-ov
"""
import argparse
import sys
from pathlib import Path

DEFAULT_MODEL = "OpenVINO/Qwen2.5-3B-Instruct-int4-ov"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model ID")
    parser.add_argument(
        "--dest",
        default="./models",
        help="Directory to download into (default: ./models)",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "huggingface-hub is not installed. Run:\n"
            "  pip install -r backend/requirements-openvino.txt",
            file=sys.stderr,
        )
        return 1

    dest = Path(args.dest) / args.model.split("/")[-1].lower()
    print(f"Downloading {args.model} -> {dest} ...")
    snapshot_download(
        repo_id=args.model,
        local_dir=str(dest),
        # Only the files OpenVINO + tokenizers need — skip fp16/bf16 originals.
        allow_patterns=[
            "*.xml",
            "*.bin",
            "*.json",
            "*.txt",
            "*.model",
            "tokenizer*",
            "*.jinja",
        ],
    )

    xml = list(dest.glob("*.xml")) or list(dest.rglob("openvino_model.xml"))
    if not xml:
        print(
            f"WARNING: no OpenVINO IR (*.xml) found in {dest}. "
            "Check the model ID — it must be an *-ov / *-int4-ov repo.",
            file=sys.stderr,
        )
        return 1

    print(f"Done. IR files: {[p.name for p in xml]}")
    print("Set in .env:")
    print("  LLM_PROVIDER=openvino")
    print(f"  OPENVINO_MODEL_ID={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

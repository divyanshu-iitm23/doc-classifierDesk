"""
cli.py
------
Command-line interface for the document classification engine.

Examples:
    python cli.py samples/aadhaar_card.pdf          # classify one file
    python cli.py samples/                           # classify a whole folder
    python cli.py samples/ --json                    # machine-readable output
    python cli.py scan.pdf --lang eng+hin            # OCR with extra language
"""

import argparse
import json
import os
import sys

from engine import classify_pdf, classify_folder


def _print_human(r):
    if not r.get("ok", False):
        print(f"  {r['file']:32s}  ERROR: {r.get('error')}")
        return
    flag = "  ⚠ REVIEW" if r["needs_human_review"] else ""
    ident = r["identifier"] or "—"
    valid = "valid" if r["identifier_valid"] else "not validated"
    print(f"  {r['file']:32s}  ->  {r['display_name']:18s} "
          f"conf={r['confidence']:.2f}  [{ident} · {valid}]  "
          f"({r['extraction_method']}, {r['elapsed_ms']}ms){flag}")


def main():
    ap = argparse.ArgumentParser(description="Indian KYC document classifier")
    ap.add_argument("path", help="a PDF file or a folder of PDFs")
    ap.add_argument("--json", action="store_true", help="print full JSON")
    ap.add_argument("--lang", default="eng", help="Tesseract OCR language(s), e.g. eng+hin")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"Path not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    if os.path.isdir(args.path):
        results = classify_folder(args.path, ocr_lang=args.lang)
    else:
        results = [classify_pdf(args.path, ocr_lang=args.lang)]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(f"\n  Classified {len(results)} document(s):\n")
        for r in results:
            _print_human(r)
        print()


if __name__ == "__main__":
    main()

"""
cli.py
------
Command-line interface for the document classification engine.

Examples:
    python cli.py samples/aadhaar_card.pdf          # classify one file (PDF or image)
    python cli.py mydocs/                            # classify a whole folder
    python cli.py mydocs/ --json                     # machine-readable output
    python cli.py photo.jpg                          # a phone photo works too
    python cli.py scan.pdf --lang eng+hin            # OCR with an extra language pack
    python cli.py mydocs/ --no-ocr                   # text-layer only (fast, digital PDFs)
"""

import argparse
import json
import os
import sys

from engine import classify_file, classify_folder


def _print_human(r):
    if not r.get("ok", False):
        print(f"  {r['file']:32s}  {r['decision']}: {r.get('error')}")
        return
    flag = "  ⚠ REVIEW" if r.get("needs_human_review") else ""
    ident = r["identifier"] or "—"
    valid = "valid" if r["identifier_valid"] else "not validated"
    print(f"  {r['file']:32s}  ->  {r['display_name']:18s} "
          f"conf={r['confidence']:.2f}  [{ident} · {valid}]  "
          f"({r['extraction_method']}, {r['elapsed_ms']}ms){flag}")


def main():
    ap = argparse.ArgumentParser(description="Indian KYC document classifier")
    ap.add_argument("path", help="a PDF/image file or a folder of them")
    ap.add_argument("--json", action="store_true", help="print full JSON")
    ap.add_argument("--lang", default="eng", help="Tesseract OCR language(s), e.g. eng+hin")
    ap.add_argument("--no-ocr", action="store_true", help="text-layer only; skip OCR")
    ap.add_argument("--lenient", action="store_true",
                    help="classify on identifier shape only (no checksum/keywords) — "
                         "for testing with DUMMY documents; not for production")
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f"Path not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    use_ocr = not args.no_ocr
    if os.path.isdir(args.path):
        results = classify_folder(args.path, ocr_lang=args.lang, ocr=use_ocr, lenient=args.lenient)
    else:
        results = [classify_file(args.path, ocr_lang=args.lang, ocr=use_ocr, lenient=args.lenient)]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(f"\n  Classified {len(results)} document(s):\n")
        for r in results:
            _print_human(r)
        print()


if __name__ == "__main__":
    main()

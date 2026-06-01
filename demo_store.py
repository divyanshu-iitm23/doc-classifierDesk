"""
demo_store.py
-------------
Classify every document in samples/ and store extracted data into SQLite.

Run:  python3 demo_store.py
"""

import os
import sys

from engine import classify_file
from engine.extractor import text_candidates
from engine.store import store_result
from engine.model import init_db, get_session, IDDocument, PANCard, BankAccount

SAMPLES_DIR = "samples"
CUSTOMER_ID = "cust-001"


def main():
    # 1) Init the DB
    init_db()
    print("✓ Database initialised\n")

    # 2) Process every file in samples/
    exts = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
    files = sorted(
        f for f in os.listdir(SAMPLES_DIR)
        if os.path.splitext(f)[1].lower() in exts
    )
    print(f"Found {len(files)} documents in {SAMPLES_DIR}/\n")
    print(f"{'File':<35s} {'Decision':<18s} {'ID':<18s} {'Stored':<8s} Table")
    print("─" * 100)

    stored_count = 0
    for fname in files:
        path = os.path.join(SAMPLES_DIR, fname)

        # Classify
        result = classify_file(path, lenient=True)

        if not result.get("ok"):
            print(f"{fname:<35s} {'ERROR':<18s} {'—':<18s} {'—':<8s} {result.get('error', '')[:40]}")
            continue

        decision = result["decision"]
        identifier = result.get("identifier") or "—"

        # Get raw text for field extraction (first usable candidate)
        raw_text = ""
        try:
            raw_text = next((t for t, _ in text_candidates(path)), "")
        except Exception:
            pass

        # Store
        outcome = store_result(CUSTOMER_ID, result, raw_text)
        did_store = outcome.get("stored", False)
        table = outcome.get("table", "—")
        if did_store:
            stored_count += 1

        status = "✓" if did_store else "—"
        print(f"{fname:<35s} {decision:<18s} {identifier:<18s} {status:<8s} {table}")

        # Print extracted fields for stored documents
        if did_store:
            fields = outcome.get("fields", {})
            non_null = {k: v for k, v in fields.items() if v is not None}
            for k, v in non_null.items():
                print(f"  {'':35s} ↳ {k}: {v}")

    # 3) Summary
    print("─" * 100)
    print(f"\n✓ Processed {len(files)} files, stored {stored_count} records\n")

    # 4) Query DB contents
    print("═" * 60)
    print("  DATABASE CONTENTS")
    print("═" * 60)

    s = get_session()

    docs = s.query(IDDocument).all()
    if docs:
        print(f"\n  📋 id_documents ({len(docs)} records):")
        for doc in docs:
            print(f"     {doc.document_type.value:10s} │ {doc.document_id:15s} │ {doc.name or '—':20s} │ DOB: {doc.date_of_birth or '—'}")

    pans = s.query(PANCard).all()
    if pans:
        print(f"\n  📋 pan_cards ({len(pans)} records):")
        for pan in pans:
            print(f"     {pan.pan_no:10s} │ {pan.name or '—':20s} │ father: {pan.father_name or '—'}")

    banks = s.query(BankAccount).all()
    if banks:
        print(f"\n  📋 bank_accounts ({len(banks)} records):")
        for bank in banks:
            print(f"     {bank.account_no:15s} │ {bank.bank_name or '—':25s} │ IFSC: {bank.ifsc_code or '—':11s} │ {bank.account_type or '—'}")

    s.close()
    print(f"\n✓ Data saved in doc_classifier.db")


if __name__ == "__main__":
    main()

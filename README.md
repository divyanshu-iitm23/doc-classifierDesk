# Document Classification Engine — Indian KYC, Bank & Receipt Documents (v5)

The first engine of the L&T Finance AI Document Intelligence platform (BRD §7.8).
It classifies single-document PDFs **and images** into one of eleven Indian document
types across three families:

| # | Document | Family | Anchor | How it's classified |
|---|----------|--------|--------|---------------------|
| 1 | **Aadhaar** | ID card | 12 digits | identifier + Verhoeff checksum |
| 2 | **PAN** | ID card | `AAAAA9999A` | identifier + structure |
| 3 | **Voter ID** | ID card | `AAA9999999` | identifier + structure |
| 4 | **Driving Licence** | ID card | `AA` + 13 digits | identifier + valid RTO state code |
| 5 | **Passport** | ID card | `A9999999` | identifier + structure |
| 6 | **Bank Statement** | bank | IFSC `AAAA0XXXXXX` | IFSC + transaction table + phrases |
| 7 | **Bank Passbook** | bank | IFSC | IFSC + passbook phrases |
| 8 | **Bank Cheque** | bank | IFSC | IFSC + cheque phrases (validity notice, A/C payee) |
| 9 | **Invoice** | receipt | GSTIN (15-char) | distinctive phrases + GSTIN anchor |
| 10 | **Insurance Receipt** | receipt | — | distinctive phrases (policy, premium, IRDAI) |
| 11 | **Road Tax Receipt** | receipt | vehicle reg | distinctive phrases + vehicle-reg anchor |

Three classification strategies, one per family:

- **ID cards** — detect a unique, fixed-format identifier and validate it
  (Aadhaar's Verhoeff checksum, PAN's structure, etc.).
- **Bank documents** — anchor on the IFSC, then a weighted contest of distinctive
  phrases plus a transaction-table signal to separate statement / passbook / cheque.
- **Receipt documents** — score on distinctive phrases, with an optional structured
  anchor where one exists: **GSTIN** (15 chars: state + embedded PAN + entity + Z +
  check) for invoices, and a **vehicle-registration number** for road-tax receipts.
  Insurance receipts have no standard identifier, so they are phrase-only.

A **document-context gate** protects all of this: because bank and receipt documents
are full of long numbers (account, CIF, GSTIN, policy, chassis) and a random 12-digit
string passes the Aadhaar checksum ~10% of the time, the presence of clear bank/receipt
markers caps ID-card scores — so a coincidental number collision can never be
misclassified as an Aadhaar/PAN/etc. Genuine ID cards carry none of these markers and
are unaffected.

---

## How it handles REAL documents (the v2 pipeline)

A real card is a photograph, not text. The engine deals with that in two ways:

**1. Image preprocessing before OCR** (`engine/preprocess.py`). Each page is
rendered at 400 DPI and turned into several cleaned-up variants:
`gentle` (sharpen only — best for stylised Aadhaar/passport number fonts),
`otsu` and `adaptive` (binarisation — best for coloured backgrounds),
`gray_upscaled`, `deskewed_otsu` (rotation correction), and `raw`.

**2. "Try several, keep the best"** (`engine/pipeline.py`). The engine OCRs each
variant (with two page-segmentation modes), classifies every result, and keeps
the one that yields a **valid** identifier. It early-exits the moment it gets a
confident, validated hit — so clean digital PDFs finish in ~10 ms and real cards
in a few seconds. A preprocessing variant that fails on one card simply loses to
one that works; it can never make the result worse.

**3. OCR-noise repair** (`engine/classifier.py`). Real OCR mangles characters
(`O`↔`0`, `A`↔`4`, `E`↔`3`), mis-spaces the Aadhaar 4-4-4 grouping, and injects
stray punctuation. The classifier coerces tokens toward each type's expected
shape and re-validates — but only when the document also carries matching context
keywords, so a misread date can't become a fake passport number.

---

## Why it's more than regex

Per candidate text, each document type gets a confidence score:

```
confidence =  0.55 · (a correctly-shaped identifier was found)
           +  0.30 · (that identifier passed validation / checksum)
           +  0.15 · (fraction of expected context keywords present)
```

The highest scorer wins; if even the best is below threshold (or two types tie),
the document is flagged `needs_human_review: true` — the human-in-the-loop hook
the BRD calls for (§7.11). This is what stops a bank statement's 12-digit account
number (matches the Aadhaar *shape*, but fails the **Verhoeff checksum** and has
no Aadhaar keywords) from being mislabelled.

---

## Pipeline

```
   PDF / image
       │
       ▼
┌──────────────────────────────────────────────────┐
│ EXTRACT  (extractor.py)                            │
│   digital text layer  → pdfplumber (instant)       │
│   else / also → render @400dpi → preprocess.py     │
│                 → OCR each variant × 2 PSM modes    │
└──────────────────────────────────────────────────┘
       │  one or more text candidates
       ▼
┌──────────────────────────────────────────────────┐
│ DETECT + REPAIR (identifiers.py, classifier.py)    │
│   per-type regex → candidate identifiers           │
│   + OCR-confusion repair, shape-aware, re-validated │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ VALIDATE (validators.py)                           │
│   Aadhaar → Verhoeff checksum                      │
│   PAN/Voter/DL/Passport → structural rules         │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ CLASSIFY + PICK BEST (classifier.py, pipeline.py)  │
│   multi-signal score; keep best validated candidate │
│   low/ambiguous → human review                     │
└──────────────────────────────────────────────────┘
       │
       ▼
     JSON result
```

---

## Setup (Linux)

```bash
sudo apt update
sudo apt install -y tesseract-ocr poppler-utils    # OCR + PDF rendering
# optional, for reading Hindi context text:  sudo apt install -y tesseract-ocr-hin

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The digital-PDF path works without Tesseract/Poppler; you only need them for
scanned/photographed documents (which is most real ones).

---

## Usage

### 1. Generate synthetic test documents (no real data needed)
```bash
python generate_samples.py            # REALISTIC card-like images (force OCR)
python generate_samples.py --simple   # clean text-only PDFs (fast sanity check)
python generate_samples.py --all       # both
```
All identifiers are randomly generated test fixtures — **not real documents**.

### 2. Classify
```bash
python cli.py samples/                    # whole folder
python cli.py samples/aadhaar_card.pdf    # one file
python cli.py photo.jpg                   # a phone photo
python cli.py samples/ --json             # full reasoning per document
python cli.py scan.pdf --lang eng+hin     # OCR with an extra language pack
python cli.py mydocs/ --no-ocr            # text-layer only (fast)
```

Example:
```
  aadhaar_card.pdf   ->  Aadhaar Card   conf=0.93  [714428179457 · valid]  (ocr:gentle/psm6, 5s)
  decoy_bank_stmt    ->  Unknown        conf=0.55  [— · not validated]     ⚠ REVIEW
```

### 3. As a library
```python
from engine import classify_file
r = classify_file("some_document.pdf")     # or .jpg/.png
print(r["decision"], r["confidence"], r["identifier"])
```

### 4. As a REST API
```bash
python api.py
curl -F "file=@samples/pan_card.pdf" http://127.0.0.1:7000/classify
```

### 5. Tests
```bash
python tests/test_engine.py        # or: python -m pytest tests/ -v
```

---

## Testing on YOUR real documents

```bash
mkdir mydocs
# copy COPIES of your document PDFs/photos in (one document per file)
python cli.py mydocs/
```

Real-document gotchas:
- **Encrypted e-Aadhaar/e-PAN** → returns `ERROR`. Decrypt first:
  `qpdf --decrypt --password=YOURPASS in.pdf out.pdf` (password = first 4 letters
  of name in CAPS + birth year), then classify `out.pdf`.
- **Masked Aadhaar** (`XXXX XXXX 1234`) → `UNKNOWN` (the checksum needs all 12 digits).
- **Glare / steep angle photos** → may land in `⚠ REVIEW`; re-shoot flatter and brighter.

When done: `rm -rf mydocs/` and don't keep the `--json` output (it contains
identifier numbers in plaintext).

---

## Project layout

```
doc-classifier/
├── README.md
├── requirements.txt
├── engine/
│   ├── __init__.py          public API: classify_file, classify_folder, classify_text
│   ├── identifiers.py       per-type regex, keywords, OCR-confusion repair maps
│   ├── validators.py        Verhoeff checksum + structural validators
│   ├── preprocess.py        OpenCV image cleanup variants for OCR   ← NEW in v2
│   ├── extractor.py         PDF/image → text candidates (text layer + multi-variant OCR)
│   ├── classifier.py        multi-signal scoring + OCR repair + decision
│   └── pipeline.py          orchestrator: try candidates, keep best
├── cli.py                   command-line interface
├── api.py                   Flask REST API
├── generate_samples.py      synthetic test-document generator (realistic + simple)
├── tests/
│   └── test_engine.py       14 unit tests
└── samples/                 generated test documents (after step 1)
```

---

## Honest limitations

This engine classifies by identifier + context, which is the right tool here:
deterministic, explainable, no training data needed. It will **not** be perfect on
every real card — masked Aadhaar, very low-quality photos, heavy security overprints,
or unusual state DL formats can still land in `⚠ REVIEW`. That is the safe failure
mode (route to a human), not a wrong answer. For pixel-perfect *digit* extraction
(vs. classification) you'd add the key-value extraction engine (BRD §7.5); for
layout/vision classification you'd add a LayoutLM/ViT signal inside
`classifier.score_document()` — the scoring is isolated in that one function so
nothing else changes.

---

## A note on data

The sample generator produces **synthetic** identifiers with valid structure purely
so the validation path can run. They are test fixtures, not anyone's identity. Route
real KYC documents only through access-controlled, PII-masked, audit-logged storage
(BRD §11) — never log raw identifier values in plaintext.

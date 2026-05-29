# Document Classification Engine — Indian KYC Documents

The first engine of the L&T Finance AI Document Intelligence platform (BRD §7.8).
It classifies single-document PDFs into one of five Indian KYC document types by
**detecting and validating the unique identifier** printed on each document.

| Document | Identifier | Format | Validation |
|----------|-----------|--------|------------|
| **Aadhaar** | 12 digits | `XXXX XXXX XXXX` | Verhoeff checksum + first digit 2–9 |
| **PAN** | 10 chars | `AAAAA9999A` | shape + valid holder-type char |
| **Voter ID** | 10 chars | `AAA9999999` | shape (3 letters + 7 digits) |
| **Driving Licence** | 15 chars | `AA9999999999999` | shape + valid RTO state code |
| **Passport** | 8 chars | `A9999999` | shape + valid prefix letter |

> Note on the Driving Licence: real Indian DLs carry a **2-letter state code + 13 digits**
> (e.g. `MH1220110012345`). The BRD says "15 digits"; the engine accepts **both** the
> canonical lettered form and a pure 15-digit form.

---

## Why this is more than regex

A naive engine would just pattern-match. This one runs a **multi-signal confidence model**:

```
confidence =  0.55 · (a correctly-shaped identifier was found)
           +  0.30 · (that identifier passed validation / checksum)
           +  0.15 · (fraction of expected context keywords present)
```

The result is robust against the two things that break document pipelines in production:

1. **Lookalike numbers.** A bank statement's 12-digit account number matches the
   Aadhaar *shape*, but fails the **Verhoeff checksum** and has no Aadhaar keywords,
   so it is correctly sent to human review instead of being mislabelled.
2. **OCR noise.** Scanned cards produce garbled text — `O`↔`0`, `l`↔`1`, stray `/`
   inside numbers. The engine runs an **OCR-repair pass** that coerces glyphs toward
   the expected shape and re-validates, but only when the document carries matching
   context keywords (so a misread date can't become a fake passport number).

When confidence is too low, or two types are too close, the document is flagged
`needs_human_review: true` — the human-in-the-loop hook the BRD calls for (§7.11).

---

## Pipeline

```
   PDF
    │
    ▼
┌─────────────────────────────────────────────┐
│ 1. EXTRACT  (engine/extractor.py)           │
│    digital text layer  → pdfplumber         │
│    if scanned/empty    → Tesseract OCR      │
└─────────────────────────────────────────────┘
    │  raw text
    ▼
┌─────────────────────────────────────────────┐
│ 2. DETECT   (engine/identifiers.py)         │
│    per-type regex → candidate identifiers   │
│    + OCR-repair pass for noisy scans        │
└─────────────────────────────────────────────┘
    │  candidate tokens
    ▼
┌─────────────────────────────────────────────┐
│ 3. VALIDATE (engine/validators.py)          │
│    Aadhaar → Verhoeff checksum              │
│    PAN/Voter/DL/Passport → structural rules │
└─────────────────────────────────────────────┘
    │  validated + scored
    ▼
┌─────────────────────────────────────────────┐
│ 4. CLASSIFY (engine/classifier.py)          │
│    multi-signal score → winner + confidence │
│    low/ambiguous → human review             │
└─────────────────────────────────────────────┘
    │
    ▼
   JSON result
```

---

## Setup

**Requirements:** Python 3.9+, and for the OCR path two system binaries:
- **Tesseract OCR** — [install guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)
  (Windows: download the installer; Mac: `brew install tesseract`; Ubuntu: `sudo apt install tesseract-ocr`)
- **Poppler** — (Windows: download poppler binaries and add to PATH; Mac: `brew install poppler`; Ubuntu: `sudo apt install poppler-utils`)

> The **digital-PDF path works without these** — you only need Tesseract + Poppler
> to classify *scanned/photographed* documents.

```bash
cd doc-classifier
pip install -r requirements.txt
```

---

## Usage

### 1. Generate synthetic test PDFs (no real data needed)
```bash
python generate_samples.py            # digital text PDFs
python generate_samples.py --scanned  # also image-only PDFs that force OCR
```
This writes one PDF per type (plus a decoy bank statement) to `samples/`.
All identifiers are randomly generated test fixtures — **not real documents**.

### 2. Classify
```bash
python cli.py samples/                       # classify a whole folder
python cli.py samples/aadhaar_card.pdf       # one file
python cli.py samples/ --json                # full machine-readable output
python cli.py scan.pdf --lang eng+hin        # OCR with an extra language pack
```

Example output:
```
  aadhaar_card.pdf      ->  Aadhaar Card     conf=1.00  [849467217616 · valid]  (text-layer, 8ms)
  decoy_bank_statement  ->  Unknown          conf=0.55  [— · not validated]     ⚠ REVIEW
```

### 3. As a library
```python
from engine import classify_pdf
result = classify_pdf("some_document.pdf")
print(result["decision"], result["confidence"], result["identifier"])
```

### 4. As a REST API
```bash
python api.py
# then:
curl -F "file=@samples/pan_card.pdf" http://127.0.0.1:7000/classify
```

### 5. Run the tests
```bash
python tests/test_engine.py
# or: python -m pytest tests/ -v
```

---

## Project layout

```
doc-classifier/
├── README.md
├── requirements.txt
├── engine/
│   ├── __init__.py          public API: classify_pdf, classify_folder, classify_text
│   ├── identifiers.py       per-type regex, keywords, OCR-repair shapes
│   ├── validators.py        Verhoeff checksum + structural validators
│   ├── extractor.py         PDF → text (digital + OCR fallback)
│   ├── classifier.py        multi-signal scoring + decision
│   └── pipeline.py          end-to-end orchestrator
├── cli.py                   command-line interface
├── api.py                   Flask REST API
├── generate_samples.py      synthetic test-PDF generator
├── tests/
│   └── test_engine.py       14 unit tests
└── samples/                 generated test PDFs (after step 1)
```

---

## Result schema

```json
{
  "file": "aadhaar_card.pdf",
  "ok": true,
  "decision": "AADHAAR",
  "display_name": "Aadhaar Card",
  "confidence": 1.0,
  "identifier": "849467217616",
  "identifier_valid": true,
  "needs_human_review": false,
  "extraction_method": "text-layer",
  "chars_extracted": 247,
  "elapsed_ms": 8,
  "ranked": [ { "doc_type": "...", "score": ..., "matched_keywords": [...] }, ... ]
}
```

---

## Where an ML model plugs in

This engine is deliberately rule + checksum + OCR driven, which is the right tool
for *identifier-based* classification: it is deterministic, explainable, and needs no
training data. The BRD also asks for layout/vision classification (§7.8). That slots in
as an additional signal in `classifier.score_document()` — add a `model_score` term
(e.g. from a fine-tuned LayoutLM or a Vision Transformer) alongside the existing
pattern/validation/keyword signals, and re-weight. The architecture already isolates
scoring in one function, so no other module changes.

---

## A note on data

The sample generator produces **synthetic** identifiers with valid structure purely so
the validation path can be exercised. They are test fixtures, not anyone's real identity
documents. In production, route real KYC documents through your existing access-controlled,
PII-masked, audit-logged storage (BRD §11) — never log raw identifier values in plaintext.

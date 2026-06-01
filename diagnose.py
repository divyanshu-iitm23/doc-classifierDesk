import sys
from engine.extractor import text_candidates
from engine.classifier import classify, _find_candidates
from engine import identifiers
import re

path = sys.argv[1]
print(f"\n=== DIAGNOSING {path} ===\n")

for text, method in text_candidates(path):
    print(f"\n----- variant: {method} -----")
    # show all alphanumeric tokens of plausible ID length
    toks = re.findall(r"[A-Z0-9][A-Z0-9 ]{6,18}[A-Z0-9]", text.upper())
    print("candidate tokens:", toks[:12])
    # what each doc type detects
    for dt, spec in identifiers.DOCUMENT_SPECS.items():
        cands = _find_candidates(text.upper(), spec, dt)
        if cands:
            print(f"   {dt}: {cands}")
    r = classify(text)
    print(f"   -> decision={r['decision']} conf={r['confidence']:.2f}")
    # only need the first couple of variants to diagnose
"""
api.py
------
REST API around the classification engine, so other LTF systems (LOS, SFDC,
the review portal) can call it over HTTP.

Run:
    python api.py
    # -> http://127.0.0.1:7000

Endpoints:
    GET  /health
    POST /classify        multipart/form-data with a 'file' field (a PDF)
    POST /classify-batch  multipart with multiple 'files'

Example:
    curl -F "file=@samples/pan_card.pdf" http://127.0.0.1:7000/classify
"""

import os
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS

from engine import classify_file

app = Flask(__name__)
CORS(app)

MAX_MB = 25
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


def _save_and_classify(file_storage, lang):
    suffix = os.path.splitext(file_storage.filename or "upload.pdf")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file_storage.save(tmp.name)
        tmp_path = tmp.name
    try:
        result = classify_file(tmp_path, ocr_lang=lang)
        result["file"] = file_storage.filename
        return result
    finally:
        os.unlink(tmp_path)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "doc-classifier", "version": "1.0.0"})


@app.route("/classify", methods=["POST"])
def classify_one():
    if "file" not in request.files:
        return jsonify({"error": "send a PDF in the 'file' field"}), 400
    lang = request.form.get("lang", "eng")
    result = _save_and_classify(request.files["file"], lang)
    return jsonify(result)


@app.route("/classify-batch", methods=["POST"])
def classify_many():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "send PDFs in the 'files' field"}), 400
    lang = request.form.get("lang", "eng")
    return jsonify([_save_and_classify(f, lang) for f in files])


if __name__ == "__main__":
    print("\n  Document Classification Engine API")
    print("  http://127.0.0.1:7000   (POST a PDF to /classify)\n")
    app.run(host="127.0.0.1", port=7000, debug=False)

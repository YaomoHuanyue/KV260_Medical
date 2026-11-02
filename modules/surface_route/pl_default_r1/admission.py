"""Bind the isolated source change without changing any sealed parent closure."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def candidate_sources():
    path=HERE/'inputs.json';record=json.loads(path.read_text())
    for name,wanted in record['source_SHA256'].items():
        p=(ROOT/name).resolve()
        if not p.is_relative_to(ROOT) or not p.is_file():raise RuntimeError('Missing surface PL input: '+name)
        with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=wanted:raise RuntimeError('Changed surface PL input: '+name)
    return hashlib.sha256(path.read_bytes()).hexdigest()

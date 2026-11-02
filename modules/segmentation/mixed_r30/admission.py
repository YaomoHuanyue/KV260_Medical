"""Explicit test admission for the measured-hybrid integration candidate."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    path=Path(path);temp=path.with_name(path.name+'.new')
    temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)
def verify(path,digest):
    path=Path(path).resolve(strict=True)
    if not path.is_relative_to(ROOT) or sha(path)!=digest:raise ValueError('Explicit hybrid admission SHA required')
    value=read(path)
    if (value.get('schema')!='kv260.explicit_hybrid.candidate.r30' or value.get('silent_PS_fallback') is not False
            or value.get('cleanup_backend')!='PS_original_clean_mask' or value.get('production_promoted') is not False):
        raise ValueError('Unsupported hybrid candidate policy')
    for name,digest in value['source_SHA256'].items():
        p=(ROOT/name).resolve(strict=True)
        if not p.is_relative_to(ROOT) or sha(p)!=digest:raise ValueError('Changed hybrid input: '+name)
    return value

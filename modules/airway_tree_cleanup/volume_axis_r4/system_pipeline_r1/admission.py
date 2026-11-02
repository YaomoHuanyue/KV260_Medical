"""Pin this candidate without altering protected released source/firmware."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
BINDING_SHA='2260ea1875d3921ef350fd4b92883872a4421ea14fa1a30e26f7550384a6d0a4'
def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    p=Path(p);t=p.with_name(p.name+'.new');t.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');t.replace(p)
def verify(path,digest):
    path=Path(path).resolve(strict=True)
    if not path.is_relative_to(ROOT)or sha(path)!=digest:raise ValueError('Explicit complete-B7 candidate admission SHA required')
    r=read(path)
    if r.get('schema')!='kv260.B7.complete_pipeline.candidate.v1'or r.get('performance_qualified')is not False:raise ValueError('Unsupported/inaccurate candidate status')
    for n,h in r['source_SHA256'].items():
        p=(ROOT/n).resolve(strict=True)
        if not p.is_relative_to(ROOT)or sha(p)!=h:raise ValueError('Changed complete-B7 candidate source: '+n)
    binding=HERE.parent/'runtime_binding.json'
    if sha(binding)!=BINDING_SHA:raise ValueError('Whole139-qualified B7 binding changed')
    return r

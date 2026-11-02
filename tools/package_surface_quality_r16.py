"""Transport the new sources without changing any sealed parent source."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    parent=json.loads((ROOT/'modules/surface_route/native_UI_source_closure_r15.json').read_text())['files_sha256']
    closure=ROOT/'modules/surface_route/native_UI_source_closure_r16.json'
    bound=json.loads(closure.read_text())['files_sha256']
    extra=['tools/surface_quality_trial_r16.py','tools/package_surface_quality_r16.py','modules/surface_route/test_quality_action_r16.py']
    for n in extra:bound[n]=hashlib.sha256((ROOT/n).read_bytes()).hexdigest()
    closure.write_text(json.dumps(dict(files_sha256=bound),indent=2)+'\n',encoding='utf-8')
    names=set(n for n,h in bound.items() if parent.get(n)!=h)|{closure.relative_to(ROOT).as_posix()}
    manifest={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
    archive=ROOT/'tools/surface_quality_r16_upload.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for n in manifest:z.write(ROOT/n,n)
        z.writestr('upload_manifest.json',json.dumps(manifest))
    print(json.dumps(dict(archive=archive.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),count=len(manifest))))
if __name__=='__main__':main()

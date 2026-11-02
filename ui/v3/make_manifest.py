"""在板上生成 V3 发布清单（ui/v3/manifest.json）。
以正式 V2 清单为基础：静态区、固件、后端文件哈希原样继承，并先逐个重新核对与 V2 清单一致；
再加入 V3 自身的二进制、源码/QML 与 speedup_r1 后端文件哈希。V2 文件不做任何修改。"""
from pathlib import Path
import hashlib,json,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
v2p=ROOT/'ui/v2/manifest.json';v2=json.loads(v2p.read_bytes())
# 继承的后端文件必须与 V2 清单完全一致，否则拒绝生成
for name,h in {**v2['backend_files_sha256'],**v2.get('installed_backend_files_sha256',{})}.items():
    assert sha(ROOT/name)==h,'backend file changed since V2: '+name
own=[p for p in sorted(HERE.rglob('*')) if p.is_file() and p.relative_to(HERE).parts[0] in ('src','qml','assets','tools')]
own+= [HERE/n for n in ('qml.qrc','build.py','runtime.py','make_manifest.py','hdmi_preview.py')]
files={str(p.relative_to(ROOT)):sha(p) for p in own}
files.update({n:h for n,h in v2['files_sha256'].items() if not n.startswith('ui/v2/')})
speedup={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'modules/segmentation/speedup_r1').glob('*.py'))}
d=dict(v2)
d.update(schema='kv260.native_UI_V3.v1',name='native_UI_V3_production',binary='ui/v3/bin/medical_ui',binary_sha256=sha(ROOT/'ui/v3/bin/medical_ui'),
         files_sha256=files,backend_files_sha256={**v2['backend_files_sha256'],**speedup},manual_launcher='ui/v3/runtime.py',
         superseded_ui_sha256=sorted(set(v2['superseded_ui_sha256'])|{v2['binary_sha256']}),
         launch_backend_dependencies=['ui/v3/runtime.py','ui/v3/build.py','ui/releases/feature_completion_r6/backend_core_r6.py'],
         prior_UI_manifest='ui/v2/manifest.json',prior_UI_manifest_SHA256=sha(v2p),
         ui_promotion=dict(date='2026-11-01',basis='user HDMI acceptance of the V3 candidate',rollback='set "ui": "v2" in system/autostart/profile.json and restart kv260-medical-ui.service'),
         speedup_backend=dict(entry='modules/segmentation/speedup_r1/backend.py',used_by='V3 run button (KV260_SPEEDUP!=0)',
                              outputs_identical_to='modules/segmentation/reader_burst/backend.py',evidence='maintenance/speedup/README.md'),
         generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
for k in ('CXX_source_files',):d[k]=len([n for n in files if n.endswith(('.cpp','.hpp','.inc'))])
pending=HERE/'manifest.json.pending';pending.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');pending.replace(HERE/'manifest.json')
print(json.dumps(dict(binary_sha256=d['binary_sha256'],files=len(files),backend_files=len(d['backend_files_sha256']),prior=d['prior_UI_manifest_SHA256'])))

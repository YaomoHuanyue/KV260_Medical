"""Derive complete-scene transport while preserving accepted production sources."""
from pathlib import Path
import hashlib
import json
from modules.surface_route.derive_scene_r9 import replace_once

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT/'ui/releases/feature_completion_r6/src'


def main():
    parents = {name:hashlib.sha256((FOLDER/name).read_bytes()).hexdigest()
               for name in ('pl_scope.hpp', 'pl_scope.cpp')}
    header = (FOLDER/'pl_scope.hpp').read_text(encoding='utf-8')
    header = replace_once(header, ' void start(QString result,QJsonObject pose);',
        ' void start(QString result,QJsonObject pose);\n'
        ' void startScene(QString bundle,QString revision,QJsonObject pose);')
    cpp = (FOLDER/'pl_scope.cpp').read_text(encoding='utf-8')
    cpp = replace_once(cpp, '#include "pl_scope.hpp"',
        '#include "pl_scope_complete_r9.hpp"\n'
        '#include "../../../../modules/surface_route/scope_protocol_r9.hpp"')
    cpp = replace_once(cpp, 'QString root,source,frameFile,module;',
        'QString root,source,frameFile,module,sceneRevision,sceneScalar;')
    cpp = replace_once(cpp, ' void start(QString result,QJsonObject pose);',
        ' void start(QString result,QJsonObject pose);\n'
        ' void startScene(QString bundle,QString revision,QJsonObject pose);\n'
        ' void startFor(QString selected,QString result,QString revision,QJsonObject pose);')
    cpp = replace_once(cpp, 'void PlScopeTransport::start(QString result,QJsonObject pose){\n ++intent;',
        'void PlScopeTransport::start(QString result,QJsonObject pose){\n'
        ' startFor(qEnvironmentVariable("KV260_SCOPE_MODULE","visualization"),result,QString(),pose);\n}\n'
        'void PlScopeTransport::startScene(QString bundle,QString revision,QJsonObject pose){\n'
        ' startFor("surface_quality",bundle,revision,pose);\n}\n'
        'void PlScopeTransport::startFor(QString selected,QString result,QString revision,QJsonObject pose){\n ++intent;')
    cpp = replace_once(cpp, 'if(source==result&&!stopping)',
        'if(source==result&&module==selected&&sceneRevision==revision&&!stopping)')
    cpp = replace_once(cpp, 'afterStop.append([this,result,pose,wanted]{if(wanted==intent)start(result,pose);});',
        'afterStop.append([this,selected,result,revision,pose,wanted]{if(wanted==intent)startFor(selected,result,revision,pose);});')
    cpp = replace_once(cpp, ' if(module!="visualization"&&module!="surface")',
        ' module=selected;sceneRevision=revision;sceneScalar.clear();\n'
        ' if(module=="surface_quality"){\n'
        '  QFile sceneFile(result+"/scene.json");\n'
        '  if(!sceneFile.open(QIODevice::ReadOnly)){if(onActive)onActive(false,uiIntent);return;}\n'
        '  auto m=QJsonDocument::fromJson(sceneFile.readAll()).object();sceneScalar=m["renderer_scalar_sha256"].toString();\n'
        '  if(m["schema"].toString()!="kv260.surface_route.complete_scene.v1"||!m["complete"].toBool()\n'
        '     ||m["revision"].toString()!=revision||revision.size()!=64||sceneScalar.size()!=64){\n'
        '   if(onActive)onActive(false,uiIntent);if(onStatus)onStatus("Complete scene revision mismatch");return;}\n'
        ' }\n'
        ' if(module!="visualization"&&module!="surface"&&module!="surface_quality")')
    cpp = replace_once(cpp,
        ' process.start(root+"/.venv/bin/python",{root+"/dfx/"+module+"/worker.py","--result",result,"--frame",frameFile});',
        ' if(module=="surface_quality")process.start(root+"/.venv/bin/python",{root+"/modules/surface_route/quality_worker_r9.py",\n'
        '   "--bundle",result,"--revision",sceneRevision,"--frame",frameFile});\n'
        ' else process.start(root+"/.venv/bin/python",{root+"/dfx/"+module+"/worker.py","--result",result,"--frame",frameFile});')
    cpp = replace_once(cpp, ' sentPose=req;roundTrip.restart();',
        ' if(!sceneRevision.isEmpty())req["revision"]=sceneRevision;\n sentPose=req;roundTrip.restart();')
    cpp = replace_once(cpp, 'if(event=="ready"){ready=true;send();}',
        'if(event=="ready"){\n'
        '   if(module=="surface_quality"&&!CompleteScopeProtocol::ready(o,sceneRevision)){\n'
        '    if(onStatus)onStatus("Complete scene ready revision mismatch");stop();continue;}\n'
        '   ready=true;send();}')
    old = '   o["camera_lps"]=sentPose["camera"];o["arc_mm"]=sentPose["arc_mm"];o["requested_camera"]=sentPose;o["pose_source"]="completed_PL_frame";'
    cpp = replace_once(cpp, old,
        '   if(module=="surface_quality"){\n'
        '    if(!CompleteScopeProtocol::frame(o,sentPose,sceneRevision,sceneScalar,frameFile)){\n'
        '     if(onStatus)onStatus("Complete scene frame/pose identity mismatch; image rejected");stop();continue;}\n'
        '   }else{'+old.strip()+'}\n')
    marker = 'void PlScope::request(QJsonObject pose)'
    cpp = replace_once(cpp, marker,
        'void PlScope::startScene(QString bundle,QString revision,QJsonObject pose){\n'
        ' const auto serial=++intent;running=true;acceptFrames=true;\n'
        ' QMetaObject::invokeMethod(io,[this,bundle,revision,pose,serial]{io->uiIntent=serial;io->startScene(bundle,revision,pose);},Qt::QueuedConnection);\n'
        '}\n'+marker)
    outputs = {}
    for name, text in [('pl_scope_complete_r9.hpp', header), ('pl_scope_complete_r9.cpp', cpp)]:
        with (FOLDER/name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
        outputs[name] = hashlib.sha256((FOLDER/name).read_bytes()).hexdigest()
    proof = dict(parents=parents, outputs=outputs, production_sources_unchanged=True,
                 changes=['explicit C9 bundle/revision selection', 'strict ready/frame scalar and pose pairing',
                          'cooperative stop and one-frame/latest-pose transport preserved'])
    with (Path(__file__).parent/'transport_derivation_r9.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(proof, indent=2)+'\n')


if __name__ == '__main__':
    main()

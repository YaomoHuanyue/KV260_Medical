"""Derive a separate UI from the final accepted R3 integration, once only."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'ui/releases/feature_completion_r3'
NEW=ROOT/'ui/releases/feature_completion_r4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def replace(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)


def main():
    assert not NEW.exists()
    copies={
        'src/main_namespace_fixed_r4.cpp':'src/main_catalogue_r1.cpp',
        'backend_r4.py':'backend_r1.py',
        'backend_core_r3.py':'backend_core_r1.py',
        'complete_import_r4.py':'complete_import_r1.py',
        'complete_features_r4.py':'complete_features_r1.py',
        'analysis_partial.py':'analysis_partial.py',
        'reconstruction_partial.py':'reconstruction_partial.py',
        'run_r4.sh':'run_r1.sh',
        'verify_partial_numerics.py':'verify_partial_numerics.py',
        'run_regressions_namespace_fixed_r5.py':'run_regressions_r1.py',
        'test_regressions_with_restore_r5.sh':'test_regressions_with_restore_r1.sh',
    }
    for p in (OLD/'src').iterdir():
        if p.suffix in ('.inc','.hpp') or p.name in ('views.cpp','pl_scope.cpp','pl_composite.cpp'):
            copies[p.relative_to(OLD).as_posix()]=p.relative_to(OLD).as_posix()
    originals={p.relative_to(ROOT).as_posix():sha(p) for p in [OLD/a for a in copies]}
    original_build=json.loads((OLD/'build_r4/build.json').read_text(encoding='utf-8'))
    assert sha(OLD/'build_r4/medical_ui')==original_build['binary_sha256']
    NEW.mkdir(parents=True)
    for a,b in copies.items():
        text=(OLD/a).read_text(encoding='utf-8')
        for old,new in (('feature_completion_r3','feature_completion_r4'),
                        ('backend_core_r3','backend_core_r1'),('backend_r4.py','backend_r1.py'),
                        ('complete_import_r4','complete_import_r1'),('complete_features_r4','complete_features_r1'),
                        ('build_r4','build_r1'),('run_r4.sh','run_r1.sh'),
                        ('run_regressions_namespace_fixed_r5.py','run_regressions_r1.py')):
            text=text.replace(old,new)
        p=NEW/b;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8',newline='\n')
    p=NEW/'src/main_catalogue_r1.cpp';text=p.read_text(encoding='utf-8')
    text=replace(text,'QDoubleSpinBox*diameter,*margin,*minimumBend;',
                 'QDoubleSpinBox*minimumCandidateVolume=nullptr;QDoubleSpinBox*diameter,*margin,*minimumBend;')
    text=replace(text,'!scene["candidates"].toArray().isEmpty()&&',
                 'lesionList&&lesionList->count()>0&&')
    text=replace(text,'if(minimumBend)minimumBend->setEnabled(!value);',
                 'if(minimumBend)minimumBend->setEnabled(!value);if(minimumCandidateVolume)minimumCandidateVolume->setEnabled(!value);if(focusButton)focusButton->setEnabled(!value&&!source.isEmpty()&&lesionList->count()>0);')
    old=next(line for line in text.splitlines() if line.startswith('  lesionList->blockSignals(true);'))
    text=replace(text,old,'  refreshCandidates();')
    text=replace(text,'lesion->setRange(0,999);','lesion->setRange(-1,1000000000);')
    text=replace(text,'form->addRow(u("目标候选"),lesionList);',
        'form->addRow(u("目标候选"),lesionList);minimumCandidateVolume=new QDoubleSpinBox;'
        'minimumCandidateVolume->setRange(0,1.e9);minimumCandidateVolume->setDecimals(1);'
        'minimumCandidateVolume->setValue(14);minimumCandidateVolume->setSuffix(u(" mm³"));'
        'minimumCandidateVolume->setToolTip(u("按原始体素的物理体积筛选候选，0 显示全部；不修改分割或重建模型。"));'
        'form->addRow(u("最小候选体积"),minimumCandidateVolume);')
    text=replace(text,'candidateInfo->setText(u("当前结果没有病灶候选"));return;',
        'lesion->setValue(-1);for(auto*v:{overview,miniOverview})v->selectCandidate(-1);'
        'candidateInfo->setText(scene["candidates"].toArray().isEmpty()?u("当前结果没有病灶候选"):u("当前体积筛选无候选；降低阈值可恢复"));'
        'updateAnalysis();busy(processing());return;')
    text=replace(text,'break;}}updateAnalysis();}','break;}}updateAnalysis();busy(processing());}')
    anchor=' void updateCandidate(){'
    method=''' void refreshCandidates(){
  int previous=lesion->value();lesionList->blockSignals(true);lesionList->clear();
  for(auto value:scene["candidates"].toArray()){auto c=value.toObject();
   if(c["volume_mm3"].toDouble()<minimumCandidateVolume->value())continue;
   int id=c["index"].toInt();lesionList->addItem(QString(u("候选 #%1 · %2 mm³")).arg(id).arg(c["volume_mm3"].toDouble(),0,'f',1),id);
  }
  int selected=lesionList->findData(previous);lesionList->setCurrentIndex(selected>=0?selected:0);
  lesionList->blockSignals(false);updateCandidate();
 }
#include "catalogue_test.inc"
'''
    text=replace(text,anchor,method+anchor)
    text=replace(text,'connect(focusButton,&QPushButton::clicked,this,[this]{focusCandidate();});',
        'connect(minimumCandidateVolume,QOverload<double>::of(&QDoubleSpinBox::valueChanged),this,[this]{refreshCandidates();});'
        'connect(focusButton,&QPushButton::clicked,this,[this]{focusCandidate();});')
    text=replace(text,'"--result",source,"--destination",path});',
        '"--result",source,"--destination",path,"--minimum-candidate-volume",QString::number(minimumCandidateVolume->value(),\'g\',15)});')
    text=replace(text,'if(missingDataTesting){QTimer::singleShot',
        'if(qEnvironmentVariableIntValue("KV260_CATALOGUE_UI_TEST")==1){QTimer::singleShot(400,this,[this]{catalogueTest();});}else if(missingDataTesting){QTimer::singleShot')
    text=replace(text,'result["schema"]=="kv260.export.v3"','result["schema"]=="kv260.export.v4"')
    text=replace(text,'ticks-exportStartTick>=2;','ticks-exportStartTick>=2&&result["lesion_catalogue_state"]=="retained_candidates"&&QFileInfo::exists(folder+"/lesions/lesion_labels.nrrd");')
    p.write_text(text,encoding='utf-8',newline='\n')
    p=NEW/'complete_features_r1.py';text=p.read_text(encoding='utf-8')
    text=replace(text,"p.add_argument('--result',type=Path);p.add_argument('--destination',type=Path)",
        "p.add_argument('--result',type=Path);p.add_argument('--destination',type=Path)\n    p.add_argument('--minimum-candidate-volume',type=float,default=14.)")
    text=replace(text,'from modules.surface_export.bundle import export_bundle',
                 'from modules.lesion_catalogue.bundle import export_bundle\n        import SimpleITK as sitk')
    text=replace(text,'report=export_bundle(a.result,a.destination,sha(a.input))',
        'report=export_bundle(a.result,a.destination,sha(a.input),a.minimum_candidate_volume,sitk.ReadImage(str(a.input)))')
    text=replace(text,"schema=report['schema'],surface_export_seconds=report['surface_export_seconds'])",
        "schema=report['schema'],surface_export_seconds=report['surface_export_seconds'],\n            lesion_catalogue_state=report['lesion_catalogue_state'],minimum_candidate_volume_mm3=report['minimum_candidate_volume_mm3'])")
    p.write_text(text,encoding='utf-8',newline='\n')
    # Derive only the original enrich_scene body. Run one CCL and retain the
    # exact planner/CT grid and its strict accepted UI geometry guard.
    analysis=ROOT/'ui/features/analysis.py';body=analysis.read_text(encoding='utf-8').split('def enrich_scene(',1)[1]
    body=body.replace("meta['candidates']=candidates(sitk.GetArrayFromImage(mi)>0,image)",
        "report,_=catalogue(sitk.GetArrayViewFromImage(mi),image,0.,False)\n    meta['candidates']=report['rows']\n    meta['candidate_catalogue']=report")
    optional=(NEW/'analysis_partial.py').read_text(encoding='utf-8')
    optional=optional.replace('from features.analysis import enrich_scene as enrich_complete',
        'import numpy as np\nimport json\nfrom modules.lesion_catalogue.catalogue import catalogue')
    (NEW/'analysis_partial.py').write_text(optional+'\n\ndef enrich_complete('+body,encoding='utf-8',newline='\n')
    p=NEW/'backend_core_r1.py';text=p.read_text(encoding='utf-8')
    text=replace(text,"'result': str(result)}", "'result': str(result), 'lesion_catalogue':sha(ROOT/'modules/lesion_catalogue/catalogue.py')}")
    p.write_text(text,encoding='utf-8',newline='\n')
    test=NEW/'run_regressions_r1.py';text=test.read_text(encoding='utf-8')
    text=replace(text,"'KV260_MISSING_DATA_TEST','KV260_PARTIAL_IMPORT_NAMES')",
                 "'KV260_MISSING_DATA_TEST','KV260_PARTIAL_IMPORT_NAMES','KV260_CATALOGUE_UI_TEST')")
    text=replace(text,"    tests=[\n", "    tests=[\n        ('candidate_volume_filter','KV260_CATALOGUE_UI_TEST',[],'catalogue_UI.json',\n         'passed_actual_Qt_candidate_filter_identity_and_empty_recovery',ct,{}),\n")
    text=text.replace('regression_summary_r2.json','regression_summary_r1.json').replace('evidence_r2','evidence_r1')
    text=text.replace("f'{name}_r2.log'","f'{name}_r1.log'").replace('all_eighteen','all_nineteen').replace('All eighteen','All nineteen')
    text=text.replace("C2_R5_new_bitstream_tested=False","C2_R8_new_bitstream_tested=False")
    test.write_text(text,encoding='utf-8',newline='\n')
    p=NEW/'test_regressions_with_restore_r1.sh';text=p.read_text(encoding='utf-8').replace('_r2.json','_r1.json').replace('_r2.log','_r1.log')
    p.write_text(text,encoding='utf-8',newline='\n')
    shared={n:d for n,d in original_build['shared_source_sha256'].items() if not n.startswith('ui/releases/feature_completion_r3/')}
    shared['ui/features/analysis.py']=sha(analysis)
    for p in (ROOT/'modules/lesion_catalogue').glob('*.py'):shared[p.relative_to(ROOT).as_posix()]=sha(p)
    origin=dict(status='separate_catalogue_UI_derived_sources_prepared_not_compiled',
        old_source_sha256=originals,original_R3_binary_sha256=original_build['binary_sha256'],
        accepted_UI_binary_sha256=sha(ROOT/'ui/build/medical_ui'),
        C9_release_sha256=sha(ROOT/'dfx/surface_quality/release/manifest.json'),
        shared_source_sha256=shared,analysis_enrichment_origin_sha256=sha(analysis),
        runtime_old_candidate_imports=False,PL_algorithms_changed=False)
    (NEW/'derivation_origin.json').write_text(json.dumps(origin,indent=2)+'\n',encoding='utf-8')
    print(origin['status'])


if __name__=='__main__':main()

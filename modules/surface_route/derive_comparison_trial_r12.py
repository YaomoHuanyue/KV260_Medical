"""Derive one independently measured root-proof reuse trial, preserving R11."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from modules.surface_route.bundle_r8 import sha,write_json
from modules.surface_route.derive_scene_r9 import replace_once


def main():
    parent=ROOT/'modules/surface_route/own_CT_comparison_r11.py'
    text=replace_once(parent.read_text(),
        'from modules.surface_route.comparison_r11 import Comparison, solve_all',
        'from modules.surface_route.comparison_r12 import Comparison\nfrom modules.surface_route.comparison_r11 import solve_all')
    text=replace_once(text,"k!='exact_wall_query_reuse'","k not in ('exact_wall_query_reuse','root_winding_query_reuse')")
    text=replace_once(text,'comparison_source_closure_r11.json','comparison_source_closure_r12.json')
    target=parent.with_name('own_CT_comparison_r12.py')
    with target.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    supervisor=ROOT/'tools/comparison_trial_r11.py'
    new=supervisor.read_text().replace('r11','r12')
    target_supervisor=supervisor.with_name('comparison_trial_r12.py')
    with target_supervisor.open('x',encoding='utf-8',newline='\n') as f:f.write(new)
    doc=ROOT/'modules/surface_route/comparison_derivation_r12.json'
    write_json(doc,dict(parent_sha256=sha(parent),output_sha256=sha(target),
        parent_supervisor_sha256=sha(supervisor),output_supervisor_sha256=sha(target_supervisor),
        changes=['reuse original immutable exact root winding','exclude optimization counters from semantic report equality',
                 'separate source closure and evidence directories'],R11_sources_unchanged=True))
    prior=ROOT/'modules/surface_route/comparison_source_closure_r11.json'
    closure=json.loads(prior.read_text())
    for p,h in closure['files_sha256'].items():assert sha(ROOT/p)==h,p
    names=[target,target_supervisor,Path(__file__),doc,ROOT/'modules/surface_route/comparison_r12.py',
           ROOT/'modules/surface_route/test_comparison_r12.py',prior]
    closure['files_sha256'].update({p.relative_to(ROOT).as_posix():sha(p) for p in names})
    closure['previous_comparison_closure_sha256']=sha(prior)
    write_json(ROOT/'modules/surface_route/comparison_source_closure_r12.json',closure)


if __name__=='__main__':main()

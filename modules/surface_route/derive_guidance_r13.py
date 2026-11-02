"""Keep the sealed R5 ownership/aperture implementation; replace arc mapping only."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
source=HERE/'guidance_r5.py'
output=HERE/'guidance_r13.py'
receipt=HERE/'guidance_derivation_r13.json'
assert not output.exists() and not receipt.exists()
text=source.read_text(encoding='utf-8')
begin=text.index('def source_node_arcs(c, route):')
end=text.index('\ndef field_aperture(',begin)
replacement=('from modules.surface_route.selected_surface_r13 import selected_node_arcs as source_node_arcs\n\n')
derived=text[:begin]+replacement+text[end:]
output.write_text(derived,encoding='utf-8',newline='\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt.write_text(json.dumps(dict(parent=source.name,parent_sha256=sha(source),
    output=output.name,output_sha256=sha(output),
    changed='source_node_arcs only: exact retained selected-curve producer parameter and audited prefix',
    original_field_aperture_branch_ownership_target_mapping_and_cue_body_unchanged=True),indent=2)+'\n',encoding='utf-8')

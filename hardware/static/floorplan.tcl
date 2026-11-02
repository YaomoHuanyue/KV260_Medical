# Resource-site ranges deliberately exclude the PS8 hard block and BUFG sites.
# CLOCKREGION ranges alone accidentally put the PS into the RP's exclusion area.
create_pblock pblock_rp
add_cells_to_pblock [get_pblocks pblock_rp] [get_cells rp]
foreach cr [get_clock_regions] {
 if {$cr in {X0Y0 X1Y0}} {continue}
 foreach pattern {SLICE_* DSP48E2_* RAMB36_* RAMB18_* URAM288_*} {
  set sites [get_sites -quiet -of_objects $cr -filter "NAME =~ $pattern"]
  if {![llength $sites]} {continue}
  set minx 9999;set miny 9999;set maxx -1;set maxy -1
  foreach site $sites {
   if {![regexp {(.+)_X([0-9]+)Y([0-9]+)$} $site _ prefix x y]} {error "Unexpected site $site"}
   set minx [expr {min($minx,$x)}];set miny [expr {min($miny,$y)}]
   set maxx [expr {max($maxx,$x)}];set maxy [expr {max($maxy,$y)}]
  }
  resize_pblock [get_pblocks pblock_rp] -add ${prefix}_X${minx}Y${miny}:${prefix}_X${maxx}Y${maxy}
 }
}
set_property SNAPPING_MODE ON [get_pblocks pblock_rp]
set_property RESET_AFTER_RECONFIG true [get_pblocks pblock_rp]

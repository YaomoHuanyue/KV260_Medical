# Complete C5 pool candidate; all input files belong to one admitted task.
if {![info exists ::env(POOL_OWNED_ROOT)]} {error "Exact owned task root is required"}
set owned [file normalize $::env(POOL_OWNED_ROOT)]
set source_root [file normalize [file dirname [info script]]]
if {![string match -nocase "${owned}/workspace/*" $source_root]} {error "Source outside owned task"}
if {[version -short] ne "2025.2.1"} {error "Wrong same-version tool"}
if {![file exists [file join $owned i admission_verified.json]]} {error "Complete pre-route qualification is required"}
set_param general.maxThreads 4
set out [file join $owned b route]
if {[file exists $out]} {error "Existing route must not be overwritten"}
file mkdir $out
open_checkpoint [file join $owned i static_routed.dcp]
read_checkpoint -cell rp -strict [file join $owned i ct_pool_synth.dcp]
opt_design
place_design
if {[catch {route_design} route_error]} {
 catch {report_route_status -file [file join $out failed_route_status.rpt]}
 catch {write_checkpoint -force [file join $out failed_route.dcp]}
 error $route_error
}
report_timing_summary -file [file join $out timing_ct_tensor_r3.rpt]
report_utilization -hierarchical -file [file join $out utilization_ct_tensor_r3.rpt]
report_utilization -pblocks pblock_rp -file [file join $out capacity_ct_tensor_r3.rpt]
report_drc -file [file join $out drc_ct_tensor_r3.rpt]
foreach type {max min} {
 set paths [get_timing_paths -delay_type $type -max_paths 1]
 if {![llength $paths] || [get_property SLACK [lindex $paths 0]] < 0} {error "C5 pool $type timing failed"}
}
foreach violation [get_drc_violations] {
 if {[get_property SEVERITY $violation] in {Error {Critical Warning}}} {error "Unresolved C5 pool DRC: $violation"}
}
write_checkpoint -force [file join $out config_ct_tensor_r3.dcp]
foreach reference {mc smooth edt route ct} {
 pr_verify -full_check [file join $owned i config_${reference}.dcp] [file join $out config_ct_tensor_r3.dcp] -file [file join $out pr_verify_ct_tensor_r3_${reference}.log]
}
write_bitstream -force -bin_file [file join $out config_ct_tensor_r3.bit]
set fp [open [file join $out OFFLINE_COMPLETE_ct_tensor_r3.txt] w]
puts $fp "C5 pool candidate routed and all five frozen configurations checked; board equality and speed remain required."
close $fp
close_project

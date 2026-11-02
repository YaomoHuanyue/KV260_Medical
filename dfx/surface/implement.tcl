set root [file normalize [file dirname [info script]]]
set base [exec C:/Python314/python.exe -c {from pathlib import Path;print((Path.cwd().resolve().parent/'medical/build').as_posix())}]
set out [file join $root build]
set_param general.maxThreads 4
open_checkpoint [file join $base static_routed.dcp]
read_checkpoint -cell rp -strict [file join $out rm_scope_synth.dcp]
opt_design;place_design;route_design
report_timing_summary -file [file join $out timing.rpt]
report_utilization -hierarchical -file [file join $out utilization.rpt]
report_drc -file [file join $out drc.rpt]
write_checkpoint -force [file join $out config_scope.dcp]
foreach type {max min} {
 set paths [get_timing_paths -delay_type $type -max_paths 1]
 if {![llength $paths] || [get_property SLACK [lindex $paths 0]]<0} {error "Scope $type timing failed"}
}
pr_verify -full_check [file join $base config_smooth.dcp] [file join $out config_scope.dcp] -file [file join $out pr_verify.log]
write_bitstream -force -bin_file [file join $out config_scope.bit]
set f [open [file join $out OFFLINE_COMPLETE.txt] w];puts $f "Routed and compatible. Board test still required.";close $f
close_project

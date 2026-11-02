set root [file normalize [file dirname [info script]]]
set base [file normalize [file join $root .. .. medical build]]
set out [file join $root build]
set_param general.maxThreads 4
if {[version -short] ne "2025.2.1"} {error "Wrong same-version tool"}
open_checkpoint [file join $base static_routed.dcp]
read_checkpoint -cell rp -strict [file join $root input qualified_shared_fma2_r1_RM.dcp]
opt_design;opt_design -control_set_merge;place_design -directive Explore;route_design
report_timing_summary -file [file join $out timing_shared_fma2_r1.rpt]
report_utilization -hierarchical -file [file join $out utilization_shared_fma2_r1.rpt]
report_drc -file [file join $out drc_shared_fma2_r1.rpt]
write_checkpoint -force [file join $out config_smooth_shared_fma2_r1.dcp]
foreach type {max min} {
 set paths [get_timing_paths -delay_type $type -max_paths 1]
 if {![llength $paths] || [get_property SLACK [lindex $paths 0]]<0} {error "C2 R11 $type timing failed"}
}
pr_verify -full_check [file join $base config_smooth.dcp] [file join $out config_smooth_shared_fma2_r1.dcp] -file [file join $out pr_verify_shared_fma2_r1.log]
write_bitstream -force -bin_file [file join $out config_smooth_shared_fma2_r1.bit]
set f [open [file join $out OFFLINE_COMPLETE_shared_fma2_r1.txt] w];puts $f "100MHz route and full PR compatibility passed; board test pending.";close $f
close_project

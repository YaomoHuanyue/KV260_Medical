# Offline D9 candidate only. No board, driver, static design or release mutation.
set root [file normalize [file dirname [info script]]]
set base [file normalize [file join $root .. .. medical build]]
set out [file join $root build]
set_param general.maxThreads 4
if {[version -short] ne "2025.2.1"} {error "Wrong same-version tool"}
if {![file exists [file join $root input admission_verified.json]]} {error "Missing checked D9 offline admission"}
file mkdir $out
open_checkpoint [file join $base static_routed.dcp]
read_checkpoint -cell rp -strict [file join $root input qualified_D9_RM.dcp]
opt_design
opt_design -control_set_merge
place_design -directive Explore
route_design
report_timing_summary -file [file join $out timing_D9_r1.rpt]
report_utilization -hierarchical -file [file join $out utilization_D9_r1.rpt]
report_drc -file [file join $out drc_D9_r1.rpt]
write_checkpoint -force [file join $out config_smooth_D9_r1.dcp]
foreach type {max min} {
    set paths [get_timing_paths -delay_type $type -max_paths 1]
    if {![llength $paths] || [get_property SLACK [lindex $paths 0]] < 0} {error "D9 $type timing failed"}
}
foreach reference {mc smooth edt route ct} {
    pr_verify -full_check [file join $base config_${reference}.dcp] [file join $out config_smooth_D9_r1.dcp] -file [file join $out pr_verify_D9_r1_${reference}.log]
}
write_bitstream -force -bin_file [file join $out config_smooth_D9_r1.bit]
set report [open [file join $out OFFLINE_COMPLETE_D9_r1.txt] w]
puts $report "Offline D9 100MHz route and five full PR reference checks completed; ARM/XRT, board correctness and PS4 speed gates remain."
close $report
close_project

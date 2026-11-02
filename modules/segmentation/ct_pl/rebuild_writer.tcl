set root [file normalize [file dirname [info script]]]
set out [file join $root build vivado_parallel128_debug]
open_project [file join $out ct_segmentation.xpr]
open_bd_design [get_files design_1.bd]
update_ip_catalog -rebuild
upgrade_bd_cells [get_bd_cells ct_writer_0]
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
reset_run design_1_ct_writer_0_0_synth_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {![string match "*Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Implementation failed"}
set synth_log [open [file join $out ct_segmentation.runs synth_1 runme.log] r]
set synth_text [read $synth_log];close $synth_log
if {[regexp {CRITICAL WARNING:.*unconnected pin} $synth_text]} {error "Unconnected interface pin; refusing release"}
open_run impl_1
report_timing_summary -file [file join $root build timing_summary.rpt]
report_utilization -file [file join $root build utilization.rpt]
foreach mode {max min} {
 set p [get_timing_paths -quiet -delay_type $mode -max_paths 1]
 if {[llength $p]==0 || [get_property SLACK [lindex $p 0]]<0} {error "Timing closure failed: $mode"}
}
set release [file join $root build release];file mkdir $release
file copy -force [file join $out ct_segmentation.runs impl_1 design_1_wrapper.bit] [file join $release ct_segmentation.bit]
file copy -force [file join $out ct_segmentation.gen sources_1 bd design_1 hw_handoff design_1.hwh] [file join $release ct_segmentation.hwh]
puts "RELEASE_READY: $release"
close_project


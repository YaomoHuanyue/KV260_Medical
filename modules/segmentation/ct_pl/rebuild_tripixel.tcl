set_param general.maxThreads 4
set root [file normalize [file dirname [info script]]]
set out [file join $root build vivado_parallel128_debug]
open_project [file join $out ct_segmentation.xpr]
open_bd_design [get_files design_1.bd]
set_property ip_repo_paths [list [file join $root build wide_input ct_reader hls impl ip] [file join $root build tripixel ct_conv hls impl ip] [file join $root build fusion component hls impl ip]] [current_project]
update_ip_catalog -rebuild
upgrade_bd_cells [get_bd_cells ct_conv_0]
set_property CONFIG.C_M_AXI_MEMORY_DATA_WIDTH 256 [get_bd_cells ct_reader_0]
set_property CONFIG.TDATA_NUM_BYTES 32 [get_bd_cells pixels_fifo]
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
reset_run design_1_ct_conv_0_0_synth_1
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
if {![string match "*Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Implementation failed"}
set f [open [file join $out ct_segmentation.runs synth_1 runme.log] r]
set s [read $f];close $f
if {[regexp {CRITICAL WARNING:.*unconnected pin} $s]} {error "Unconnected interface pin; refusing release"}
open_run impl_1
report_timing_summary -file [file join $root build tripixel timing_summary.rpt]
report_utilization -file [file join $root build tripixel utilization.rpt]
foreach mode {max min} {
 set p [get_timing_paths -quiet -delay_type $mode -max_paths 1]
 if {[llength $p]==0 || [get_property SLACK [lindex $p 0]]<0} {error "Timing closure failed: $mode"}
}
set release [file join $root build release_tripixel];file mkdir $release
file copy -force [file join $out ct_segmentation.runs impl_1 design_1_wrapper.bit] [file join $release ct_segmentation.bit]
file copy -force [file join $out ct_segmentation.gen sources_1 bd design_1 hw_handoff design_1.hwh] [file join $release ct_segmentation.hwh]
puts "RELEASE_READY: $release"
close_project

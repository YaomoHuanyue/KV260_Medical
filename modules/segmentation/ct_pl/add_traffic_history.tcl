set root [file normalize [file dirname [info script]]]
set out [file join $root build vivado_parallel128_debug]
open_project [file join $out ct_segmentation.xpr]
open_bd_design [get_files design_1.bd]
set_property -dict [list CONFIG.C_ALL_INPUTS {0} CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_TRI_DEFAULT {0xFFFFFFFF}] [get_bd_cells stream_status]
# C_TRI_DEFAULT keeps channel 1 input-only at the pins, while DATA writes
# select a diagnostic page through the independent output latch.
add_files -norecurse [file join $root stream_monitor.v]
update_compile_order -fileset sources_1
create_bd_cell -type module -reference stream_monitor traffic_history
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins traffic_history/clk]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins traffic_history/resetn]
connect_bd_net [get_bd_pins status_bits/dout] [get_bd_pins traffic_history/signals]
connect_bd_net [get_bd_pins stream_status/gpio_io_o] [get_bd_pins traffic_history/page]
connect_bd_net [get_bd_pins traffic_history/value] [get_bd_pins stream_status/gpio2_io_i]
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
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

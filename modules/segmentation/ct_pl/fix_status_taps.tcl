set root [file normalize [file dirname [info script]]]
set out [file join $root build vivado_parallel128_debug]
open_project [file join $out ct_segmentation.xpr]
open_bd_design [get_files design_1.bd]
set debug_pins {
 ct_reader_0/m_axi_memory_ARVALID memory_bus/S00_AXI_arready memory_bus/S00_AXI_rvalid ct_reader_0/m_axi_memory_RREADY
 ct_conv_0/m_axi_memory_ARVALID memory_bus/S01_AXI_arready memory_bus/S01_AXI_rvalid ct_conv_0/m_axi_memory_RREADY
 ct_writer_0/m_axi_memory_AWVALID memory_bus/S02_AXI_awready ct_writer_0/m_axi_memory_WVALID memory_bus/S02_AXI_wready
 memory_bus/S02_AXI_bvalid ct_writer_0/m_axi_memory_BREADY
 ct_reader_0/pixels_TVALID pixels_fifo/s_axis_tready pixels_fifo/m_axis_tvalid ct_conv_0/pixels_TREADY
 ct_conv_0/sums_TVALID sums_fifo/s_axis_tready sums_fifo/m_axis_tvalid ct_writer_0/sums_TREADY
 memory_bus/M00_AXI_arvalid ps/saxigp2_arready ps/saxigp2_rvalid memory_bus/M00_AXI_rready
 memory_bus/M00_AXI_awvalid ps/saxigp2_awready memory_bus/M00_AXI_wvalid ps/saxigp2_wready ps/saxigp2_bvalid memory_bus/M00_AXI_bready
}
set debug_sinks {
memory_bus/S00_AXI_arvalid ct_reader_0/m_axi_memory_ARREADY ct_reader_0/m_axi_memory_RVALID memory_bus/S00_AXI_rready
memory_bus/S01_AXI_arvalid ct_conv_0/m_axi_memory_ARREADY ct_conv_0/m_axi_memory_RVALID memory_bus/S01_AXI_rready
memory_bus/S02_AXI_awvalid ct_writer_0/m_axi_memory_AWREADY memory_bus/S02_AXI_wvalid ct_writer_0/m_axi_memory_WREADY ct_writer_0/m_axi_memory_BVALID memory_bus/S02_AXI_bready
pixels_fifo/s_axis_tvalid ct_reader_0/pixels_TREADY ct_conv_0/pixels_TVALID pixels_fifo/m_axis_tready
sums_fifo/s_axis_tvalid ct_conv_0/sums_TREADY ct_writer_0/sums_TVALID sums_fifo/m_axis_tready
ps/saxigp2_arvalid memory_bus/M00_AXI_arready memory_bus/M00_AXI_rvalid ps/saxigp2_rready
ps/saxigp2_awvalid memory_bus/M00_AXI_awready ps/saxigp2_wvalid memory_bus/M00_AXI_wready memory_bus/M00_AXI_bvalid ps/saxigp2_bready
}
set n 0
foreach pin $debug_pins sink $debug_sinks {
 connect_bd_net [get_bd_pins $pin] [get_bd_pins $sink] [get_bd_pins status_bits/In$n]
 incr n
}
validate_bd_design
save_bd_design
generate_target all [get_files design_1.bd]
reset_run synth_1
launch_runs impl_1 -to_step write_bitstream -jobs 1
wait_on_run impl_1
set log [open [file join $out ct_segmentation.runs synth_1 runme.log] r]
set content [read $log];close $log
if {[regexp {CRITICAL WARNING:.*unconnected pin} $content]} {error "Unconnected monitored interface pin"}
if {![string match "*Complete*" [get_property STATUS [get_runs impl_1]]]} {error "Implementation failed"}
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

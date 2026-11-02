# Independent CT segmentation accelerator. No reconstruction IP or project dependency.
set root [file normalize [file dirname [info script]]]
set out [file join $root build vivado_parallel128_debug]
file mkdir $out
create_project ct_segmentation $out -part xck26-sfvc784-2LV-c -force
set boards [get_board_parts -quiet xilinx.com:kv260_som:part0:*]
if {[llength $boards]==0} {error "KV260 SOM preset missing"}
set_property board_part [lindex [lsort -dictionary $boards] end] [current_project]
set repos {}
foreach ip {ct_reader ct_conv ct_writer} {lappend repos [file join $root build $ip hls impl ip]}
set_property ip_repo_paths $repos [current_project]
update_ip_catalog
create_bd_design design_1
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 ps
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} [get_bd_cells ps]
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {0} CONFIG.PSU__USE__M_AXI_GP1 {0} CONFIG.PSU__USE__M_AXI_GP2 {1} \
 CONFIG.PSU__USE__S_AXI_GP0 {0} CONFIG.PSU__USE__S_AXI_GP1 {0} CONFIG.PSU__USE__S_AXI_GP2 {1} \
 CONFIG.PSU__MAXIGP2__DATA_WIDTH {32} CONFIG.PSU__SAXIGP2__DATA_WIDTH {128} \
 CONFIG.PSU__FPGA_PL0_ENABLE {1} CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] [get_bd_cells ps]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 control_bus
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {4}] [get_bd_cells control_bus]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 memory_bus
set_property CONFIG.NUM_SI {3} [get_bd_cells memory_bus]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0} CONFIG.C_AUX_RESET_HIGH {1}] [get_bd_cells rst]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
set_property CONFIG.CONST_VAL {1} [get_bd_cells one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells zero]
connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_LPD] [get_bd_intf_pins control_bus/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins memory_bus/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0_FPD]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/maxihpm0_lpd_aclk] [get_bd_pins ps/saxihp0_fpd_aclk] [get_bd_pins control_bus/aclk] [get_bd_pins memory_bus/aclk] [get_bd_pins rst/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins rst/ext_reset_in]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/aux_reset_in] [get_bd_pins rst/mb_debug_sys_rst]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins control_bus/aresetn] [get_bd_pins memory_bus/aresetn]
set i 0
foreach ip {ct_reader ct_conv ct_writer} {
 create_bd_cell -type ip -vlnv xilinx.com:hls:$ip:1.0 ${ip}_0
 connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ${ip}_0/ap_clk]
 connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins ${ip}_0/ap_rst_n]
 connect_bd_intf_net [get_bd_intf_pins control_bus/[format M%02d_AXI $i]] [get_bd_intf_pins ${ip}_0/s_axi_control]
 connect_bd_intf_net [get_bd_intf_pins ${ip}_0/m_axi_memory] [get_bd_intf_pins memory_bus/[format S%02d_AXI $i]]
 incr i
}
foreach {name bytes} {pixels_fifo 8 sums_fifo 32} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 $name
 set_property -dict [list CONFIG.TDATA_NUM_BYTES $bytes CONFIG.FIFO_DEPTH {64} CONFIG.HAS_TKEEP {1} CONFIG.HAS_TSTRB {1} CONFIG.HAS_TLAST {1}] [get_bd_cells $name]
 connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins $name/s_axis_aclk]
 connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins $name/s_axis_aresetn]
}
connect_bd_intf_net [get_bd_intf_pins ct_reader_0/pixels] [get_bd_intf_pins pixels_fifo/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins pixels_fifo/M_AXIS] [get_bd_intf_pins ct_conv_0/pixels]
connect_bd_intf_net [get_bd_intf_pins ct_conv_0/sums] [get_bd_intf_pins sums_fifo/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins sums_fifo/M_AXIS] [get_bd_intf_pins ct_writer_0/sums]
# Read-only handshake observability at 0x80030000; no extra XRT compute unit.
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 stream_status
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_INPUTS {0} CONFIG.C_IS_DUAL {1} CONFIG.C_GPIO2_WIDTH {32} CONFIG.C_ALL_INPUTS_2 {1} CONFIG.C_TRI_DEFAULT {0xFFFFFFFF}] [get_bd_cells stream_status]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins stream_status/s_axi_aclk]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins stream_status/s_axi_aresetn]
connect_bd_intf_net [get_bd_intf_pins control_bus/M03_AXI] [get_bd_intf_pins stream_status/S_AXI]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 status_bits
set_property CONFIG.NUM_PORTS {32} [get_bd_cells status_bits]
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
connect_bd_net [get_bd_pins status_bits/dout] [get_bd_pins stream_status/gpio_io_i]
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
assign_bd_address
set_property offset 0x81030000 [get_bd_addr_segs ps/Data/SEG_stream_status_Reg]
set i 0
foreach ip {ct_reader ct_conv ct_writer} {set_property offset [format 0x%x [expr {0x81000000+0x10000*$i}]] [get_bd_addr_segs ps/Data/SEG_${ip}_0_Reg];incr i}
set i 0
foreach ip {ct_reader ct_conv ct_writer} {
 set seg [get_bd_addr_segs ps/Data/SEG_${ip}_0_Reg]
 set_property offset [format 0x%x [expr {0x80000000+0x10000*$i}]] $seg
 set_property range 64K $seg
 incr i
}
set_property offset 0x80030000 [get_bd_addr_segs ps/Data/SEG_stream_status_Reg]
set_property range 64K [get_bd_addr_segs ps/Data/SEG_stream_status_Reg]
validate_bd_design
save_bd_design
set bd [get_files design_1.bd]
generate_target all $bd
make_wrapper -files $bd -top
add_files -norecurse [file join $out ct_segmentation.gen sources_1 bd design_1 hdl design_1_wrapper.v]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1
# Parallel Vivado workers intermittently fail during Tcl app initialization on
# this Windows installation. Serial IP launches completed the verified build.
launch_runs impl_1 -to_step write_bitstream -jobs 1
if {[catch {wait_on_run impl_1} e]} {
 puts "Retrying failed workers once serially: $e"
 foreach run [get_runs] {if {[string match -nocase *error* [get_property STATUS $run]]} {reset_run $run}}
 reset_run impl_1
 launch_runs impl_1 -to_step write_bitstream -jobs 1
 wait_on_run impl_1
}
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

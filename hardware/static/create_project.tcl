if {[version -short] ne "2025.2.1"} {error "Require Vivado 2025.2.1"}
# Recreate the accepted static source design. Does not program the board.
set repo [file normalize [file join [file dirname [info script]] ../..]]
set root [file join $repo dfx medical]
set out [file join $repo build fpga_static];file mkdir $out
set part xck26-sfvc784-2LV-c
create_project dfx_medical [file join $out project] -part $part -force
set boards [get_board_parts -quiet xilinx.com:kv260_som:part0:*]
if {![llength $boards]} {error "KV260 board preset missing"}
set_property board_part xilinx.com:kv260_som:part0:1.4 [current_project]
set repos {}
foreach ip {dfx_reader dfx_writer} {lappend repos [file join $root ip $ip]}
set_property ip_repo_paths $repos [current_project];update_ip_catalog
create_bd_design system_ps
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 ps
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} [get_bd_cells ps]
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 0 CONFIG.PSU__USE__M_AXI_GP1 0 CONFIG.PSU__USE__M_AXI_GP2 1 CONFIG.PSU__USE__S_AXI_GP0 0 CONFIG.PSU__USE__S_AXI_GP1 0 CONFIG.PSU__USE__S_AXI_GP2 1 CONFIG.PSU__SAXIGP2__DATA_WIDTH 128 CONFIG.PSU__MAXIGP2__DATA_WIDTH 32 CONFIG.PSU__FPGA_PL0_ENABLE 1 CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ 100] [get_bd_cells ps]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 control
set_property -dict [list CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO_WIDTH 32 CONFIG.C_GPIO2_WIDTH 32 CONFIG.C_ALL_OUTPUTS 1 CONFIG.C_ALL_INPUTS_2 1 CONFIG.C_DOUT_DEFAULT 0x00000001 CONFIG.C_INTERRUPT_PRESENT 0] [get_bd_cells control]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 control_bus
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 4] [get_bd_cells control_bus]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
set_property -dict [list CONFIG.C_EXT_RESET_HIGH 0 CONFIG.C_AUX_RESET_HIGH 1] [get_bd_cells rst]
foreach {name value} {one 1 zero 0} {create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 $name;set_property CONFIG.CONST_VAL $value [get_bd_cells $name]}
connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_LPD] [get_bd_intf_pins control_bus/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins control_bus/M00_AXI] [get_bd_intf_pins control/S_AXI]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 memory_bus
set_property CONFIG.NUM_SI 3 [get_bd_cells memory_bus]
connect_bd_intf_net [get_bd_intf_pins memory_bus/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0_FPD]
foreach {ip index} {dfx_reader 1 dfx_writer 2} {
 create_bd_cell -type ip -vlnv xilinx.com:hls:${ip}:1.0 $ip
 connect_bd_intf_net [get_bd_intf_pins control_bus/[format M%02d_AXI $index]] [get_bd_intf_pins $ip/s_axi_control]
 connect_bd_intf_net [get_bd_intf_pins $ip/m_axi_memory] [get_bd_intf_pins memory_bus/[format S%02d_AXI [expr {$index-1}]]]
 connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins $ip/ap_clk]
 connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins $ip/ap_rst_n]
}
# Static shutdown managers protect BOTH directions at the RM boundary.
foreach {cell master protocol width address} {control_guard false AXI4LITE 32 16 memory_guard true AXI4MM 128 40} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:dfx_axi_shutdown_manager:1.0 $cell
 set_property -dict [list CONFIG.RP_IS_MASTER $master CONFIG.CTRL_INTERFACE_TYPE 0 CONFIG.DP_PROTOCOL $protocol CONFIG.DP_AXI_DATA_WIDTH $width CONFIG.DP_AXI_ADDR_WIDTH $address CONFIG.DP_AXI_ID_WIDTH 0 CONFIG.DP_AXI_RESP 2] [get_bd_cells $cell]
 connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins $cell/clk]
 connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins $cell/resetn]
}
connect_bd_intf_net [get_bd_intf_pins control_bus/M03_AXI] [get_bd_intf_pins control_guard/S_AXI]
connect_bd_intf_net [get_bd_intf_pins memory_guard/M_AXI] [get_bd_intf_pins memory_bus/S02_AXI]
make_bd_intf_pins_external [get_bd_intf_pins control_guard/M_AXI];set_property name control [get_bd_intf_ports M_AXI_0]
make_bd_intf_pins_external [get_bd_intf_pins memory_guard/S_AXI];set_property name memory [get_bd_intf_ports S_AXI_0]
set_property CONFIG.FREQ_HZ 99999001 [get_bd_intf_ports {control memory}]
create_bd_port -dir I shutdown_request
create_bd_port -dir O control_shutdown
create_bd_port -dir O memory_shutdown
connect_bd_net [get_bd_ports shutdown_request] [get_bd_pins control_guard/request_shutdown] [get_bd_pins memory_guard/request_shutdown]
connect_bd_net [get_bd_ports control_shutdown] [get_bd_pins control_guard/in_shutdown]
connect_bd_net [get_bd_ports memory_shutdown] [get_bd_pins memory_guard/in_shutdown]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins memory_bus/aclk] [get_bd_pins ps/saxihp0_fpd_aclk]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins memory_bus/aresetn]
make_bd_intf_pins_external [get_bd_intf_pins dfx_reader/output_r];set_property name tx [get_bd_intf_ports output_r_0]
make_bd_intf_pins_external [get_bd_intf_pins dfx_writer/input_r];set_property name rx [get_bd_intf_ports input_r_0]
set_property CONFIG.FREQ_HZ 99999001 [get_bd_intf_ports {tx rx}]
create_bd_port -dir O -type clk clk
create_bd_port -dir O -type rst resetn
create_bd_port -dir O -from 31 -to 0 cfg
create_bd_port -dir I -from 31 -to 0 status
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/maxihpm0_lpd_aclk] [get_bd_pins control_bus/aclk] [get_bd_pins control/s_axi_aclk] [get_bd_pins rst/slowest_sync_clk] [get_bd_ports clk]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins rst/ext_reset_in]
connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/aux_reset_in] [get_bd_pins rst/mb_debug_sys_rst]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins control_bus/aresetn] [get_bd_pins control/s_axi_aresetn] [get_bd_ports resetn]
connect_bd_net [get_bd_pins control/gpio_io_o] [get_bd_ports cfg]
connect_bd_net [get_bd_pins control/gpio2_io_i] [get_bd_ports status]
assign_bd_address -offset 0x80000000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs control/S_AXI/Reg]
assign_bd_address -offset 0x80010000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs dfx_reader/s_axi_control/Reg]
assign_bd_address -offset 0x80020000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs dfx_writer/s_axi_control/Reg]
assign_bd_address -offset 0x80030000 -range 64K -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs control/Reg]
assign_bd_address
validate_bd_design;save_bd_design
set bd [get_files system_ps.bd];generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set python python
if {[info exists ::env(PYTHON)]} {set python $::env(PYTHON)}
set ::env(KV260_STATIC_BUILD) $out
exec $python [file join $repo hardware static generate_wrapper.py] static [lindex $wrapper 0]
file copy -force [file join $repo hardware static rp_stub.v] [file join $out rm_stub.v]
add_files [list [file join $out system_top.v] [file join $out rm_stub.v] [file join $root rtl medical_guard.v]]
set_property top system_top [current_fileset]
set_property PR_FLOW true [current_project]
update_compile_order -fileset sources_1
puts "KV260_MINIMAL_STATIC_PROJECT_READY"

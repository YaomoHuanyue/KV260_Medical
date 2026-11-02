if {![info exists ::env(PYTHON)]} {set ::env(PYTHON) python}
set _git_repo [file normalize [file join [file dirname [info script]] ../..]]
set root [file join $_git_repo dfx/edt_volume]
set out [file join $root build]
create_project rm_volume [file join $out project] -part xck26-sfvc784-2LV-c -force
set_property ip_repo_paths [list [file join $_git_repo build hls edt hls impl ip]] [current_project]
update_ip_catalog
create_bd_design algorithm_volume
create_bd_cell -type ip -vlnv xilinx.com:hls:edt_volume:1.0 core
create_bd_port -dir I -type clk clk
set_property CONFIG.FREQ_HZ 100000000 [get_bd_ports clk]
create_bd_port -dir I -type rst resetn
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_ports resetn]
create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:aximm_rtl:1.0 control
set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.ADDR_WIDTH 16 CONFIG.DATA_WIDTH 32 CONFIG.FREQ_HZ 100000000 CONFIG.HAS_PROT 0] [get_bd_intf_ports control]
connect_bd_intf_net [get_bd_intf_ports control] [get_bd_intf_pins core/s_axi_control]
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 memory
set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 40 CONFIG.DATA_WIDTH 128 CONFIG.FREQ_HZ 100000000 CONFIG.NUM_READ_OUTSTANDING 16 CONFIG.NUM_WRITE_OUTSTANDING 16] [get_bd_intf_ports memory]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 mem
set_property CONFIG.NUM_SI 1 [get_bd_cells mem]
connect_bd_intf_net [get_bd_intf_pins core/m_axi_memory] [get_bd_intf_pins mem/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins mem/M00_AXI] [get_bd_intf_ports memory]
connect_bd_net [get_bd_ports clk] [get_bd_pins core/ap_clk] [get_bd_pins mem/aclk]
connect_bd_net [get_bd_ports resetn] [get_bd_pins core/ap_rst_n] [get_bd_pins mem/aresetn]
set_property CONFIG.ASSOCIATED_BUSIF control:memory [get_bd_ports clk]
set_property CONFIG.ASSOCIATED_RESET resetn [get_bd_ports clk]
assign_bd_address -offset 0 -range 64K -target_address_space [get_bd_addr_spaces control] [get_bd_addr_segs core/s_axi_control/Reg]
assign_bd_address -offset 0 -range 4G -target_address_space [get_bd_addr_spaces core/Data_m_axi_memory] [get_bd_addr_segs memory/Reg]
validate_bd_design
save_bd_design
set bd [get_files algorithm_volume.bd]
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
exec $::env(PYTHON) -E [file join $root generate_wrapper.py] [lindex $wrapper 0]
add_files [file join $out rm_medical.v]
set_property top rm_medical [current_fileset]
update_compile_order -fileset sources_1
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]

puts "KV260_GIT_RM_READY edt"

if {![info exists ::env(PYTHON)]} {set ::env(PYTHON) python}
set _git_repo [file normalize [file join [file dirname [info script]] ../..]]
set root [file join $_git_repo dfx/surface]
create_project rm_scope [file join $root build project] -part xck26-sfvc784-2LV-c -force
set_property ip_repo_paths [list [file join $_git_repo build hls surface hls impl ip]] [current_project]
update_ip_catalog
create_bd_design algorithm_scope
create_bd_cell -type ip -vlnv xilinx.com:hls:scope_visual:1.0 core
create_bd_port -dir I -type clk clk
set_property CONFIG.FREQ_HZ 100000000 [get_bd_ports clk]
create_bd_port -dir I -type rst resetn
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_ports resetn]
create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:aximm_rtl:1.0 control
set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.ADDR_WIDTH 16 CONFIG.DATA_WIDTH 32 CONFIG.FREQ_HZ 100000000 CONFIG.HAS_PROT 0] [get_bd_intf_ports control]
connect_bd_intf_net [get_bd_intf_ports control] [get_bd_intf_pins core/s_axi_control]
foreach {name mode pin} {stream_in Slave input_r stream_out Master output_r} {
 create_bd_intf_port -mode $mode -vlnv xilinx.com:interface:axis_rtl:1.0 $name
 set_property -dict [list CONFIG.TDATA_NUM_BYTES 64 CONFIG.TUSER_WIDTH 1 CONFIG.HAS_TKEEP 1 CONFIG.HAS_TSTRB 1 CONFIG.HAS_TLAST 1 CONFIG.FREQ_HZ 100000000] [get_bd_intf_ports $name]
 set p [get_bd_intf_pins -quiet core/$pin]
 if {![llength $p]} {set p [get_bd_intf_pins core/[string trimright $pin _r]]}
 connect_bd_intf_net [get_bd_intf_ports $name] $p
}
connect_bd_net [get_bd_ports clk] [get_bd_pins core/ap_clk]
connect_bd_net [get_bd_ports resetn] [get_bd_pins core/ap_rst_n]
set_property CONFIG.ASSOCIATED_BUSIF control:stream_in:stream_out [get_bd_ports clk]
set_property CONFIG.ASSOCIATED_RESET resetn [get_bd_ports clk]
assign_bd_address -offset 0 -range 64K -target_address_space [get_bd_addr_spaces control] [get_bd_addr_segs core/s_axi_control/Reg]
validate_bd_design;save_bd_design
set bd [get_files algorithm_scope.bd];generate_target all $bd
set wrapper [make_wrapper -files $bd -top];add_files -norecurse $wrapper
exec $::env(PYTHON) [file join $root generate_wrapper.py] [lindex $wrapper 0]
add_files [file join $root build rm_medical.v]
set_property top rm_medical [current_fileset]
update_compile_order -fileset sources_1
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]

puts "KV260_GIT_RM_READY surface"

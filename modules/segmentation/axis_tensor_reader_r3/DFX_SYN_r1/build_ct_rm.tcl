set root [file normalize [file dirname [info script]]]
if {![info exists ::env(POOL_TASK_PYTHON)] || ![info exists ::env(POOL_OWNED_ROOT)]} {error "Owned task paths required"}
set owned [file normalize $::env(POOL_OWNED_ROOT)]
if {![string match -nocase "${owned}/workspace/*" $root]} {error "Source is outside the exact owned task"}
foreach kind {r c w} {
 if {![file exists [file join $owned i $kind component.xml]]} {error "Missing verified packaged IP $kind"}
}
if {![file exists [file join $root inputs rp_ports.json]]} {error "Frozen RP boundary is required"}
if {[file exists [file join $owned b p]]} {error "Do not overwrite an existing build"}
set out [file join $owned b];file mkdir $out
create_project p [file join $out p] -part xck26-sfvc784-2LV-c -force
set_property ip_repo_paths [list [file join $owned i r] [file join $owned i c] [file join $owned i w]] [current_project]
update_ip_catalog
create_bd_design a
foreach role {reader conv writer} {
 if {$role eq "writer"} {set kind ct_writer_pool} elseif {$role eq "reader"} {set kind ct_tensor_reader} else {set kind ct_${role}}
 create_bd_cell -type ip -vlnv xilinx.com:hls:${kind}:1.0 $role
}
if {[get_property CONFIG.ADDR_WIDTH [get_bd_intf_pins writer/s_axi_control]] != 8} {error "Pool writer requires 8 control address bits"}
if {[get_property CONFIG.ADDR_WIDTH [get_bd_intf_pins reader/s_axi_control]] != 8} {error "R3 reader requires 8 control address bits"}
create_bd_port -dir I -type clk clk
set_property CONFIG.FREQ_HZ 100000000 [get_bd_ports clk]
create_bd_port -dir I -type rst resetn
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_ports resetn]
create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:aximm_rtl:1.0 control
set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.ADDR_WIDTH 16 CONFIG.DATA_WIDTH 32 CONFIG.FREQ_HZ 100000000 CONFIG.HAS_PROT 0] [get_bd_intf_ports control]
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 memory
set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 40 CONFIG.DATA_WIDTH 128 CONFIG.FREQ_HZ 100000000 CONFIG.NUM_READ_OUTSTANDING 16 CONFIG.NUM_WRITE_OUTSTANDING 16] [get_bd_intf_ports memory]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 ctrl
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 3] [get_bd_cells ctrl]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 mem
set_property CONFIG.NUM_SI 3 [get_bd_cells mem]
connect_bd_intf_net [get_bd_intf_ports control] [get_bd_intf_pins ctrl/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins mem/M00_AXI] [get_bd_intf_ports memory]
set i 0
foreach role {reader conv writer} {
 connect_bd_intf_net [get_bd_intf_pins ctrl/[format M%02d_AXI $i]] [get_bd_intf_pins $role/s_axi_control]
 connect_bd_intf_net [get_bd_intf_pins $role/m_axi_memory] [get_bd_intf_pins mem/[format S%02d_AXI $i]]
 connect_bd_net [get_bd_ports clk] [get_bd_pins $role/ap_clk]
 connect_bd_net [get_bd_ports resetn] [get_bd_pins $role/ap_rst_n]
 assign_bd_address -offset [expr {$i*4096}] -range 4K -target_address_space [get_bd_addr_spaces control] [get_bd_addr_segs $role/s_axi_control/Reg]
 assign_bd_address -offset 0 -range 4G -target_address_space [get_bd_addr_spaces $role/Data_m_axi_memory] [get_bd_addr_segs memory/Reg]
 incr i
}
foreach cell {ctrl mem} {
 connect_bd_net [get_bd_ports clk] [get_bd_pins $cell/aclk]
 connect_bd_net [get_bd_ports resetn] [get_bd_pins $cell/aresetn]
}
foreach {name src dst} {pixels reader/pixels conv/pixels sums conv/sums writer/sums} {
 create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 $name
 set_property -dict [list CONFIG.FIFO_DEPTH 64 CONFIG.TDATA_NUM_BYTES 32 CONFIG.HAS_TKEEP 1 CONFIG.HAS_TSTRB 1 CONFIG.HAS_TLAST 1] [get_bd_cells $name]
 connect_bd_intf_net [get_bd_intf_pins $src] [get_bd_intf_pins $name/S_AXIS]
 connect_bd_intf_net [get_bd_intf_pins $name/M_AXIS] [get_bd_intf_pins $dst]
 connect_bd_net [get_bd_ports clk] [get_bd_pins $name/s_axis_aclk]
 connect_bd_net [get_bd_ports resetn] [get_bd_pins $name/s_axis_aresetn]
}
set_property CONFIG.ASSOCIATED_BUSIF control:memory [get_bd_ports clk]
set_property CONFIG.ASSOCIATED_RESET resetn [get_bd_ports clk]
validate_bd_design;save_bd_design
set bd [get_files a.bd];generate_target all $bd
set wrapper [make_wrapper -files $bd -top];add_files -norecurse $wrapper
exec $::env(POOL_TASK_PYTHON) [file join $root generate_wrapper.py] [file join $root inputs rp_ports.json] [lindex $wrapper 0] [file join $out rm_medical.v]
add_files [file join $out rm_medical.v]
set_property top rm_medical [current_fileset]
update_compile_order -fileset sources_1
if {[lindex $argv 0] eq "validate"} {
 puts "PASS CT BD, control map, DDR and common RP boundary validation"
 close_project
 exit
}
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]
launch_runs synth_1 -jobs 2;wait_on_run synth_1
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "CT RM synthesis failed"}
open_run synth_1
write_checkpoint -force [file join $out rm_ct_synth.dcp]
report_utilization -hierarchical -file [file join $out rm_ct_synth_util.rpt]
close_project

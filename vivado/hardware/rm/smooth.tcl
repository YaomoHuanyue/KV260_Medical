# Run only inside a bounded owned build. Requires an officially packaged,
# SHA-bound mesh_smooth_axis HLS IP tree at $root/p/component/hls/impl/ip.
set _git_repo [file normalize [file join [file dirname [info script]] ../..]]
set root [file join $_git_repo modules/reconstruction/smooth_pipeline_r2/axis_tile1024_r1/dfx_candidate_r2]
if {[version -short] ne "2025.2.1"} {error "Require exact static-platform tool version"}
set profile [file join $_git_repo hardware rm profile]
set out [file join $root build project];file mkdir $out
set_param general.maxThreads 1
create_project p $out -part xck26-sfvc784-2LV-c
set_property ip_repo_paths [list [file join $_git_repo build hls smooth hls impl ip]] [current_project]
update_ip_catalog
create_bd_design a
create_bd_cell -type ip -vlnv xilinx.com:hls:mesh_smooth_axis:1.0 core
create_bd_port -dir I -type clk clk
set_property CONFIG.FREQ_HZ 100000000 [get_bd_ports clk]
create_bd_port -dir I -type rst resetn
set_property CONFIG.POLARITY ACTIVE_LOW [get_bd_ports resetn]
create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:aximm_rtl:1.0 control
set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.ADDR_WIDTH 16 CONFIG.DATA_WIDTH 32 CONFIG.FREQ_HZ 100000000 CONFIG.HAS_PROT 0] [get_bd_intf_ports control]
connect_bd_intf_net [get_bd_intf_ports control] [get_bd_intf_pins core/s_axi_control]
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:aximm_rtl:1.0 memory
set_property -dict [list CONFIG.PROTOCOL AXI4 CONFIG.ADDR_WIDTH 40 CONFIG.DATA_WIDTH 128 CONFIG.FREQ_HZ 100000000 CONFIG.NUM_READ_OUTSTANDING 16 CONFIG.NUM_WRITE_OUTSTANDING 16] [get_bd_intf_ports memory]
set bundles {row_mem coords meta face_mem}
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 mem
set_property CONFIG.NUM_SI [llength $bundles] [get_bd_cells mem]
set i 0
foreach bundle $bundles {
 connect_bd_intf_net [get_bd_intf_pins core/m_axi_$bundle] [get_bd_intf_pins mem/[format S%02d_AXI $i]]
 incr i
}
connect_bd_intf_net [get_bd_intf_pins mem/M00_AXI] [get_bd_intf_ports memory]
foreach {name mode pin} {s Slave input_r m Master output_r} {
 create_bd_intf_port -mode $mode -vlnv xilinx.com:interface:axis_rtl:1.0 $name
 set_property -dict [list CONFIG.TDATA_NUM_BYTES 64 CONFIG.TUSER_WIDTH 1 CONFIG.HAS_TKEEP 1 CONFIG.HAS_TSTRB 1 CONFIG.HAS_TLAST 1 CONFIG.FREQ_HZ 100000000] [get_bd_intf_ports $name]
 connect_bd_intf_net [get_bd_intf_ports $name] [get_bd_intf_pins core/$pin]
}
connect_bd_net [get_bd_ports clk] [get_bd_pins core/ap_clk] [get_bd_pins mem/aclk]
connect_bd_net [get_bd_ports resetn] [get_bd_pins core/ap_rst_n] [get_bd_pins mem/aresetn]
set_property CONFIG.ASSOCIATED_BUSIF control:memory:s:m [get_bd_ports clk]
set_property CONFIG.ASSOCIATED_RESET resetn [get_bd_ports clk]
assign_bd_address -offset 0 -range 64K -target_address_space [get_bd_addr_spaces control] [get_bd_addr_segs core/s_axi_control/Reg]
set seg [get_bd_addr_segs memory/Reg]
foreach bundle $bundles {assign_bd_address -offset 0 -range 4G -target_address_space [get_bd_addr_spaces core/Data_m_axi_$bundle] $seg}
validate_bd_design;save_bd_design
set bd [get_files a.bd];generate_target all $bd
set wrapper [make_wrapper -files $bd -top];add_files -norecurse $wrapper
if {![info exists ::env(PYTHON)]} {set ::env(PYTHON) python}
exec $::env(PYTHON) -E [file join $root generate_wrapper.py] [lindex $wrapper 0] [file join $root build rm_medical_AXIS_D9.v]
add_files [file join $root build rm_medical_AXIS_D9.v]
add_files [list [file join $profile control_bank_r329.sv] [file join $profile axi_profile_timescale_r316.sv] [file join $profile optional_synth_r333 optional_profile_r332.sv]]
set_property generic {ENABLE_DIAGNOSTICS=1} [current_fileset]
set_property top rm_medical [current_fileset]
update_compile_order -fileset sources_1
set_property STEPS.SYNTH_DESIGN.ARGS.DIRECTIVE AreaOptimized_high [get_runs synth_1]
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]

puts "KV260_GIT_RM_READY smooth"

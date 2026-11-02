# Run through AMD Ross Vivado MCP with the source project open.
# This interface-view BD does not replace the production DFX RTL adapter.
set medical_root [file dirname [file normalize [info script]]]
if {[version -short] ne "2025.2.1"} {error "Use Vivado 2025.2.1"}
if {[current_project -quiet] eq ""} {error "Open the source project first"}
if {[llength [get_files -quiet */algorithm_mc.bd]]} {
    open_bd_design [get_files */algorithm_mc.bd]
} else {
    set repos [get_property IP_REPO_PATHS [current_project]]
    lappend repos [file join $medical_root ip_repo]
    set_property IP_REPO_PATHS [lsort -unique $repos] [current_project]
    update_ip_catalog
    create_bd_design algorithm_mc
    create_bd_cell -type ip -vlnv xilinx.com:hls:binary_mc_axis:1.0 mc_core
    foreach intf [get_bd_intf_pins mc_core/*] {
        make_bd_intf_pins_external $intf
    }
    foreach pin_name {ap_clk ap_rst_n interrupt} {
        make_bd_pins_external [get_bd_pins mc_core/$pin_name]
    }
    assign_bd_address
}
validate_bd_design -force
regenerate_bd_layout
save_bd_design
set_property GENERATE_SYNTH_CHECKPOINT false [get_files */algorithm_mc.bd]
generate_target all [get_files */algorithm_mc.bd]
set_property TOP system_top [get_filesets sources_1]
update_compile_order -fileset sources_1
puts "MC_BD_READY: algorithm_mc.bd (existing current MC IP; production RM remains RTL-based)"

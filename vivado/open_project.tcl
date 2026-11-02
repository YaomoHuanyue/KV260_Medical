set root [file dirname [file normalize [info script]]]
if {[version -short] ne "2025.2.1"} {error "Use Vivado 2025.2.1"}
if {![llength [get_board_parts -quiet xilinx.com:kv260_som:part0:1.4]]} {
    set_param board.repoPaths [list [file join $root hardware boards]]
}
set path [file join $root project KV260_Medical.xpr]
if {![file exists $path]} {error "Run create_project.tcl first"}
if {[current_project -quiet] ne ""} {error "Save and close the current project first"}
open_project $path
open_bd_design [get_files system_ps.bd]

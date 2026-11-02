# Execute through AMD Ross Vivado MCP, using Vivado 2025.2.1.
set root [file dirname [file normalize [info script]]]
if {[version -short] ne "2025.2.1"} {error "Use Vivado 2025.2.1"}
if {[current_project -quiet] ne ""} {error "Save and close the current project first"}
if {[file exists [file join $root project KV260_Medical.xpr]]} {
    error "Project already exists. Use open_project.tcl; creation will not overwrite edits."
}
source [file join $root hardware ross_export Scripts build.tcl]
source [file join $root add_mc_bd.tcl]
open_bd_design [get_files system_ps.bd]
regenerate_bd_layout
save_bd_design
puts "READY: project/KV260_Medical.xpr; Sources -> system_ps -> Open Block Design"

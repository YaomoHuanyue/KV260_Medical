set root [file normalize [file dirname [info script]]]
if {[version -short] ne "2025.2.1"} {error "Exact Vivado version required"}
foreach name {READER_RTL_MODE READER_OWNED_ROOT} {if {![info exists ::env($name)]} {error "Explicit owned task environment required"}}
set mode $::env(READER_RTL_MODE)
if {$mode ni {ordinary random}} {error "Invalid mode"}
set owned [file normalize $::env(READER_OWNED_ROOT)]
if {![regexp {^k26-r2450-[0-9a-f]{16}$} [file tail $owned]] || [string first "$owned/workspace/" "$root/"]!=0} {error "Outside exact owned root"}
set project [file join $owned s $mode p]
if {[file exists $project]} {error "Preserve existing simulator project"}
set_param general.maxThreads 4
create_project reader_sim $project -part xck26-sfvc784-2LV-c
add_files [glob [file join $root source_RTL *.v]]
set work [file join $root run $mode]
add_files -fileset sim_1 [list [file join $work tb.sv] [file join $work hold.sv]]
set_property top tb [get_filesets sim_1]
set_property xsim.simulate.runtime {all} [get_filesets sim_1]
set_property xsim.elaborate.debug_level {off} [get_filesets sim_1]
set_property xsim.simulate.log_all_signals false [get_filesets sim_1]
update_compile_order -fileset sim_1
launch_simulation -scripts_only
close_project

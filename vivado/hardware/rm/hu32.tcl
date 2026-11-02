set _git_repo [file normalize [file join [file dirname [info script]] ../..]]
if {![info exists ::env(PYTHON)]} {set ::env(PYTHON) python}
exec $::env(PYTHON) -E [file join $_git_repo scripts prepare_axis_rm.py] hu32
set out [file join $_git_repo build rm hu32]
create_project rm_hu32 [file join $out project] -part xck26-sfvc784-2LV-c -force
add_files [glob [file join $_git_repo build hls hu32 hls syn verilog *.v]]
set data [glob -nocomplain [file join $_git_repo build hls hu32 hls syn verilog *.dat]]
if {[llength $data]} {add_files $data}
add_files [file join $out binding rm_medical.v]
add_files -fileset constrs_1 [file join $out binding clock.xdc]
set_property top rm_medical [current_fileset]
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]
update_compile_order -fileset sources_1
puts "KV260_GIT_RM_READY hu32"

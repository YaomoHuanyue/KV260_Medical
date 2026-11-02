# Source after hardware/rm/<target>.tcl in an AMD Ross Vivado session.
set _git_repo [file normalize [file join [file dirname [info script]] ..]]
if {![info exists ::env(KV260_RM_TARGET)]} {error "Set KV260_RM_TARGET to the RM name"}
set target $::env(KV260_RM_TARGET)
if {$target ni {ct hu32 mc smooth edt route surface quality composite}} {error "Unknown RM target"}
set out [file join $_git_repo build rm $target];file mkdir $out
launch_runs synth_1 -jobs 1
wait_on_run synth_1
if {![string match "*Complete*" [get_property STATUS [get_runs synth_1]]]} {error "RM synthesis failed"}
open_run synth_1
if {[llength [get_cells -hier -filter {IS_BLACKBOX == 1}]]} {error "Unresolved RM black boxes"}
write_checkpoint -force [file join $out synth.dcp]
report_utilization -hierarchical -file [file join $out synthesis_utilization.rpt]

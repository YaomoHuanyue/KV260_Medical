# Uses the accepted frozen static route. No board installation or automatic load.
set _git_repo [file normalize [file join [file dirname [info script]] ..]]
if {[version -short] ne "2025.2.1"} {error "Frozen DFX platform requires Vivado 2025.2.1"}
if {![info exists ::env(KV260_RM_TARGET)]} {error "Set KV260_RM_TARGET"}
set target $::env(KV260_RM_TARGET)
if {$target ni {ct hu32 mc smooth edt route surface quality composite}} {error "Unknown RM target"}
set out [file join $_git_repo build rm $target]
if {![file exists [file join $out synth.dcp]]} {error "Synthesize this RM first"}
if {[current_project -quiet] ne ""} {close_project}
open_checkpoint [file join $_git_repo hardware frozen static_routed.dcp]
read_checkpoint -cell rp -strict [file join $out synth.dcp]
opt_design
place_design
route_design
foreach kind {max min} {
 set paths [get_timing_paths -delay_type $kind -max_paths 1]
 if {![llength $paths] || [get_property SLACK [lindex $paths 0]]<0} {error "RM failed $kind timing"}
}
report_timing_summary -file [file join $out timing.rpt]
report_utilization -hierarchical -file [file join $out utilization.rpt]
write_checkpoint -force [file join $out routed.dcp]
# Compare the newly routed design with the retained golden configuration.
pr_verify -full_check [file join $_git_repo hardware frozen reference_mc.dcp] [file join $out routed.dcp] -file [file join $out pr_verify.log]
write_bitstream -force -bin_file [file join $out config.bit]
puts "Candidate partial written; production qualification and board testing are separate"

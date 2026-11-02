# Register real synthesized RM checkpoints in the main project, no placeholders.
# The accepted static remains the implementation baseline of implement_rm.tcl.
set medical_root [file normalize [file join [file dirname [info script]] ..]]
if {[version -short] ne "2025.2.1"} {error "Require Vivado 2025.2.1"}
if {[current_project -quiet] eq ""} {error "Open or recreate the main project first"}
set targets {hu32 mc composite edt surface quality route ct smooth}
foreach target $targets {
    set checkpoint [file join $medical_root checkpoints rm_${target}_synth.dcp]
    if {![file exists $checkpoint]} {error "Missing real RM checkpoint: $checkpoint"}
}
if {![llength [get_partition_defs -quiet medical_pd]]} {
    create_partition_def -name medical_pd -module rm_medical
}
foreach target $targets {
    if {![llength [get_reconfig_modules -quiet rm_$target]]} {
        create_reconfig_module -name rm_$target -partition_def [get_partition_defs medical_pd] -top rm_medical -gate_level
    }
    set rm [get_reconfig_modules rm_$target]
    set checkpoint [file join $medical_root checkpoints rm_${target}_synth.dcp]
    if {![llength [get_files -quiet -of_objects $rm $checkpoint]]} {add_files -of_objects $rm $checkpoint}
    if {![llength [get_pr_configurations -quiet cfg_$target]]} {
        create_pr_configuration -name cfg_$target -partitions [list rp:rm_$target]
    }
}
set_property PR_CONFIGURATION cfg_mc [get_runs impl_1]
set flow [get_property FLOW [get_runs impl_1]]
foreach target $targets {
    if {$target eq "mc"} {continue}
    if {![llength [get_runs -quiet impl_$target]]} {
        create_run impl_$target -parent_run impl_1 -flow $flow -pr_config cfg_$target
    }
}
puts "DFX_REGISTERED: [llength [get_partition_defs]] partition definitions, [llength [get_reconfig_modules]] real RMs, [llength [get_pr_configurations]] configurations"

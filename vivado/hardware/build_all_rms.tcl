# Execute in a live AMD Ross Vivado MCP session, Vivado 2025.2.1.
# Each RM is built independently against the accepted frozen static route.
set medical_root [file normalize [file join [file dirname [info script]] ..]]
if {[version -short] ne "2025.2.1"} {error "Require Vivado 2025.2.1"}
set targets {hu32 mc composite edt surface quality route ct smooth}
if {[info exists ::env(KV260_RM_TARGETS)]} {set targets $::env(KV260_RM_TARGETS)}
file mkdir [file join $medical_root reports all_rms]
set receipt [open [file join $medical_root reports all_rms stages.tsv] a]
puts $receipt "target\tstage\tresult\tseconds"
flush $receipt
set failed {}
foreach target $targets {
    if {$target ni {hu32 mc composite edt surface quality route ct smooth}} {error "Unknown target $target"}
    set ::env(KV260_RM_TARGET) $target
    if {[current_project -quiet] ne ""} {close_project}
    set ok 1
    foreach stage {create synthesize implement} {
        set start [clock seconds]
        if {$stage eq "create"} {
            set script [file join $medical_root hardware rm ${target}.tcl]
        } else {
            set script [file join $medical_root hardware ${stage}_rm.tcl]
        }
        set code [catch {source $script} message options]
        puts $receipt "$target\t$stage\t[expr {$code ? {FAIL} : {PASS}}]\t[expr {[clock seconds]-$start}]"
        flush $receipt
        if {$code} {
            set f [open [file join $medical_root reports all_rms ${target}_${stage}_failure.txt] w]
            puts $f $message
            if {[dict exists $options -errorinfo]} {puts $f [dict get $options -errorinfo]}
            close $f
            lappend failed $target
            set ok 0
            break
        }
    }
    if {$ok} {puts "RM_COMPLETE $target"}
}
close $receipt
if {[current_project -quiet] ne ""} {close_project}
if {[llength $failed]} {error "RM build failures: $failed; see reports/all_rms"}
puts "ALL_RMS_IMPLEMENTED_AGAINST_FROZEN_STATIC"

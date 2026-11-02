# Actual accepted cf5 routed design, for hierarchy and implemented-design inspection.
set root [file dirname [file normalize [info script]]]
if {[version -short] ne "2025.2.1"} {error "Use Vivado 2025.2.1"}
if {[current_project -quiet] ne ""} {error "Save and close the source project first"}
open_checkpoint [file join $root checkpoints ct_cf5_routed.dcp]
puts "Actual cf5 implementation loaded. Inspect rp/a_i for CT hardware."

# Re-generate bitstreams from the accepted physical design. No board access.
set root [file dirname [file normalize [info script]]]
if {[version -short] ne "2025.2.1"} {error "Use Vivado 2025.2.1"}
if {[current_project -quiet] ne ""} {error "Save and close the current project first"}
set out [file join $root build ct_cf5_bit]
if {[file exists $out]} {error "Output already exists; preserve prior output or choose a fresh build directory"}
file mkdir $out
open_checkpoint [file join $root checkpoints ct_cf5_routed.dcp]
write_bitstream -force -bin_file [file join $out medical_ct_cf5.bit]
puts "Candidate bitstreams written under build/ct_cf5_bit; no firmware installed."

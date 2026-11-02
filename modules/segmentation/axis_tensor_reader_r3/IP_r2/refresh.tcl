if {![info exists ::env(R3_READER_IP_ROOT)]} {error "Owned reader IP path required"}
set core_dir [file normalize $::env(R3_READER_IP_ROOT)]
if {![regexp {k26-r2450-[0-9a-f]{16}/i/tensor$} $core_dir]} {error "Exact owned reader directory required"}
if {![file exists [file join $core_dir component.xml]]} {error "Missing reader component"}
create_project -in_memory -part xck26-sfvc784-2LV-c
set_property target_language Verilog [current_project]
ipx::open_core [file join $core_dir component.xml]
set core [ipx::current_core]
ipx::update_checksums $core
ipx::save_core $core
ipx::check_integrity -quiet $core
puts "PASS R3_READER_CANONICAL_IPX_CHECKSUMS"
close_project

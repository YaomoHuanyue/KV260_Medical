################################################################################
# project_settings.tcl - Captured Project Configuration
# Generated: Mon Nov 02 08:01:40 2026
# Project: dfx_medical
# Device: xck26-sfvc784-2LV-c
################################################################################

# Derive base_dir for referencing exported files (e.g., hook scripts)
set base_dir [file dirname [file dirname [file normalize [info script]]]]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROJECT SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set_property PART xck26-sfvc784-2LV-c [current_project]
set_property BOARD_PART {xilinx.com:kv260_som:part0:1.4} [current_project]
set_property TARGET_LANGUAGE {Verilog} [current_project]
set_property IP_CACHE_PERMISSIONS {read write} [current_project]
set_property PR_FLOW true [current_project]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILESET SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set_property TOP {system_top} [get_filesets sources_1]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SYNTHESIS SETTINGS (non-default only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set_property STEPS.SYNTH_DESIGN.ARGS.SHREG_MIN_SIZE {3} [get_runs synth_1]
set_property STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD {auto} [get_runs synth_1]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPLEMENTATION SETTINGS (non-default only)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# All implementation settings are at defaults �? nothing to restore

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TCL HOOK SCRIPTS (pre/post hooks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# No hook scripts configured

puts "Project settings restored from saved configuration"

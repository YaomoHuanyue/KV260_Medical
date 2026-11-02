if {[version -short] ne "2025.2.1"} {error "Require Vivado 2025.2.1"}
#*******************************************************************************
# build.tcl - Project Recreation Script
# Generated: Mon Nov 02 08:01:42 2026
# Original Project: dfx_medical
#*******************************************************************************

set script_dir [file dirname [file normalize [info script]]]
set base_dir [file dirname $script_dir]
set proj_name dfx_medical

#─────────────────────────────────────────────────────────────────────────────────
# Step 1: Create Project
#─────────────────────────────────────────────────────────────────────────────────
create_project dfx_medical [file normalize $base_dir/../../build/ross_project] -part xck26-sfvc784-2LV-c -force
set_property BOARD_PART {xilinx.com:kv260_som:part0:1.4} [current_project]

#─────────────────────────────────────────────────────────────────────────────────
# Step 1b: Set Custom IP Repository Paths (required before BD recreation)
#─────────────────────────────────────────────────────────────────────────────────
set_property IP_REPO_PATHS [list \
    [file normalize $base_dir/../../dfx/medical/ip/dfx_reader] \
    [file normalize $base_dir/../../dfx/medical/ip/dfx_writer] \
] [current_project]
update_ip_catalog

#─────────────────────────────────────────────────────────────────────────────────
# Step 2: Add RTL Sources
#─────────────────────────────────────────────────────────────────────────────────
# Local sources �? import into project for full portability
set rtl_files {}
catch {set rtl_files [glob $base_dir/Sources/RTL/*]}
if {[llength $rtl_files] > 0} {
    import_files $rtl_files
}

# Remote sources �? referenced in-place at their original absolute location

#─────────────────────────────────────────────────────────────────────────────────
# Step 3: Add Constraint Files
#─────────────────────────────────────────────────────────────────────────────────
set xdc_files {}
catch {set xdc_files [glob $base_dir/Sources/Constraints/*.xdc]}
# Include NoC constraints if present
catch {lappend xdc_files {*}[glob $base_dir/Sources/NoC/*.xdc]}
if {[llength $xdc_files] > 0} {
    import_files -fileset constrs_1 $xdc_files
}
# Remote constraints �? referenced in-place at their original absolute location


#─────────────────────────────────────────────────────────────────────────────────
# Step 4: Add Simulation Files
#─────────────────────────────────────────────────────────────────────────────────
set sim_files {}
catch {set sim_files [glob $base_dir/Sources/Simulation/*]}
if {[llength $sim_files] > 0} {
    import_files -fileset sim_1 $sim_files
}
# Remote simulation files �? referenced in-place at their original absolute location


#─────────────────────────────────────────────────────────────────────────────────
# Step 5: Add Data Files (Memory init, config, etc.)
#─────────────────────────────────────────────────────────────────────────────────
set data_files {}
catch {set data_files [glob $base_dir/Sources/Data/*]}
if {[llength $data_files] > 0} {
    import_files $data_files
}
# Remote data files �? referenced in-place at their original absolute location


#─────────────────────────────────────────────────────────────────────────────────
# Step 6: Recreate IP Cores
#─────────────────────────────────────────────────────────────────────────────────
set ip_tcls {}
catch {set ip_tcls [glob $base_dir/Sources/IP/*.tcl]}
foreach ip_tcl $ip_tcls {
    source $ip_tcl
}

# Create OOC synthesis runs for standalone IPs (outside Block Designs)
set standalone_ips [get_ips]
foreach ip $standalone_ips {
    set is_bd [get_property IS_BD_CONTEXT $ip]
    if {$is_bd ne "1" && $is_bd ne "true"} {
        catch {create_ip_run [get_ips [get_property NAME $ip]]}
    }
}

#─────────────────────────────────────────────────────────────────────────────────
# Step 7: Recreate Block Designs
# CRITICAL: BDC child BDs must be sourced BEFORE parent BDs that instantiate them.
# For DFX: RM Block Designs are skipped here �? they are added to RM filesets in
#          Step 12 (dfx_define_partition) to prevent them from becoming independent BDs.
#─────────────────────────────────────────────────────────────────────────────────
set bd_is_rm_owned 0
if {[info exists _rm_owned_bd_names]} {
    set bd_is_rm_owned [expr {[lsearch $_rm_owned_bd_names "system_ps"] >= 0}]
}
if {$bd_is_rm_owned} {
    puts "  Skipping BD (RM-owned): system_ps �? will be added to RM fileset in Step 12"
} elseif {0} {
    # Preserved BD (remote cache mode): add_files the .bd restored from the
    # cache in Step 1c, and rely on the .gen restored there too to avoid
    # regeneration. Non-preserved BDs use the standard Tcl-regeneration path
    # below -- this branch is per-BD, not global. Step 1c already guarantees
    # this source exists (it errors out the whole build otherwise).
    add_files -norecurse [file join ${proj_name}.srcs {} {system_ps.bd}]
    if {[catch {generate_target all [get_files system_ps.bd]} _gt_pres_err]} {
        puts "  WARNING: generate_target failed for preserved BD system_ps: $_gt_pres_err"
    }
    # add_files alone does not open the BD as a live design -- validate_bd_design
    # / save_bd_design / get_bd_designs need open_bd_design first, or they fail
    # with 'Cannot find design named ...' / 'A block design must be open'.
    catch {open_bd_design [get_files system_ps.bd]}
    catch {validate_bd_design -force -design system_ps}
    catch {save_bd_design [get_bd_designs -quiet system_ps]}
} else {
    set bd_tcl $base_dir/Sources/BD/system_ps.tcl
    if {[file exists $bd_tcl]} {
        puts "  Sourcing BD: system_ps"
        source $bd_tcl
        # Validate immediately: BDC parents that reference this BD as a
        # container (create_bd_cell -type container -reference) require it
        # to be validated first, otherwise cell creation fails.
        if {[catch {validate_bd_design -force -design system_ps} _vbd_err]} {
            puts "  WARNING: validate_bd_design reported an error for system_ps: $_vbd_err"
            puts "  This is usually caused by locked/out-of-date IPs in the BD."
            puts "  On the ORIGINAL project: open_bd_design system_ps.bd; report_ip_status"
            puts "  then upgrade_ip the flagged IPs and re-run this export."
            puts "  NOTE: Vivado now treats this session as having a logged error --"
            puts "  later commands (e.g. make_wrapper) may fail with 'failed due to"
            puts "  earlier errors' even though THIS is the real root cause."
        }
        # Persist the validated state �? without this, a sibling BD sourced
        # later that references this BD as a BDC container may see it as
        # not validated (validate_bd_design alone is not enough).
        catch {save_bd_design [get_bd_designs -quiet system_ps]}
    } else {
        puts "  WARNING: BD tcl not exported, skipping: system_ps"
    }
}


#─────────────────────────────────────────────────────────────────────────────────
# Step 8: Recreate Block Design wrappers (only if wrapper was present in project)
#─────────────────────────────────────────────────────────────────────────────────
# Create and add wrapper for BD: system_ps
set bd_obj [get_files -quiet system_ps.bd]
if {[llength $bd_obj] > 0} {
    if {[catch {set wrapper_path [make_wrapper -files $bd_obj -top]} _mw_err]} {
        puts "  ERROR: make_wrapper failed for system_ps: $_mw_err"
        puts "  This almost always means an EARLIER step already logged an error"
        puts "  for this BD (search this log above for WARNING/ERROR mentioning"
        puts "  system_ps -- commonly locked/out-of-date IPs from Step 7)."
        puts "  Fix on the ORIGINAL project (report_ip_status / upgrade_ip), then"
        puts "  re-run the export/build pipeline."
    } else {
        import_files $wrapper_path
    }
}


#─────────────────────────────────────────────────────────────────────────────────
# Step 9: Generate BD Targets and Create BD IP OOC Runs
# NOTE: Only operate on top-level user BDs from sources_1 fileset.
#       Nested sub-designs (e.g., inside Versal CIPS) are auto-generated by
#       their parent IP and MUST NOT be generated independently.
#       Using FILE_TYPE filter + .srcs path check to exclude them.
#─────────────────────────────────────────────────────────────────────────────────
set bd_files {}
catch {set bd_files [get_files -filter {FILE_TYPE == "Block Designs"} -of_objects [get_filesets sources_1]]}
foreach bd $bd_files {
    set bd_norm [file normalize $bd]
    # Skip nested sub-designs in .gen/ (auto-generated by parent IPs like Versal CIPS)
    if {[string match "*/.gen/*" $bd_norm]} {
        puts "  Skipping nested sub-design: [file tail $bd]"
        continue
    }
    # Skip generated BDs
    if {[get_property IS_GENERATED $bd] eq "1"} {
        puts "  Skipping generated BD: [file tail $bd]"
        continue
    }
    puts "  Generating targets for: [file tail $bd]"
    if {[info exists ::env(KV260_CREATE_ONLY)] && $::env(KV260_CREATE_ONLY) eq "1"} {puts "Project-only check: IP targets regenerate at synthesis";continue}
    if {[catch {generate_target all $bd} _gt_err]} {
        puts "  ERROR: generate_target failed for [file tail $bd]: $_gt_err"
        puts "  Check the ERROR/CRITICAL WARNING lines just above for the real root"
        puts "  cause. Two known classes seen in this skill's own validation:"
        puts "    1) Debug-net (mark_debug/ILA) connections routed through a Block"
        puts "       Design Container failing to resolve on a freshly recreated"
        puts "       design ('Could not find the cell' errors) -- not an export"
        puts "       issue. Workaround: remove debug cores from the BD before"
        puts "       export, or manually regenerate targets for [file tail $bd]"
        puts "       in the GUI."
        puts "    2) A NoC memory-controller PHY IP (e.g. noc_mc_ddr5_phy_v1_0)"
        puts "       failing to generate simulation BFM outputs due to a missing"
        puts "       file under this Vivado install's own"
        puts "       data/ip/xilinx/<ip>/hdl/bfm/ tree ('Failed to copy file ..."
        puts "       it does not exist' CRITICAL WARNING) -- a Vivado installation"
        puts "       gap, not something export/rebuild can fix; report it to your"
        puts "       Vivado install owner."
    }
}

# Create OOC runs for IPs within top-level Block Designs only
foreach bd $bd_files {
    set bd_norm [file normalize $bd]
    if {[string match "*/.gen/*" $bd_norm]} { continue }
    if {[get_property IS_GENERATED $bd] eq "1"} { continue }
    catch {create_ip_run [get_ips -of_objects [get_files $bd]]}
}

#─────────────────────────────────────────────────────────────────────────────────
# Step 10: Add Hook Scripts to utils_1 fileset
#─────────────────────────────────────────────────────────────────────────────────
set hook_scripts {}
catch {set hook_scripts [glob $base_dir/Sources/Scripts/*.tcl]}
if {[llength $hook_scripts] > 0} {
    import_files -fileset utils_1 $hook_scripts
}

#─────────────────────────────────────────────────────────────────────────────────
# Step 11: Apply Captured Project Settings
#─────────────────────────────────────────────────────────────────────────────────
source $script_dir/project_settings.tcl
update_compile_order -fileset sources_1

#─────────────────────────────────────────────────────────────────────────────────
# Step 11b: Restore fileset source ordering (if captured)
#─────────────────────────────────────────────────────────────────────────────────
proc _rc_restore_fileset_order {fileset_name ordered_tails} {
    if {[llength [get_filesets -quiet $fileset_name]] == 0} { return }
    set last_file ""
    foreach tail $ordered_tails {
        set match {}
        catch {set match [get_files -quiet -of_objects [get_filesets $fileset_name] -filter "NAME =~ *${tail}"]}
        if {[llength $match] == 0} { continue }
        set f [lindex $match 0]
        if {$last_file eq ""} {
            catch {reorder_files -fileset $fileset_name -front $f}
        } else {
            catch {reorder_files -fileset $fileset_name -after $last_file $f}
        }
        set last_file $f
    }
    catch {update_compile_order -fileset $fileset_name}
}

_rc_restore_fileset_order sources_1 {system_ps.bd system_ps_ps_0.xci axi_infrastructure_v1_1_0.vh axi_infrastructure_v1_1_vl_rfs.v axi_vip_v1_1_vl_rfs.sv zynq_ultra_ps_e_vip_v1_0_22_local_params.sv zynq_ultra_ps_e_vip_v1_0_vl_rfs.sv zynq_ultra_ps_e_vip_v1_0_22_reg_params.sv zynq_ultra_ps_e_vip_v1_0_22_reg_init.sv zynq_ultra_ps_e_vip_v1_0_22_apis.sv zynq_ultra_ps_e_vip_v1_0_22_unused_ports.sv zynq_ultra_ps_e_vip_v1_0_22_axi_gp.sv zynq_ultra_ps_e_vip_v1_0_22_axi_acp.sv zynq_ultra_ps_e_vip_v1_0_22_axi_ace.sv system_ps_ps_0_vip_wrapper.v zynq_ultra_ps_e_v3_5_8.v system_ps_ps_0_ooc.xdc system_ps_ps_0.xdc system_ps_ps_0.hwdef psu_init.c psu_init.h psu_init_gpl.c psu_init_gpl.h psu_init.tcl psu_init.html system_ps_ps_0.v system_ps_control_0.xci system_ps_control_0_board.xdc axi_lite_ipif_v3_0_vh_rfs.vhd interrupt_control_v3_1_vh_rfs.vhd system_ps_control_0_ooc.xdc axi_gpio_v2_0_vh_rfs.vhd system_ps_control_0.vhd system_ps_control_0.vhd system_ps_control_bus_0.xci sc_xtlm_system_ps_control_bus_0.mem proc_sys_reset_v5_0_vh_rfs.vhd sc_util_v1_0_4_constants.vh sc_util_v1_0_4_constants_noc.vh sc_util_v1_0_4_structs.svh sc_node_v1_0_19_t_reqsend.svh axi_infrastructure_v1_1_0.vh axi_infrastructure_v1_1_vl_rfs.v axi_register_slice_v2_1_vl_rfs.v axi_vip_v1_1_vl_rfs.sv system_ps_control_bus_0.sv ooc.xdc smartconnect.xdc system_ps_control_bus_0.v system_ps_rst_0.xci system_ps_rst_0_board.xdc proc_sys_reset_v5_0_vh_rfs.vhd system_ps_rst_0.vhd system_ps_rst_0.vhd system_ps_rst_0_ooc.xdc system_ps_one_0.xci xlconstant_v1_1_vl_rfs.v system_ps_one_0.v system_ps_one_0.v system_ps_zero_0.xci xlconstant_v1_1_vl_rfs.v system_ps_zero_0.v system_ps_zero_0.v system_ps_memory_bus_0.xci sc_post_elab.rld sc_xtlm_system_ps_memory_bus_0.mem proc_sys_reset_v5_0_vh_rfs.vhd sc_util_v1_0_4_constants.vh sc_util_v1_0_4_constants_noc.vh sc_util_v1_0_4_structs.svh sc_node_v1_0_19_t_reqsend.svh axi_infrastructure_v1_1_0.vh axi_infrastructure_v1_1_vl_rfs.v axi_register_slice_v2_1_vl_rfs.v axi_vip_v1_1_vl_rfs.sv system_ps_memory_bus_0.sv ooc.xdc smartconnect.xdc system_ps_memory_bus_0.v system_ps_dfx_reader_0.xci dfx_reader_ooc.xdc dfx_reader_control_s_axi.v dfx_reader_flow_control_loop_pipe.v dfx_reader_hls_deadlock_idx0_monitor.v dfx_reader_hls_deadlock_kernel_monitor_top.vh dfx_reader_memory_m_axi.v dfx_reader_regslice_both.v dfx_reader.v system_ps_dfx_reader_0.v dfx_reader.mdd dfx_reader.tcl dfx_reader.yaml CMakeLists.txt Makefile xdfx_reader.c xdfx_reader.h xdfx_reader_hw.h xdfx_reader_linux.c xdfx_reader_sinit.c system_ps_dfx_reader_0.v system_ps_dfx_writer_0.xci dfx_writer_ooc.xdc dfx_writer_control_s_axi.v dfx_writer_flow_control_loop_delay_pipe.v dfx_writer_hls_deadlock_idx0_monitor.v dfx_writer_hls_deadlock_kernel_monitor_top.vh dfx_writer_memory_m_axi.v dfx_writer_regslice_both.v dfx_writer.v system_ps_dfx_writer_0.v dfx_writer.mdd dfx_writer.tcl dfx_writer.yaml CMakeLists.txt Makefile xdfx_writer.c xdfx_writer.h xdfx_writer_hw.h xdfx_writer_linux.c xdfx_writer_sinit.c system_ps_dfx_writer_0.v system_ps_control_guard_0.xci system_ps_control_guard_0.vhd system_ps_control_guard_0.vhd system_ps_control_guard_0_ooc.xdc system_ps_memory_guard_0.xci system_ps_memory_guard_0.vhd system_ps_memory_guard_0.vhd system_ps_memory_guard_0_ooc.xdc system_ps.v system_ps.v system_ps_ooc.xdc system_ps.hwh system_ps.bda system_ps.hwdef system_ps.protoinst system_ps.vho system_ps.veo system_ps_sv.sveo medical_guard.v rm_stub.v system_ps_wrapper.v system_top.v}

#─────────────────────────────────────────────────────────────────────────────────
# Step 13: Finalize Project
#─────────────────────────────────────────────────────────────────────────────────
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "──────────────────────────────────────────────────────────────────────────"
puts "Project recreated successfully!"
puts "──────────────────────────────────────────────────────────────────────────"

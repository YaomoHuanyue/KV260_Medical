
wire kernel_monitor_reset;
wire kernel_monitor_clock;
wire kernel_monitor_report;
assign kernel_monitor_reset = ~ap_rst_n;
assign kernel_monitor_clock = ap_clk;
assign kernel_monitor_report = 1'b0;
wire [6:0] axis_block_sigs;
wire [12:0] inst_idle_sigs;
wire [3:0] inst_block_sigs;
wire kernel_block;

assign axis_block_sigs[0] = ~output_r_TDATA_blk_n;
assign axis_block_sigs[1] = ~grp_binary_mc_axis_Pipeline_drain_invalid_fu_223.input_r_TDATA_blk_n;
assign axis_block_sigs[2] = ~grp_execute_fu_240.scan_U0.grp_scan_Pipeline_VITIS_LOOP_27_4_VITIS_LOOP_27_5_scan_groups_fu_185.input_r_TDATA_blk_n;
assign axis_block_sigs[3] = ~grp_execute_fu_240.scan_U0.grp_scan_Pipeline_drain_extra_fu_229.input_r_TDATA_blk_n;
assign axis_block_sigs[4] = ~grp_execute_fu_240.pack_U0.output_r_TDATA_blk_n;
assign axis_block_sigs[5] = ~grp_execute_fu_240.pack_U0.grp_pack_Pipeline_VITIS_LOOP_97_1_fu_191.output_r_TDATA_blk_n;
assign axis_block_sigs[6] = ~grp_execute_fu_240.pack_U0.grp_pack_Pipeline_pad_missing_fu_213.output_r_TDATA_blk_n;

assign inst_idle_sigs[0] = grp_execute_fu_240.execute_Block_entry_proc_U0.ap_idle;
assign inst_block_sigs[0] = (grp_execute_fu_240.execute_Block_entry_proc_U0.ap_done & ~grp_execute_fu_240.execute_Block_entry_proc_U0.ap_continue);
assign inst_idle_sigs[1] = grp_execute_fu_240.scan_U0.ap_idle;
assign inst_block_sigs[1] = (grp_execute_fu_240.scan_U0.ap_done & ~grp_execute_fu_240.scan_U0.ap_continue) | ~grp_execute_fu_240.scan_U0.cells_blk_n | ~grp_execute_fu_240.scan_U0.grp_scan_Pipeline_VITIS_LOOP_27_4_VITIS_LOOP_27_5_scan_groups_fu_185.cells_blk_n | ~grp_execute_fu_240.scan_U0.cmp_loc_c_blk_n;
assign inst_idle_sigs[2] = grp_execute_fu_240.triangulate_U0.ap_idle;
assign inst_block_sigs[2] = (grp_execute_fu_240.triangulate_U0.ap_done & ~grp_execute_fu_240.triangulate_U0.ap_continue) | ~grp_execute_fu_240.triangulate_U0.cmp_loc_blk_n | ~grp_execute_fu_240.triangulate_U0.cells_blk_n | ~grp_execute_fu_240.triangulate_U0.vertices_blk_n | ~grp_execute_fu_240.triangulate_U0.grp_triangulate_Pipeline_emit_vertices_fu_335.vertices_blk_n;
assign inst_idle_sigs[3] = grp_execute_fu_240.pack_U0.ap_idle;
assign inst_block_sigs[3] = (grp_execute_fu_240.pack_U0.ap_done & ~grp_execute_fu_240.pack_U0.ap_continue) | ~grp_execute_fu_240.pack_U0.grp_pack_Pipeline_VITIS_LOOP_97_1_fu_191.vertices_blk_n;

assign inst_idle_sigs[4] = 1'b0;
assign inst_idle_sigs[5] = grp_binary_mc_axis_Pipeline_drain_invalid_fu_223.ap_idle;
assign inst_idle_sigs[6] = grp_execute_fu_240.ap_idle;
assign inst_idle_sigs[7] = grp_execute_fu_240.scan_U0.ap_idle;
assign inst_idle_sigs[8] = grp_execute_fu_240.scan_U0.grp_scan_Pipeline_VITIS_LOOP_27_4_VITIS_LOOP_27_5_scan_groups_fu_185.ap_idle;
assign inst_idle_sigs[9] = grp_execute_fu_240.scan_U0.grp_scan_Pipeline_drain_extra_fu_229.ap_idle;
assign inst_idle_sigs[10] = grp_execute_fu_240.pack_U0.ap_idle;
assign inst_idle_sigs[11] = grp_execute_fu_240.pack_U0.grp_pack_Pipeline_VITIS_LOOP_97_1_fu_191.ap_idle;
assign inst_idle_sigs[12] = grp_execute_fu_240.pack_U0.grp_pack_Pipeline_pad_missing_fu_213.ap_idle;

binary_mc_axis_hls_deadlock_idx0_monitor binary_mc_axis_hls_deadlock_idx0_monitor_U (
    .clock(kernel_monitor_clock),
    .reset(kernel_monitor_reset),
    .axis_block_sigs(axis_block_sigs),
    .inst_idle_sigs(inst_idle_sigs),
    .inst_block_sigs(inst_block_sigs),
    .block(kernel_block)
);


always @ (kernel_block or kernel_monitor_reset) begin
    if (kernel_block == 1'b1 && kernel_monitor_reset == 1'b0) begin
        find_kernel_block = 1'b1;
    end
    else begin
        find_kernel_block = 1'b0;
    end
end

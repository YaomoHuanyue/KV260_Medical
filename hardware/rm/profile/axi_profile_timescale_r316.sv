`timescale 1ns/1ps
// Passive observer: every AXI signal is an input. It cannot stall or change DMA.
module medical_axi_profile_r312 (
    input wire clk,
    input wire resetn,
    input wire run_start,
    input wire run_stop,
    input wire arvalid, arready,
    input wire [7:0] arlen,
    input wire [2:0] arsize,
    input wire rvalid, rready, rlast,
    input wire [1:0] rresp,
    input wire awvalid, awready,
    input wire [7:0] awlen,
    input wire [2:0] awsize,
    input wire wvalid, wready,
    input wire [15:0] wstrb,
    input wire bvalid, bready,
    input wire [1:0] bresp,
    output reg active,
    output reg snapshot_valid,
    output wire [1023:0] counters,
    output reg [31:0] pending_reads,
    output reg [31:0] pending_writes
);
    reg [63:0] values [0:15];
    wire ar_fire = arvalid && arready;
    wire r_fire = rvalid && rready;
    wire r_done = r_fire && rlast;
    wire aw_fire = awvalid && awready;
    wire w_fire = wvalid && wready;
    wire b_fire = bvalid && bready;
    wire [31:0] read_next = pending_reads + (ar_fire ? 32'd1 : 32'd0)
        - ((r_done && (pending_reads != 0 || ar_fire)) ? 32'd1 : 32'd0);
    wire [31:0] write_next = pending_writes + (aw_fire ? 32'd1 : 32'd0)
        - ((b_fire && (pending_writes != 0 || aw_fire)) ? 32'd1 : 32'd0);
    wire [63:0] read_bytes = ({56'd0, arlen} + 64'd1) << arsize;
    wire read_error = r_fire && rresp != 0;
    wire write_error = b_fire && bresp != 0;
    function automatic [4:0] byte_count(input [15:0] mask);
        integer j;
        begin
            byte_count = 0;
            for (j = 0; j < 16; j = j + 1)
                byte_count = byte_count + mask[j];
        end
    endfunction
    genvar k;
    generate
        for (k = 0; k < 16; k = k + 1) begin: pack
            assign counters[k*64 +: 64] = values[k];
        end
    endgenerate
    integer i;
    always @(posedge clk) begin
        if (!resetn) begin
            active <= 0;
            snapshot_valid <= 0;
            pending_reads <= 0;
            pending_writes <= 0;
            for (i = 0; i < 16; i = i + 1) values[i] <= 0;
        end else if (run_start) begin
            active <= 1;
            snapshot_valid <= 0;
            pending_reads <= 0;
            pending_writes <= 0;
            for (i = 0; i < 16; i = i + 1) values[i] <= 0;
        end else if (active) begin
            values[0] <= values[0] + 1; // cycles through the stop observation
            if (ar_fire) begin
                values[1] <= values[1] + 1;
                values[3] <= values[3] + read_bytes;
            end
            if (r_fire) values[2] <= values[2] + 1;
            if (arvalid && !arready) values[4] <= values[4] + 1;
            if (pending_reads != 0 && !rvalid) values[5] <= values[5] + 1;
            if (rvalid && !rready) values[6] <= values[6] + 1;
            if (aw_fire) values[7] <= values[7] + 1;
            if (w_fire) begin
                values[8] <= values[8] + 1;
                values[9] <= values[9] + byte_count(wstrb);
            end
            if (awvalid && !awready) values[10] <= values[10] + 1;
            if (wvalid && !wready) values[11] <= values[11] + 1;
            if (bvalid && !bready) values[12] <= values[12] + 1;
            values[13] <= values[13] + (read_error ? 64'd1 : 64'd0) + (write_error ? 64'd1 : 64'd0);
            pending_reads <= read_next;
            pending_writes <= write_next;
            if (read_next > values[14]) values[14] <= {32'd0, read_next};
            if (write_next > values[15]) values[15] <= {32'd0, write_next};
            if (run_stop) begin
                active <= 0;
                snapshot_valid <= 1;
            end
        end
    end
endmodule

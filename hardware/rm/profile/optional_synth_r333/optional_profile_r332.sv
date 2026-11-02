`timescale 1ns/1ps
module optional_profile_r332 #(parameter ENABLE_DIAGNOSTICS=1)(
    input wire clk, resetn,
    input wire [15:0] s_awaddr,
    input wire s_awvalid, output wire s_awready,
    input wire [31:0] s_wdata, input wire [3:0] s_wstrb,
    input wire s_wvalid, output wire s_wready,
    output wire [1:0] s_bresp, output wire s_bvalid, input wire s_bready,
    input wire [15:0] s_araddr,
    input wire s_arvalid, output wire s_arready,
    output wire [31:0] s_rdata, output wire [1:0] s_rresp,
    output wire s_rvalid, input wire s_rready,
    output wire [7:0] m_awaddr,
    output wire m_awvalid, input wire m_awready,
    output wire [31:0] m_wdata, output wire [3:0] m_wstrb,
    output wire m_wvalid, input wire m_wready,
    input wire [1:0] m_bresp, input wire m_bvalid, output wire m_bready,
    output wire [7:0] m_araddr,
    output wire m_arvalid, input wire m_arready,
    input wire [31:0] m_rdata, input wire [1:0] m_rresp,
    input wire m_rvalid, output wire m_rready,
    input wire memory_arvalid,memory_arready,
    input wire [7:0] memory_arlen,
    input wire [2:0] memory_arsize,
    input wire memory_rvalid,memory_rready,memory_rlast,
    input wire [1:0] memory_rresp,
    input wire memory_awvalid,memory_awready,
    input wire [7:0] memory_awlen,
    input wire [2:0] memory_awsize,
    input wire memory_wvalid,memory_wready,
    input wire [15:0] memory_wstrb,
    input wire memory_bvalid,memory_bready,
    input wire [1:0] memory_bresp
);
wire profile_active,snapshot_valid,run_start,run_stop;wire [1023:0] counters;wire [31:0]pending_reads,pending_writes;
medical_axi_profile_control_r329 #(.ENABLE_DIAGNOSTICS(ENABLE_DIAGNOSTICS)) control_bank(.clk(clk),.resetn(resetn),.s_awaddr(s_awaddr),.s_awvalid(s_awvalid),.s_awready(s_awready),.s_wdata(s_wdata),.s_wstrb(s_wstrb),.s_wvalid(s_wvalid),.s_wready(s_wready),.s_bresp(s_bresp),.s_bvalid(s_bvalid),.s_bready(s_bready),.s_araddr(s_araddr),.s_arvalid(s_arvalid),.s_arready(s_arready),.s_rdata(s_rdata),.s_rresp(s_rresp),.s_rvalid(s_rvalid),.s_rready(s_rready),.m_awaddr(m_awaddr),.m_awvalid(m_awvalid),.m_awready(m_awready),.m_wdata(m_wdata),.m_wstrb(m_wstrb),.m_wvalid(m_wvalid),.m_wready(m_wready),.m_bresp(m_bresp),.m_bvalid(m_bvalid),.m_bready(m_bready),.m_araddr(m_araddr),.m_arvalid(m_arvalid),.m_arready(m_arready),.m_rdata(m_rdata),.m_rresp(m_rresp),.m_rvalid(m_rvalid),.m_rready(m_rready),.profile_active(profile_active),.snapshot_valid(snapshot_valid),.counters(counters),.pending_reads(pending_reads),.pending_writes(pending_writes),.run_start(run_start),.run_stop(run_stop));
generate if(ENABLE_DIAGNOSTICS)begin: debug_build
medical_axi_profile_r312 observer(.clk(clk),.resetn(resetn),.run_start(run_start),.run_stop(run_stop),.snapshot_valid(snapshot_valid),.counters(counters),.pending_reads(pending_reads),.pending_writes(pending_writes),.active(profile_active),.arvalid(memory_arvalid),.arready(memory_arready),.arlen(memory_arlen),.arsize(memory_arsize),.rvalid(memory_rvalid),.rready(memory_rready),.rlast(memory_rlast),.rresp(memory_rresp),.awvalid(memory_awvalid),.awready(memory_awready),.awlen(memory_awlen),.awsize(memory_awsize),.wvalid(memory_wvalid),.wready(memory_wready),.wstrb(memory_wstrb),.bvalid(memory_bvalid),.bready(memory_bready),.bresp(memory_bresp));
end else begin: production_build
assign profile_active=0;assign snapshot_valid=0;assign counters=0;assign pending_reads=0;assign pending_writes=0;
end endgenerate
endmodule

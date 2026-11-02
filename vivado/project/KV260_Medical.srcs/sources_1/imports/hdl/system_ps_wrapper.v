//Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
//Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
//--------------------------------------------------------------------------------
//Tool Version: Vivado v.2025.2.1 (win64) Build 6403652 Thu Mar 19 19:48:24 GMT 2026
//Date        : Mon Nov  2 09:28:21 2026
//Host        : NYANKO-YUE running 64-bit major release  (build 9200)
//Command     : generate_target system_ps_wrapper.bd
//Design      : system_ps_wrapper
//Purpose     : IP block netlist
//--------------------------------------------------------------------------------
`timescale 1 ps / 1 ps

module system_ps_wrapper
   (cfg,
    clk,
    control_araddr,
    control_arprot,
    control_arready,
    control_arvalid,
    control_awaddr,
    control_awprot,
    control_awready,
    control_awvalid,
    control_bready,
    control_bresp,
    control_bvalid,
    control_rdata,
    control_rready,
    control_rresp,
    control_rvalid,
    control_shutdown,
    control_wdata,
    control_wready,
    control_wstrb,
    control_wvalid,
    memory_araddr,
    memory_arburst,
    memory_arcache,
    memory_arid,
    memory_arlen,
    memory_arlock,
    memory_arprot,
    memory_arqos,
    memory_arready,
    memory_arregion,
    memory_arsize,
    memory_arvalid,
    memory_awaddr,
    memory_awburst,
    memory_awcache,
    memory_awid,
    memory_awlen,
    memory_awlock,
    memory_awprot,
    memory_awqos,
    memory_awready,
    memory_awregion,
    memory_awsize,
    memory_awvalid,
    memory_bid,
    memory_bready,
    memory_bresp,
    memory_bvalid,
    memory_rdata,
    memory_rid,
    memory_rlast,
    memory_rready,
    memory_rresp,
    memory_rvalid,
    memory_shutdown,
    memory_wdata,
    memory_wlast,
    memory_wready,
    memory_wstrb,
    memory_wvalid,
    resetn,
    rx_tdata,
    rx_tkeep,
    rx_tlast,
    rx_tready,
    rx_tstrb,
    rx_tuser,
    rx_tvalid,
    shutdown_request,
    status,
    tx_tdata,
    tx_tkeep,
    tx_tlast,
    tx_tready,
    tx_tstrb,
    tx_tuser,
    tx_tvalid);
  output [31:0]cfg;
  output clk;
  output [15:0]control_araddr;
  output [2:0]control_arprot;
  input control_arready;
  output control_arvalid;
  output [15:0]control_awaddr;
  output [2:0]control_awprot;
  input control_awready;
  output control_awvalid;
  output control_bready;
  input [1:0]control_bresp;
  input control_bvalid;
  input [31:0]control_rdata;
  output control_rready;
  input [1:0]control_rresp;
  input control_rvalid;
  output control_shutdown;
  output [31:0]control_wdata;
  input control_wready;
  output [3:0]control_wstrb;
  output control_wvalid;
  input [39:0]memory_araddr;
  input [1:0]memory_arburst;
  input [3:0]memory_arcache;
  input [0:0]memory_arid;
  input [7:0]memory_arlen;
  input memory_arlock;
  input [2:0]memory_arprot;
  input [3:0]memory_arqos;
  output memory_arready;
  input [3:0]memory_arregion;
  input [2:0]memory_arsize;
  input memory_arvalid;
  input [39:0]memory_awaddr;
  input [1:0]memory_awburst;
  input [3:0]memory_awcache;
  input [0:0]memory_awid;
  input [7:0]memory_awlen;
  input memory_awlock;
  input [2:0]memory_awprot;
  input [3:0]memory_awqos;
  output memory_awready;
  input [3:0]memory_awregion;
  input [2:0]memory_awsize;
  input memory_awvalid;
  output [0:0]memory_bid;
  input memory_bready;
  output [1:0]memory_bresp;
  output memory_bvalid;
  output [127:0]memory_rdata;
  output [0:0]memory_rid;
  output memory_rlast;
  input memory_rready;
  output [1:0]memory_rresp;
  output memory_rvalid;
  output memory_shutdown;
  input [127:0]memory_wdata;
  input memory_wlast;
  output memory_wready;
  input [15:0]memory_wstrb;
  input memory_wvalid;
  output [0:0]resetn;
  input [511:0]rx_tdata;
  input [63:0]rx_tkeep;
  input [0:0]rx_tlast;
  output rx_tready;
  input [63:0]rx_tstrb;
  input [0:0]rx_tuser;
  input rx_tvalid;
  input shutdown_request;
  input [31:0]status;
  output [511:0]tx_tdata;
  output [63:0]tx_tkeep;
  output [0:0]tx_tlast;
  input tx_tready;
  output [63:0]tx_tstrb;
  output [0:0]tx_tuser;
  output tx_tvalid;

  wire [31:0]cfg;
  wire clk;
  wire [15:0]control_araddr;
  wire [2:0]control_arprot;
  wire control_arready;
  wire control_arvalid;
  wire [15:0]control_awaddr;
  wire [2:0]control_awprot;
  wire control_awready;
  wire control_awvalid;
  wire control_bready;
  wire [1:0]control_bresp;
  wire control_bvalid;
  wire [31:0]control_rdata;
  wire control_rready;
  wire [1:0]control_rresp;
  wire control_rvalid;
  wire control_shutdown;
  wire [31:0]control_wdata;
  wire control_wready;
  wire [3:0]control_wstrb;
  wire control_wvalid;
  wire [39:0]memory_araddr;
  wire [1:0]memory_arburst;
  wire [3:0]memory_arcache;
  wire [0:0]memory_arid;
  wire [7:0]memory_arlen;
  wire memory_arlock;
  wire [2:0]memory_arprot;
  wire [3:0]memory_arqos;
  wire memory_arready;
  wire [3:0]memory_arregion;
  wire [2:0]memory_arsize;
  wire memory_arvalid;
  wire [39:0]memory_awaddr;
  wire [1:0]memory_awburst;
  wire [3:0]memory_awcache;
  wire [0:0]memory_awid;
  wire [7:0]memory_awlen;
  wire memory_awlock;
  wire [2:0]memory_awprot;
  wire [3:0]memory_awqos;
  wire memory_awready;
  wire [3:0]memory_awregion;
  wire [2:0]memory_awsize;
  wire memory_awvalid;
  wire [0:0]memory_bid;
  wire memory_bready;
  wire [1:0]memory_bresp;
  wire memory_bvalid;
  wire [127:0]memory_rdata;
  wire [0:0]memory_rid;
  wire memory_rlast;
  wire memory_rready;
  wire [1:0]memory_rresp;
  wire memory_rvalid;
  wire memory_shutdown;
  wire [127:0]memory_wdata;
  wire memory_wlast;
  wire memory_wready;
  wire [15:0]memory_wstrb;
  wire memory_wvalid;
  wire [0:0]resetn;
  wire [511:0]rx_tdata;
  wire [63:0]rx_tkeep;
  wire [0:0]rx_tlast;
  wire rx_tready;
  wire [63:0]rx_tstrb;
  wire [0:0]rx_tuser;
  wire rx_tvalid;
  wire shutdown_request;
  wire [31:0]status;
  wire [511:0]tx_tdata;
  wire [63:0]tx_tkeep;
  wire [0:0]tx_tlast;
  wire tx_tready;
  wire [63:0]tx_tstrb;
  wire [0:0]tx_tuser;
  wire tx_tvalid;

  system_ps system_ps_i
       (.cfg(cfg),
        .clk(clk),
        .control_araddr(control_araddr),
        .control_arprot(control_arprot),
        .control_arready(control_arready),
        .control_arvalid(control_arvalid),
        .control_awaddr(control_awaddr),
        .control_awprot(control_awprot),
        .control_awready(control_awready),
        .control_awvalid(control_awvalid),
        .control_bready(control_bready),
        .control_bresp(control_bresp),
        .control_bvalid(control_bvalid),
        .control_rdata(control_rdata),
        .control_rready(control_rready),
        .control_rresp(control_rresp),
        .control_rvalid(control_rvalid),
        .control_shutdown(control_shutdown),
        .control_wdata(control_wdata),
        .control_wready(control_wready),
        .control_wstrb(control_wstrb),
        .control_wvalid(control_wvalid),
        .memory_araddr(memory_araddr),
        .memory_arburst(memory_arburst),
        .memory_arcache(memory_arcache),
        .memory_arid(memory_arid),
        .memory_arlen(memory_arlen),
        .memory_arlock(memory_arlock),
        .memory_arprot(memory_arprot),
        .memory_arqos(memory_arqos),
        .memory_arready(memory_arready),
        .memory_arregion(memory_arregion),
        .memory_arsize(memory_arsize),
        .memory_arvalid(memory_arvalid),
        .memory_awaddr(memory_awaddr),
        .memory_awburst(memory_awburst),
        .memory_awcache(memory_awcache),
        .memory_awid(memory_awid),
        .memory_awlen(memory_awlen),
        .memory_awlock(memory_awlock),
        .memory_awprot(memory_awprot),
        .memory_awqos(memory_awqos),
        .memory_awready(memory_awready),
        .memory_awregion(memory_awregion),
        .memory_awsize(memory_awsize),
        .memory_awvalid(memory_awvalid),
        .memory_bid(memory_bid),
        .memory_bready(memory_bready),
        .memory_bresp(memory_bresp),
        .memory_bvalid(memory_bvalid),
        .memory_rdata(memory_rdata),
        .memory_rid(memory_rid),
        .memory_rlast(memory_rlast),
        .memory_rready(memory_rready),
        .memory_rresp(memory_rresp),
        .memory_rvalid(memory_rvalid),
        .memory_shutdown(memory_shutdown),
        .memory_wdata(memory_wdata),
        .memory_wlast(memory_wlast),
        .memory_wready(memory_wready),
        .memory_wstrb(memory_wstrb),
        .memory_wvalid(memory_wvalid),
        .resetn(resetn),
        .rx_tdata(rx_tdata),
        .rx_tkeep(rx_tkeep),
        .rx_tlast(rx_tlast),
        .rx_tready(rx_tready),
        .rx_tstrb(rx_tstrb),
        .rx_tuser(rx_tuser),
        .rx_tvalid(rx_tvalid),
        .shutdown_request(shutdown_request),
        .status(status),
        .tx_tdata(tx_tdata),
        .tx_tkeep(tx_tkeep),
        .tx_tlast(tx_tlast),
        .tx_tready(tx_tready),
        .tx_tstrb(tx_tstrb),
        .tx_tuser(tx_tuser),
        .tx_tvalid(tx_tvalid));
endmodule

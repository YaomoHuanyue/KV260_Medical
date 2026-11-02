`timescale 1ns/1ps
// Optional AXI-Lite diagnostic bank. No AXI memory/DMA signals pass through it.
// ENABLE_DIAGNOSTICS=0 is a wire-only control bypass, with no counters attached.
module medical_axi_profile_control_r329 #(
    parameter ENABLE_DIAGNOSTICS = 1
)(
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
    input wire profile_active, snapshot_valid,
    input wire [1023:0] counters,
    input wire [31:0] pending_reads,pending_writes,
    output wire run_start,run_stop
);
generate if (!ENABLE_DIAGNOSTICS) begin: production_bypass
    assign m_awaddr=s_awaddr[7:0];assign m_awvalid=s_awvalid;assign s_awready=m_awready;
    assign m_wdata=s_wdata;assign m_wstrb=s_wstrb;assign m_wvalid=s_wvalid;assign s_wready=m_wready;
    assign s_bresp=m_bresp;assign s_bvalid=m_bvalid;assign m_bready=s_bready;
    assign m_araddr=s_araddr[7:0];assign m_arvalid=s_arvalid;assign s_arready=m_arready;
    assign s_rdata=m_rdata;assign s_rresp=m_rresp;assign s_rvalid=m_rvalid;assign m_rready=s_rready;
    assign run_start=1'b0;assign run_stop=1'b0;
end else begin: diagnostics
    // One outstanding transaction per direction. AW and W are captured
    // independently, then held until each downstream channel accepts it.
    reg [15:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0,rdata=0;
    reg [3:0] wstrb=0;
    reg aw_held=0,w_held=0,aw_sent=0,w_sent=0;
    reg [1:0] bresp=0,rresp=0;
    reg bvalid=0,rvalid=0,rd_forward=0,ar_sent=0;
    reg start_pulse=0,stop_pulse=0;
    wire wr_diag=awaddr[15:12]==4'hf;
    wire wr_pair=aw_held&&w_held&&!bvalid;
    assign s_awready=resetn&&!aw_held&&!bvalid;
    assign s_wready=resetn&&!w_held&&!bvalid;
    assign m_awaddr=awaddr[7:0];assign m_awvalid=resetn&&wr_pair&&!wr_diag&&!aw_sent;
    assign m_wdata=wdata;assign m_wstrb=wstrb;assign m_wvalid=resetn&&wr_pair&&!wr_diag&&!w_sent;
    assign m_bready=resetn&&wr_pair&&!wr_diag&&aw_sent&&w_sent;
    assign s_bresp=bresp;assign s_bvalid=bvalid;
    assign s_arready=resetn&&!rd_forward&&!rvalid;
    assign m_araddr=araddr[7:0];assign m_arvalid=resetn&&rd_forward&&!ar_sent;
    assign m_rready=resetn&&rd_forward&&ar_sent&&!rvalid;
    assign s_rdata=rdata;assign s_rresp=rresp;assign s_rvalid=rvalid;
    assign run_start=start_pulse;assign run_stop=stop_pulse;
    integer index;
    always @(posedge clk) begin
        if(!resetn) begin
            awaddr<=0;araddr<=0;wdata<=0;wstrb<=0;rdata<=0;
            aw_held<=0;w_held<=0;aw_sent<=0;w_sent<=0;
            bresp<=0;rresp<=0;bvalid<=0;rvalid<=0;rd_forward<=0;ar_sent<=0;
            start_pulse<=0;stop_pulse<=0;
        end else begin
            start_pulse<=0;stop_pulse<=0;
            if(s_awvalid&&s_awready)begin awaddr<=s_awaddr;aw_held<=1;end
            if(s_wvalid&&s_wready)begin wdata<=s_wdata;wstrb<=s_wstrb;w_held<=1;end
            if(m_awvalid&&m_awready)aw_sent<=1;
            if(m_wvalid&&m_wready)w_sent<=1;
            if(wr_pair&&wr_diag)begin
                bvalid<=1;bresp<=2'b10;
                if(awaddr==16'hf000)begin
                    if(!wstrb[0]||wdata[7:0]==0)bresp<=0;
                    else if(wdata[7:0]==1)begin start_pulse<=1;bresp<=0;end
                    else if(wdata[7:0]==2)begin stop_pulse<=1;bresp<=0;end
                end
            end
            if(m_bvalid&&m_bready)begin bvalid<=1;bresp<=m_bresp;end
            if(s_bvalid&&s_bready)begin bvalid<=0;aw_held<=0;w_held<=0;aw_sent<=0;w_sent<=0;end
            if(s_arvalid&&s_arready)begin
                araddr<=s_araddr;ar_sent<=0;
                if(s_araddr[15:12]==4'hf)begin
                    rvalid<=1;rdata<=0;rresp<=2'b10;
                    case(s_araddr)
                        16'hf000:begin rdata<=0;rresp<=0;end
                        16'hf004:begin rdata<=32'h4d415850;rresp<=0;end
                        16'hf008:begin rdata<=32'h00011040;rresp<=0;end
                        16'hf00c:begin rdata<={30'b0,snapshot_valid,profile_active};rresp<=0;end
                        16'hf010:begin rdata<=pending_reads;rresp<=0;end
                        16'hf014:begin rdata<=pending_writes;rresp<=0;end
                        default:begin
                            if(s_araddr>=16'hf020&&s_araddr<=16'hf09c&&s_araddr[1:0]==0&&snapshot_valid&&!profile_active)begin
                                index=(s_araddr-16'hf020)>>2;
                                rdata<=counters[index*32 +: 32];rresp<=0;
                            end
                        end
                    endcase
                end else rd_forward<=1;
            end
            if(m_arvalid&&m_arready)ar_sent<=1;
            if(m_rvalid&&m_rready)begin rvalid<=1;rdata<=m_rdata;rresp<=m_rresp;rd_forward<=0;ar_sent<=0;end
            if(s_rvalid&&s_rready)rvalid<=0;
        end
    end
end endgenerate
endmodule

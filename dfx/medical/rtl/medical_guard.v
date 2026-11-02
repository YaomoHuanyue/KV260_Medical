`timescale 1ns/1ps
// Software first waits for algorithm ap_idle and both static DMA engines.
// Hardware then waits for BOTH AXI shutdown acknowledgements and AXIS TLAST.
module medical_guard(input clk,input resetn,input [31:0] cfg,
 input control_shutdown,input memory_shutdown,input tx_valid,input tx_ready,
 input rx_valid,input rx_ready,input rx_last,
 output reg isolated=1,output reg busy=0,output reg [15:0] transactions=0,
 output rm_resetn);
assign rm_resetn=resetn&&!isolated;
always @(posedge clk)begin
 if(!resetn)begin isolated<=1;busy<=0;transactions<=0;end
 else begin
  if(cfg[0]&&control_shutdown&&memory_shutdown&&!busy&&!(tx_valid&&tx_ready))isolated<=1;
  else if(!cfg[0]&&cfg[1])isolated<=0;
  if(tx_valid&&tx_ready)busy<=1;
  if(rx_valid&&rx_ready&&rx_last)begin busy<=0;transactions<=transactions+1;end
 end
end
endmodule

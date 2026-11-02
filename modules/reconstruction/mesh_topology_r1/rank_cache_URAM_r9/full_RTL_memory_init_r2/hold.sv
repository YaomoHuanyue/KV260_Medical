`timescale 1ns/1ps
// Simulation-only monitor, not included in a hardware release.
module topology_hold #(parameter integer BITS=1)(
 input logic clk,resetn,valid,ready,input logic[BITS-1:0] payload);
 logic stalled=0;logic[BITS-1:0] previous;
 always @(posedge clk)begin
  if(!resetn)stalled<=0;
  else begin
   if(stalled && (!valid || payload!==previous))$fatal(1,"AXI/AXIS changed a stalled payload");
   stalled<=valid&&!ready;previous<=payload;
  end
 end
endmodule

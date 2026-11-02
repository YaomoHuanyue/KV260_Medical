`timescale 1ns/1ps
// The fixed static writer consumes a programmed count. Pad a compact route
// packet to its declared maximum, preserving its useful payload unchanged.
// Scene loads also use this count; the host only interprets the first word.
module route_pad #(parameter WORDS=8706)(input clk,input resetn,
 input s_valid,output s_ready,input [511:0] s_data,input [63:0] s_keep,s_strb,input s_user,s_last,
 output m_valid,input m_ready,output [511:0] m_data,output [63:0] m_keep,m_strb,output m_user,m_last);
reg padding=0;reg [13:0] count=0;
assign s_ready=m_ready&&!padding;
assign m_valid=padding||s_valid;
assign m_data=padding?512'b0:s_data;
assign m_keep=padding?64'hffffffffffffffff:s_keep;
assign m_strb=padding?64'hffffffffffffffff:s_strb;
assign m_user=(count==0)&&!padding&&s_user;
assign m_last=count==WORDS-1;
always @(posedge clk)begin
 if(!resetn)begin padding<=0;count<=0;end
 else if(m_valid&&m_ready)begin
  if(count==WORDS-1)begin count<=0;padding<=0;end
  else begin count<=count+1'b1;if(s_last&&!padding)padding<=1;end
 end
end
endmodule

// Passive transfer history. Page 0: clock counter; 1..16: VALID && READY counts.
// Page is selected by GPIO channel 1's output latch while its pins stay inputs.
module stream_monitor(input wire clk, input wire resetn,
                      input wire [31:0] signals, input wire [31:0] page,
                      output reg [31:0] value);
  reg [31:0] cycles=0;
  reg [31:0] counts [0:15];
  integer i;
  always @(posedge clk) begin
    if (!resetn) begin
      cycles <= 0;
      for (i=0;i<16;i=i+1) counts[i] <= 0;
    end else begin
      cycles <= cycles+1;
      for (i=0;i<16;i=i+1)
        if (signals[i*2] && signals[i*2+1]) counts[i] <= counts[i]+1;
    end
  end
  always @* begin
    value=32'hbad00000;
    if (page==0) value=cycles;
    else if (page<=16) value=counts[page-1];
  end
endmodule

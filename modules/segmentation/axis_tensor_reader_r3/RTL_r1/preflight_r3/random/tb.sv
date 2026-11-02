`timescale 1ns/1ps
// Simulation only. No stimulus, golden model or monitor enters the PL source.
module tb;
 localparam integer STALLS=1;
 logic  clk;
 logic  resetn;
 wire  m_awvalid;
 logic  m_awready;
 wire [64 - 1:0] m_awaddr;
 wire [1 - 1:0] m_awid;
 wire [7:0] m_awlen;
 wire [2:0] m_awsize;
 wire [1:0] m_awburst;
 wire [1:0] m_awlock;
 wire [3:0] m_awcache;
 wire [2:0] m_awprot;
 wire [3:0] m_awqos;
 wire [3:0] m_awregion;
 wire [1 - 1:0] m_awuser;
 wire  m_wvalid;
 logic  m_wready;
 wire [256 - 1:0] m_wdata;
 wire [32 - 1:0] m_wstrb;
 wire  m_wlast;
 wire [1 - 1:0] m_wid;
 wire [1 - 1:0] m_wuser;
 wire  m_arvalid;
 logic  m_arready;
 wire [64 - 1:0] m_araddr;
 wire [1 - 1:0] m_arid;
 wire [7:0] m_arlen;
 wire [2:0] m_arsize;
 wire [1:0] m_arburst;
 wire [1:0] m_arlock;
 wire [3:0] m_arcache;
 wire [2:0] m_arprot;
 wire [3:0] m_arqos;
 wire [3:0] m_arregion;
 wire [1 - 1:0] m_aruser;
 logic  m_rvalid;
 wire  m_rready;
 logic [256 - 1:0] m_rdata;
 logic  m_rlast;
 logic [1 - 1:0] m_rid;
 logic [1 - 1:0] m_ruser;
 logic [1:0] m_rresp;
 logic  m_bvalid;
 wire  m_bready;
 logic [1:0] m_bresp;
 logic [1 - 1:0] m_bid;
 logic [1 - 1:0] m_buser;
 wire [255:0] s_data;
 wire  s_valid;
 logic  s_ready;
 wire [31:0] s_keep;
 wire [31:0] s_strb;
 wire [0:0] s_last;
 logic  c_awvalid;
 wire  c_awready;
 logic [8 - 1:0] c_awaddr;
 logic  c_wvalid;
 wire  c_wready;
 logic [32 - 1:0] c_wdata;
 logic [4 - 1:0] c_wstrb;
 logic  c_arvalid;
 wire  c_arready;
 logic [8 - 1:0] c_araddr;
 wire  c_rvalid;
 logic  c_rready;
 wire [32 - 1:0] c_rdata;
 wire [1:0] c_rresp;
 wire  c_bvalid;
 logic  c_bready;
 wire [1:0] c_bresp;
 wire  irq;
 ct_tensor_reader dut(.ap_clk(clk),
.ap_rst_n(resetn),
.m_axi_memory_AWVALID(m_awvalid),
.m_axi_memory_AWREADY(m_awready),
.m_axi_memory_AWADDR(m_awaddr),
.m_axi_memory_AWID(m_awid),
.m_axi_memory_AWLEN(m_awlen),
.m_axi_memory_AWSIZE(m_awsize),
.m_axi_memory_AWBURST(m_awburst),
.m_axi_memory_AWLOCK(m_awlock),
.m_axi_memory_AWCACHE(m_awcache),
.m_axi_memory_AWPROT(m_awprot),
.m_axi_memory_AWQOS(m_awqos),
.m_axi_memory_AWREGION(m_awregion),
.m_axi_memory_AWUSER(m_awuser),
.m_axi_memory_WVALID(m_wvalid),
.m_axi_memory_WREADY(m_wready),
.m_axi_memory_WDATA(m_wdata),
.m_axi_memory_WSTRB(m_wstrb),
.m_axi_memory_WLAST(m_wlast),
.m_axi_memory_WID(m_wid),
.m_axi_memory_WUSER(m_wuser),
.m_axi_memory_ARVALID(m_arvalid),
.m_axi_memory_ARREADY(m_arready),
.m_axi_memory_ARADDR(m_araddr),
.m_axi_memory_ARID(m_arid),
.m_axi_memory_ARLEN(m_arlen),
.m_axi_memory_ARSIZE(m_arsize),
.m_axi_memory_ARBURST(m_arburst),
.m_axi_memory_ARLOCK(m_arlock),
.m_axi_memory_ARCACHE(m_arcache),
.m_axi_memory_ARPROT(m_arprot),
.m_axi_memory_ARQOS(m_arqos),
.m_axi_memory_ARREGION(m_arregion),
.m_axi_memory_ARUSER(m_aruser),
.m_axi_memory_RVALID(m_rvalid),
.m_axi_memory_RREADY(m_rready),
.m_axi_memory_RDATA(m_rdata),
.m_axi_memory_RLAST(m_rlast),
.m_axi_memory_RID(m_rid),
.m_axi_memory_RUSER(m_ruser),
.m_axi_memory_RRESP(m_rresp),
.m_axi_memory_BVALID(m_bvalid),
.m_axi_memory_BREADY(m_bready),
.m_axi_memory_BRESP(m_bresp),
.m_axi_memory_BID(m_bid),
.m_axi_memory_BUSER(m_buser),
.pixels_TDATA(s_data),
.pixels_TVALID(s_valid),
.pixels_TREADY(s_ready),
.pixels_TKEEP(s_keep),
.pixels_TSTRB(s_strb),
.pixels_TLAST(s_last),
.s_axi_control_AWVALID(c_awvalid),
.s_axi_control_AWREADY(c_awready),
.s_axi_control_AWADDR(c_awaddr),
.s_axi_control_WVALID(c_wvalid),
.s_axi_control_WREADY(c_wready),
.s_axi_control_WDATA(c_wdata),
.s_axi_control_WSTRB(c_wstrb),
.s_axi_control_ARVALID(c_arvalid),
.s_axi_control_ARREADY(c_arready),
.s_axi_control_ARADDR(c_araddr),
.s_axi_control_RVALID(c_rvalid),
.s_axi_control_RREADY(c_rready),
.s_axi_control_RDATA(c_rdata),
.s_axi_control_RRESP(c_rresp),
.s_axi_control_BVALID(c_bvalid),
.s_axi_control_BREADY(c_bready),
.s_axi_control_BRESP(c_bresp),
.interrupt(irq));
 initial clk=0;always #5 clk=~clk;
 logic[31:0] random_state=32'hb41c239a;
 logic active=0,invalid=0,done_seen=0,force_ar=0,force_r=0,force_axis=0;
 integer case_id=-1,h,w,ca,cb,fa,fb,k,mode,ci,groups,model_id=-1;
 integer a_bytes,b_bytes,lut_bytes,total_packets,word_index=0,frames=0,resets=0;
 logic[63:0] a_base,b_base,lut_base;
 longint unsigned cycles=0,start_cycle=0,axis_stalls=0,ar_stalls=0,r_stalls=0,reads=0,beats=0;
 logic read_busy=0;logic[63:0] read_address;integer remaining;logic read_id;
 logic[7:0] model_lut[0:1535];
 assign m_awready=0;assign m_wready=0;assign m_bvalid=0;assign m_bresp=0;assign m_bid=0;assign m_buser=0;
 assign m_arready=resetn&&!read_busy&&!m_rvalid&&!force_ar&&(!STALLS||random_state[1]);
 assign m_rresp=0;assign m_ruser=0;
 always @(negedge clk)s_ready=resetn&&!force_axis&&(!STALLS||random_state[3:2]!=0);

 topology_hold #(.BITS(321)) hs(clk,resetn,s_valid,s_ready,{s_data,s_keep,s_strb,s_last});
 topology_hold #(.BITS(96)) har(clk,resetn,m_arvalid,m_arready,{m_araddr,m_arid,m_arlen,m_arsize,m_arburst,m_arlock,m_arcache,m_arprot,m_arqos,m_arregion,m_aruser});
 topology_hold #(.BITS(261)) hr(clk,resetn,m_rvalid,m_rready,{m_rdata,m_rlast,m_rid,m_ruser,m_rresp});
 topology_hold #(.BITS(8)) hcaw(clk,resetn,c_awvalid,c_awready,c_awaddr);
 topology_hold #(.BITS(36)) hcw(clk,resetn,c_wvalid,c_wready,{c_wdata,c_wstrb});
 topology_hold #(.BITS(8)) hcar(clk,resetn,c_arvalid,c_arready,c_araddr);
 topology_hold #(.BITS(34)) hcr(clk,resetn,c_rvalid,c_rready,{c_rdata,c_rresp});
 topology_hold #(.BITS(2)) hcb(clk,resetn,c_bvalid,c_bready,c_bresp);

 function automatic logic[7:0] pattern(input integer branch,y,x,c,seed);
  logic[31:0] v;
  v=(32'(y)*32'd1103515245)^(32'(x)*32'd2654435761)^(32'(c)*32'd2246822519)^(32'(seed)*32'd3266489917)^(32'(branch)*32'd668265263);
  v=v^(v>>15);v=v*32'd2246822519;v=v^(v>>13);return (v^(v>>16))&255;
 endfunction
 function automatic logic[7:0] table_byte(input integer branch,index);
  if(model_id>=0)return model_lut[model_id*512+branch*256+index];
  if(mode==0)return 8'(index);
  return pattern(branch,case_id,index,branch+3,919);
 endfunction
 function automatic logic[7:0] source_byte(input integer branch,offset);
  integer channels,factor,padded,pixel,c,y,x;
  channels=branch?cb:ca;factor=branch?fb:fa;padded=((channels+7)/8)*8;
  pixel=offset/padded;c=offset%padded;y=pixel/(w/factor);x=pixel%(w/factor);
  if(c>=channels)return 0;
  return pattern(branch,y,x,c,947923+case_id);
 endfunction
 function automatic logic[7:0] expected_byte(input integer y,x,c);
  integer branch,factor,local_c;logic[7:0] raw;
  if(c>=ci)return 0;
  if(mode==0)return pattern(0,y,x,c,947923+case_id);
  branch=c<ca?0:1;factor=branch?fb:fa;local_c=branch?c-ca:c;
  raw=pattern(branch,y/factor,x/factor,local_c,947923+case_id);
  return table_byte(branch,int'(raw));
 endfunction
 function automatic logic[7:0] memory_byte(input logic[63:0] address);
  integer offset;
  if(address>=a_base&&address<a_base+a_bytes)begin
   offset=int'(address-a_base);
   if(offset>=h/fa*(w/fa)*((ca+7)/8)*8)return 0;
   return source_byte(0,offset);
  end
  if(cb&&address>=b_base&&address<b_base+b_bytes)begin
   offset=int'(address-b_base);
   if(offset>=h/fb*(w/fb)*((cb+7)/8)*8)return 0;
   return source_byte(1,offset);
  end
  if(mode&&address>=lut_base&&address<lut_base+lut_bytes)begin
   offset=int'(address-lut_base);return table_byte(offset/256,offset%256);
  end
  $fatal(1,"READER illegal DDR byte case=%0d address=%h",case_id,address);return 0;
 endfunction
 function automatic bit contained(input logic[63:0] address,endpoint,base,input integer bytes);
  return bytes>0&&address>=base&&endpoint<=base+64'(bytes);
 endfunction
 function automatic logic[255:0] golden(input integer packet);
  logic[255:0] result;integer at,pixel,c,y,x,g;
  result=0;
  if(k==1)begin
   for(integer j=0;j<32;j=j+1)begin
    at=packet*32+j;
    if(at<h*w*groups*8)begin
     pixel=at/(groups*8);c=at%(groups*8);
     result[j*8+:8]=expected_byte(pixel/w,pixel%w,c);
    end
   end
  end else begin
   g=packet%groups;pixel=packet/groups;y=pixel/(w+2);x=pixel%(w+2);
   if(y>=1&&y<=h&&x>=1&&x<=w)
    for(integer j=0;j<8;j=j+1)result[j*8+:8]=expected_byte(y-1,x-1,g*8+j);
  end
  return result;
 endfunction

 always @(posedge clk)begin : monitor
  logic[63:0] endpoint;logic[255:0] expected;logic[31:0] keep;integer remain;
  cycles=cycles+1;
  if(!resetn)begin
   random_state<=32'hb41c239a;read_busy<=0;m_rvalid<=0;m_rlast<=0;m_rdata<=0;m_rid<=0;done_seen=0;word_index=0;
  end else begin
   random_state<={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
   if(m_awvalid||m_wvalid)$fatal(1,"Read-only core attempted DDR mutation");
   if(active&&s_valid&&!s_ready)axis_stalls=axis_stalls+1;
   if(active&&m_arvalid&&!m_arready)ar_stalls=ar_stalls+1;
   if(active&&m_rvalid&&!m_rready)r_stalls=r_stalls+1;
   if(m_arvalid&&m_arready)begin
    endpoint=m_araddr+(64'(m_arlen)+1)*32;
    if(!active||invalid||m_arburst!=1||m_arsize!=5||m_araddr%32!=0||endpoint>64'h80000000||
       (m_araddr&4095)+(64'(m_arlen)+1)*32>4096||
       !(contained(m_araddr,endpoint,a_base,a_bytes)||(cb&&contained(m_araddr,endpoint,b_base,b_bytes))||
         (mode&&contained(m_araddr,endpoint,lut_base,lut_bytes))))
     $fatal(1,"READER AXI range/4K/shape case=%0d address=%h len=%0d",case_id,m_araddr,m_arlen);
    read_busy<=1;read_address<=m_araddr;remaining<=int'(m_arlen)+1;read_id<=m_arid;reads=reads+1;
   end
   if(m_rvalid&&m_rready)begin m_rvalid<=0;beats=beats+1;end
   if(read_busy&&!m_rvalid&&!force_r&&(!STALLS||random_state[5:4]!=0))begin
    for(integer j=0;j<32;j=j+1)m_rdata[j*8+:8]<=memory_byte(read_address+j);
    m_rvalid<=1;m_rlast<=remaining==1;m_rid<=read_id;
    if(remaining==1)read_busy<=0;
    else begin read_address<=read_address+32;remaining<=remaining-1;end
   end
   if(s_valid&&s_ready)begin
    if(!active||invalid||word_index>=total_packets)$fatal(1,"READER extra output packet case=%0d packet=%0d",case_id,word_index);
    expected=golden(word_index);remain=h*w*groups*8-word_index*32;
    keep=k==3?32'hff:(word_index+1<total_packets||remain==32?32'hffffffff:((32'h1<<remain)-1));
    if(s_data!==expected||s_keep!==keep||s_strb!==keep||s_last!==(word_index+1==total_packets))
     $fatal(1,"READER full data/keep/strb/last differs case=%0d packet=%0d got=%h want=%h",case_id,word_index,s_data,expected);
    word_index=word_index+1;
   end
   if(active&&dut.ap_done)done_seen=1;
   if(active&&cycles-start_cycle>64'(total_packets)*256+1000000)$fatal(1,"READER cycle watchdog case=%0d",case_id);
  end
 end

 task automatic write_reg(input logic[7:0] address,input logic[31:0] value);
  @(negedge clk);c_awaddr=address;c_awvalid=1;
  do @(posedge clk);while(!c_awready);
  @(negedge clk);c_awvalid=0;c_wdata=value;c_wstrb=15;c_wvalid=1;c_bready=0;
  do @(posedge clk);while(!c_wready);
  @(negedge clk);c_wvalid=0;
  if(STALLS)repeat(random_state[6:5])@(negedge clk);
  c_bready=1;do @(posedge clk);while(!c_bvalid);
  if(c_bresp!==0)$fatal(1,"AXIL write error");@(negedge clk);c_bready=0;
 endtask
 task automatic read_reg(input logic[7:0] address,output logic[31:0] value);
  @(negedge clk);c_araddr=address;c_arvalid=1;c_rready=0;
  do @(posedge clk);while(!c_arready);
  @(negedge clk);c_arvalid=0;
  if(STALLS)repeat(random_state[8:7])@(negedge clk);
  c_rready=1;do @(posedge clk);while(!c_rvalid);
  value=c_rdata;if(c_rresp!==0)$fatal(1,"AXIL read error");@(negedge clk);c_rready=0;
 endtask
 task automatic prepare(input integer index);
  if(read_busy||m_rvalid||s_valid)$fatal(1,"Outstanding DDR/AXIS between frames");
  @(negedge clk);case_id=index;model_id=-1;
  case(index)
   0:begin h=1;w=1;ca=1;cb=0;fa=1;fb=1;k=1;mode=0;ci=1;invalid=0;model_id=-1;end
   1:begin h=1;w=1;ca=5;cb=0;fa=1;fb=1;k=1;mode=0;ci=5;invalid=0;model_id=-1;end
   2:begin h=1;w=1;ca=8;cb=0;fa=1;fb=1;k=1;mode=0;ci=8;invalid=0;model_id=-1;end
   3:begin h=1;w=1;ca=9;cb=0;fa=1;fb=1;k=1;mode=0;ci=9;invalid=0;model_id=-1;end
   4:begin h=1;w=1;ca=31;cb=0;fa=1;fb=1;k=1;mode=0;ci=31;invalid=0;model_id=-1;end
   5:begin h=1;w=1;ca=32;cb=0;fa=1;fb=1;k=1;mode=0;ci=32;invalid=0;model_id=-1;end
   6:begin h=1;w=1;ca=63;cb=0;fa=1;fb=1;k=1;mode=0;ci=63;invalid=0;model_id=-1;end
   7:begin h=1;w=1;ca=64;cb=0;fa=1;fb=1;k=1;mode=0;ci=64;invalid=0;model_id=-1;end
   8:begin h=1;w=7;ca=1;cb=0;fa=1;fb=1;k=1;mode=0;ci=1;invalid=0;model_id=-1;end
   9:begin h=1;w=7;ca=5;cb=0;fa=1;fb=1;k=1;mode=0;ci=5;invalid=0;model_id=-1;end
   10:begin h=1;w=7;ca=8;cb=0;fa=1;fb=1;k=1;mode=0;ci=8;invalid=0;model_id=-1;end
   11:begin h=1;w=7;ca=9;cb=0;fa=1;fb=1;k=1;mode=0;ci=9;invalid=0;model_id=-1;end
   12:begin h=1;w=7;ca=31;cb=0;fa=1;fb=1;k=1;mode=0;ci=31;invalid=0;model_id=-1;end
   13:begin h=1;w=7;ca=32;cb=0;fa=1;fb=1;k=1;mode=0;ci=32;invalid=0;model_id=-1;end
   14:begin h=1;w=7;ca=63;cb=0;fa=1;fb=1;k=1;mode=0;ci=63;invalid=0;model_id=-1;end
   15:begin h=1;w=7;ca=64;cb=0;fa=1;fb=1;k=1;mode=0;ci=64;invalid=0;model_id=-1;end
   16:begin h=3;w=5;ca=1;cb=0;fa=1;fb=1;k=1;mode=0;ci=1;invalid=0;model_id=-1;end
   17:begin h=3;w=5;ca=5;cb=0;fa=1;fb=1;k=1;mode=0;ci=5;invalid=0;model_id=-1;end
   18:begin h=3;w=5;ca=8;cb=0;fa=1;fb=1;k=1;mode=0;ci=8;invalid=0;model_id=-1;end
   19:begin h=3;w=5;ca=9;cb=0;fa=1;fb=1;k=1;mode=0;ci=9;invalid=0;model_id=-1;end
   20:begin h=3;w=5;ca=31;cb=0;fa=1;fb=1;k=1;mode=0;ci=31;invalid=0;model_id=-1;end
   21:begin h=3;w=5;ca=32;cb=0;fa=1;fb=1;k=1;mode=0;ci=32;invalid=0;model_id=-1;end
   22:begin h=3;w=5;ca=63;cb=0;fa=1;fb=1;k=1;mode=0;ci=63;invalid=0;model_id=-1;end
   23:begin h=3;w=5;ca=64;cb=0;fa=1;fb=1;k=1;mode=0;ci=64;invalid=0;model_id=-1;end
   24:begin h=8;w=16;ca=1;cb=0;fa=1;fb=1;k=1;mode=0;ci=1;invalid=0;model_id=-1;end
   25:begin h=8;w=16;ca=5;cb=0;fa=1;fb=1;k=1;mode=0;ci=5;invalid=0;model_id=-1;end
   26:begin h=8;w=16;ca=8;cb=0;fa=1;fb=1;k=1;mode=0;ci=8;invalid=0;model_id=-1;end
   27:begin h=8;w=16;ca=9;cb=0;fa=1;fb=1;k=1;mode=0;ci=9;invalid=0;model_id=-1;end
   28:begin h=8;w=16;ca=31;cb=0;fa=1;fb=1;k=1;mode=0;ci=31;invalid=0;model_id=-1;end
   29:begin h=8;w=16;ca=32;cb=0;fa=1;fb=1;k=1;mode=0;ci=32;invalid=0;model_id=-1;end
   30:begin h=8;w=16;ca=63;cb=0;fa=1;fb=1;k=1;mode=0;ci=63;invalid=0;model_id=-1;end
   31:begin h=8;w=16;ca=64;cb=0;fa=1;fb=1;k=1;mode=0;ci=64;invalid=0;model_id=-1;end
   32:begin h=1;w=1;ca=1;cb=0;fa=1;fb=1;k=3;mode=0;ci=1;invalid=0;model_id=-1;end
   33:begin h=1;w=1;ca=5;cb=0;fa=1;fb=1;k=3;mode=0;ci=5;invalid=0;model_id=-1;end
   34:begin h=1;w=1;ca=8;cb=0;fa=1;fb=1;k=3;mode=0;ci=8;invalid=0;model_id=-1;end
   35:begin h=1;w=1;ca=9;cb=0;fa=1;fb=1;k=3;mode=0;ci=9;invalid=0;model_id=-1;end
   36:begin h=1;w=1;ca=31;cb=0;fa=1;fb=1;k=3;mode=0;ci=31;invalid=0;model_id=-1;end
   37:begin h=1;w=1;ca=32;cb=0;fa=1;fb=1;k=3;mode=0;ci=32;invalid=0;model_id=-1;end
   38:begin h=1;w=1;ca=63;cb=0;fa=1;fb=1;k=3;mode=0;ci=63;invalid=0;model_id=-1;end
   39:begin h=1;w=1;ca=64;cb=0;fa=1;fb=1;k=3;mode=0;ci=64;invalid=0;model_id=-1;end
   40:begin h=1;w=7;ca=1;cb=0;fa=1;fb=1;k=3;mode=0;ci=1;invalid=0;model_id=-1;end
   41:begin h=1;w=7;ca=5;cb=0;fa=1;fb=1;k=3;mode=0;ci=5;invalid=0;model_id=-1;end
   42:begin h=1;w=7;ca=8;cb=0;fa=1;fb=1;k=3;mode=0;ci=8;invalid=0;model_id=-1;end
   43:begin h=1;w=7;ca=9;cb=0;fa=1;fb=1;k=3;mode=0;ci=9;invalid=0;model_id=-1;end
   44:begin h=1;w=7;ca=31;cb=0;fa=1;fb=1;k=3;mode=0;ci=31;invalid=0;model_id=-1;end
   45:begin h=1;w=7;ca=32;cb=0;fa=1;fb=1;k=3;mode=0;ci=32;invalid=0;model_id=-1;end
   46:begin h=1;w=7;ca=63;cb=0;fa=1;fb=1;k=3;mode=0;ci=63;invalid=0;model_id=-1;end
   47:begin h=1;w=7;ca=64;cb=0;fa=1;fb=1;k=3;mode=0;ci=64;invalid=0;model_id=-1;end
   48:begin h=3;w=5;ca=1;cb=0;fa=1;fb=1;k=3;mode=0;ci=1;invalid=0;model_id=-1;end
   49:begin h=3;w=5;ca=5;cb=0;fa=1;fb=1;k=3;mode=0;ci=5;invalid=0;model_id=-1;end
   50:begin h=3;w=5;ca=8;cb=0;fa=1;fb=1;k=3;mode=0;ci=8;invalid=0;model_id=-1;end
   51:begin h=3;w=5;ca=9;cb=0;fa=1;fb=1;k=3;mode=0;ci=9;invalid=0;model_id=-1;end
   52:begin h=3;w=5;ca=31;cb=0;fa=1;fb=1;k=3;mode=0;ci=31;invalid=0;model_id=-1;end
   53:begin h=3;w=5;ca=32;cb=0;fa=1;fb=1;k=3;mode=0;ci=32;invalid=0;model_id=-1;end
   54:begin h=3;w=5;ca=63;cb=0;fa=1;fb=1;k=3;mode=0;ci=63;invalid=0;model_id=-1;end
   55:begin h=3;w=5;ca=64;cb=0;fa=1;fb=1;k=3;mode=0;ci=64;invalid=0;model_id=-1;end
   56:begin h=8;w=16;ca=1;cb=0;fa=1;fb=1;k=3;mode=0;ci=1;invalid=0;model_id=-1;end
   57:begin h=8;w=16;ca=5;cb=0;fa=1;fb=1;k=3;mode=0;ci=5;invalid=0;model_id=-1;end
   58:begin h=8;w=16;ca=8;cb=0;fa=1;fb=1;k=3;mode=0;ci=8;invalid=0;model_id=-1;end
   59:begin h=8;w=16;ca=9;cb=0;fa=1;fb=1;k=3;mode=0;ci=9;invalid=0;model_id=-1;end
   60:begin h=8;w=16;ca=31;cb=0;fa=1;fb=1;k=3;mode=0;ci=31;invalid=0;model_id=-1;end
   61:begin h=8;w=16;ca=32;cb=0;fa=1;fb=1;k=3;mode=0;ci=32;invalid=0;model_id=-1;end
   62:begin h=8;w=16;ca=63;cb=0;fa=1;fb=1;k=3;mode=0;ci=63;invalid=0;model_id=-1;end
   63:begin h=8;w=16;ca=64;cb=0;fa=1;fb=1;k=3;mode=0;ci=64;invalid=0;model_id=-1;end
   64:begin h=8;w=12;ca=1;cb=0;fa=1;fb=1;k=1;mode=1;ci=1;invalid=0;model_id=-1;end
   65:begin h=8;w=12;ca=1;cb=0;fa=2;fb=1;k=1;mode=1;ci=1;invalid=0;model_id=-1;end
   66:begin h=8;w=12;ca=1;cb=0;fa=1;fb=2;k=1;mode=1;ci=1;invalid=0;model_id=-1;end
   67:begin h=8;w=12;ca=1;cb=0;fa=2;fb=2;k=1;mode=1;ci=1;invalid=0;model_id=-1;end
   68:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=5;invalid=0;model_id=-1;end
   69:begin h=8;w=12;ca=5;cb=0;fa=2;fb=1;k=1;mode=1;ci=5;invalid=0;model_id=-1;end
   70:begin h=8;w=12;ca=5;cb=0;fa=1;fb=2;k=1;mode=1;ci=5;invalid=0;model_id=-1;end
   71:begin h=8;w=12;ca=5;cb=0;fa=2;fb=2;k=1;mode=1;ci=5;invalid=0;model_id=-1;end
   72:begin h=8;w=12;ca=16;cb=0;fa=1;fb=1;k=1;mode=1;ci=16;invalid=0;model_id=-1;end
   73:begin h=8;w=12;ca=16;cb=0;fa=2;fb=1;k=1;mode=1;ci=16;invalid=0;model_id=-1;end
   74:begin h=8;w=12;ca=16;cb=0;fa=1;fb=2;k=1;mode=1;ci=16;invalid=0;model_id=-1;end
   75:begin h=8;w=12;ca=16;cb=0;fa=2;fb=2;k=1;mode=1;ci=16;invalid=0;model_id=-1;end
   76:begin h=8;w=12;ca=1;cb=1;fa=1;fb=1;k=1;mode=2;ci=2;invalid=0;model_id=-1;end
   77:begin h=8;w=12;ca=1;cb=1;fa=2;fb=1;k=1;mode=2;ci=2;invalid=0;model_id=-1;end
   78:begin h=8;w=12;ca=1;cb=1;fa=1;fb=2;k=1;mode=2;ci=2;invalid=0;model_id=-1;end
   79:begin h=8;w=12;ca=1;cb=1;fa=2;fb=2;k=1;mode=2;ci=2;invalid=0;model_id=-1;end
   80:begin h=8;w=12;ca=7;cb=9;fa=1;fb=1;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   81:begin h=8;w=12;ca=7;cb=9;fa=2;fb=1;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   82:begin h=8;w=12;ca=7;cb=9;fa=1;fb=2;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   83:begin h=8;w=12;ca=7;cb=9;fa=2;fb=2;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   84:begin h=8;w=12;ca=9;cb=7;fa=1;fb=1;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   85:begin h=8;w=12;ca=9;cb=7;fa=2;fb=1;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   86:begin h=8;w=12;ca=9;cb=7;fa=1;fb=2;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   87:begin h=8;w=12;ca=9;cb=7;fa=2;fb=2;k=1;mode=2;ci=16;invalid=0;model_id=-1;end
   88:begin h=8;w=12;ca=31;cb=33;fa=1;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   89:begin h=8;w=12;ca=31;cb=33;fa=2;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   90:begin h=8;w=12;ca=31;cb=33;fa=1;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   91:begin h=8;w=12;ca=31;cb=33;fa=2;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   92:begin h=8;w=12;ca=32;cb=32;fa=1;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   93:begin h=8;w=12;ca=32;cb=32;fa=2;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   94:begin h=8;w=12;ca=32;cb=32;fa=1;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   95:begin h=8;w=12;ca=32;cb=32;fa=2;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   96:begin h=8;w=12;ca=63;cb=1;fa=1;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   97:begin h=8;w=12;ca=63;cb=1;fa=2;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   98:begin h=8;w=12;ca=63;cb=1;fa=1;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   99:begin h=8;w=12;ca=63;cb=1;fa=2;fb=2;k=1;mode=2;ci=64;invalid=0;model_id=-1;end
   100:begin h=8;w=12;ca=1;cb=0;fa=1;fb=1;k=3;mode=1;ci=1;invalid=0;model_id=-1;end
   101:begin h=8;w=12;ca=1;cb=0;fa=2;fb=1;k=3;mode=1;ci=1;invalid=0;model_id=-1;end
   102:begin h=8;w=12;ca=1;cb=0;fa=1;fb=2;k=3;mode=1;ci=1;invalid=0;model_id=-1;end
   103:begin h=8;w=12;ca=1;cb=0;fa=2;fb=2;k=3;mode=1;ci=1;invalid=0;model_id=-1;end
   104:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=3;mode=1;ci=5;invalid=0;model_id=-1;end
   105:begin h=8;w=12;ca=5;cb=0;fa=2;fb=1;k=3;mode=1;ci=5;invalid=0;model_id=-1;end
   106:begin h=8;w=12;ca=5;cb=0;fa=1;fb=2;k=3;mode=1;ci=5;invalid=0;model_id=-1;end
   107:begin h=8;w=12;ca=5;cb=0;fa=2;fb=2;k=3;mode=1;ci=5;invalid=0;model_id=-1;end
   108:begin h=8;w=12;ca=16;cb=0;fa=1;fb=1;k=3;mode=1;ci=16;invalid=0;model_id=-1;end
   109:begin h=8;w=12;ca=16;cb=0;fa=2;fb=1;k=3;mode=1;ci=16;invalid=0;model_id=-1;end
   110:begin h=8;w=12;ca=16;cb=0;fa=1;fb=2;k=3;mode=1;ci=16;invalid=0;model_id=-1;end
   111:begin h=8;w=12;ca=16;cb=0;fa=2;fb=2;k=3;mode=1;ci=16;invalid=0;model_id=-1;end
   112:begin h=8;w=12;ca=1;cb=1;fa=1;fb=1;k=3;mode=2;ci=2;invalid=0;model_id=-1;end
   113:begin h=8;w=12;ca=1;cb=1;fa=2;fb=1;k=3;mode=2;ci=2;invalid=0;model_id=-1;end
   114:begin h=8;w=12;ca=1;cb=1;fa=1;fb=2;k=3;mode=2;ci=2;invalid=0;model_id=-1;end
   115:begin h=8;w=12;ca=1;cb=1;fa=2;fb=2;k=3;mode=2;ci=2;invalid=0;model_id=-1;end
   116:begin h=8;w=12;ca=7;cb=9;fa=1;fb=1;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   117:begin h=8;w=12;ca=7;cb=9;fa=2;fb=1;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   118:begin h=8;w=12;ca=7;cb=9;fa=1;fb=2;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   119:begin h=8;w=12;ca=7;cb=9;fa=2;fb=2;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   120:begin h=8;w=12;ca=9;cb=7;fa=1;fb=1;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   121:begin h=8;w=12;ca=9;cb=7;fa=2;fb=1;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   122:begin h=8;w=12;ca=9;cb=7;fa=1;fb=2;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   123:begin h=8;w=12;ca=9;cb=7;fa=2;fb=2;k=3;mode=2;ci=16;invalid=0;model_id=-1;end
   124:begin h=8;w=12;ca=31;cb=33;fa=1;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   125:begin h=8;w=12;ca=31;cb=33;fa=2;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   126:begin h=8;w=12;ca=31;cb=33;fa=1;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   127:begin h=8;w=12;ca=31;cb=33;fa=2;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   128:begin h=8;w=12;ca=32;cb=32;fa=1;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   129:begin h=8;w=12;ca=32;cb=32;fa=2;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   130:begin h=8;w=12;ca=32;cb=32;fa=1;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   131:begin h=8;w=12;ca=32;cb=32;fa=2;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   132:begin h=8;w=12;ca=63;cb=1;fa=1;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   133:begin h=8;w=12;ca=63;cb=1;fa=2;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   134:begin h=8;w=12;ca=63;cb=1;fa=1;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   135:begin h=8;w=12;ca=63;cb=1;fa=2;fb=2;k=3;mode=2;ci=64;invalid=0;model_id=-1;end
   136:begin h=128;w=128;ca=32;cb=32;fa=1;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=0;end
   137:begin h=128;w=128;ca=32;cb=32;fa=1;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=0;end
   138:begin h=256;w=256;ca=32;cb=32;fa=1;fb=1;k=1;mode=2;ci=64;invalid=0;model_id=1;end
   139:begin h=256;w=256;ca=32;cb=32;fa=1;fb=1;k=3;mode=2;ci=64;invalid=0;model_id=1;end
   140:begin h=512;w=512;ca=16;cb=16;fa=1;fb=1;k=1;mode=2;ci=32;invalid=0;model_id=2;end
   141:begin h=512;w=512;ca=16;cb=16;fa=1;fb=1;k=3;mode=2;ci=32;invalid=0;model_id=2;end
   142:begin h=0;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   143:begin h=513;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   144:begin h=8;w=0;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   145:begin h=8;w=513;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   146:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=2;mode=1;ci=5;invalid=1;model_id=-1;end
   147:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=3;ci=5;invalid=1;model_id=-1;end
   148:begin h=8;w=12;ca=0;cb=0;fa=1;fb=1;k=1;mode=1;ci=0;invalid=1;model_id=-1;end
   149:begin h=8;w=12;ca=65;cb=0;fa=1;fb=1;k=1;mode=1;ci=65;invalid=1;model_id=-1;end
   150:begin h=8;w=12;ca=5;cb=1;fa=1;fb=1;k=1;mode=1;ci=6;invalid=1;model_id=-1;end
   151:begin h=8;w=12;ca=5;cb=0;fa=0;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   152:begin h=8;w=12;ca=5;cb=0;fa=3;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   153:begin h=8;w=12;ca=5;cb=0;fa=1;fb=0;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   154:begin h=8;w=12;ca=5;cb=0;fa=1;fb=4;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   155:begin h=7;w=12;ca=5;cb=0;fa=2;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   156:begin h=8;w=11;ca=5;cb=0;fa=2;fb=1;k=1;mode=1;ci=5;invalid=1;model_id=-1;end
   157:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=2;ci=5;invalid=1;model_id=-1;end
   158:begin h=8;w=12;ca=5;cb=0;fa=1;fb=1;k=1;mode=1;ci=6;invalid=1;model_id=-1;end
   default:$fatal(1,"Unknown full fixture");
  endcase
  groups=(ci+7)/8;
  total_packets=invalid?0:(k==1?(h*w*groups*8+31)/32:(h+2)*(w+2)*groups);
  a_base=64'h00100000+(index%3==0?4032:(index%3==1?64:0));
  b_base=64'h02100000+(index%3==1?4064:(index%3==2?96:0));
  lut_base=64'h04100000+(index%3==2?4032:0);
  a_bytes=invalid?0:((h/fa*(w/fa)*((ca+7)/8)*8+31)/32)*32;
  b_bytes=invalid||!cb?0:((h/fb*(w/fb)*((cb+7)/8)*8+31)/32)*32;
  lut_bytes=invalid||!mode?0:(cb?512:256);
  word_index=0;done_seen=0;start_cycle=cycles;active=1;
  write_reg('h10,a_base[31:0]);write_reg('h14,0);write_reg('h20,h);write_reg('h28,w);write_reg('h30,ci);write_reg('h38,k);
  write_reg('h40,b_base[31:0]);write_reg('h44,0);write_reg('h50,lut_base[31:0]);write_reg('h54,0);
  write_reg('h60,mode);write_reg('h68,ca);write_reg('h70,cb);write_reg('h78,fa);write_reg('h80,fb);
 endtask
 task automatic finish_frame;
  logic[31:0] ctrl,status;
  // Registered AXIS can retain its last beat after the producer has returned.
  while(!done_seen||word_index<total_packets||read_busy||m_rvalid)@(negedge clk);
  read_reg('h00,ctrl);read_reg('h88,status);
  if(!ctrl[1]||status!==(invalid?32'd1:32'd0))$fatal(1,"READER done/status mismatch case=%0d",case_id);
  if(word_index!=total_packets||read_busy||m_rvalid)$fatal(1,"Incomplete frame or outstanding DDR case=%0d",case_id);
  repeat(20)@(negedge clk);
  if(s_valid||m_arvalid||read_busy||m_rvalid)$fatal(1,"Trailing frame contamination case=%0d",case_id);
  active=0;frames=frames+1;
  $display("READER_RTL_FRAME case=%0d invalid=%0d packets=%0d cycles=%0d",case_id,invalid,word_index,cycles-start_cycle);
 endtask
 task automatic frame(input integer index);
  prepare(index);write_reg(0,1);finish_frame();
 endtask
 task automatic reset_core;
  logic[31:0] ctrl;
  @(negedge clk);resetn=0;active=0;c_awvalid=0;c_wvalid=0;c_arvalid=0;c_bready=0;c_rready=0;
  repeat(8)@(negedge clk);
  resetn=1;force_ar=0;force_r=0;force_axis=0;
  repeat(12)@(negedge clk);read_reg(0,ctrl);
  if(!ctrl[2])$fatal(1,"Core not idle after actual reset");
 endtask
 task automatic abort_and_recover(input integer stage);
  prepare(126); // Non-aligned two-source join, output blocked or memory pending.
  case(stage)
   0:force_ar=1;
   1:force_r=1;
   2:force_axis=1;
   3:begin force_axis=1;force_r=0;end
  endcase
  write_reg(0,1);
  case(stage)
   0:while(!m_arvalid)@(negedge clk);
   1:while(!read_busy)@(negedge clk);
   2:while(!s_valid)@(negedge clk);
   3:begin while(!s_valid)@(negedge clk);repeat(64)@(negedge clk);end
  endcase
  repeat(7)@(negedge clk);reset_core();resets=resets+1;
  $display("READER_ACTUAL_RESET stage=%0d",stage);frame(64+stage);
 endtask
 initial begin
  resetn=0;c_awvalid=0;c_wvalid=0;c_awaddr=0;c_wdata=0;c_wstrb=0;c_arvalid=0;c_araddr=0;c_rready=0;c_bready=0;
  $readmemh("model_lut.hex",model_lut);
  reset_core();
  for(integer i=0;i<159;i=i+1)frame(i);
  frame(1);frame(74);$display("READER_TWO_TRAILING_CALLS_NO_RESET_EXACT");
  for(integer stage=0;stage<4;stage=stage+1)abort_and_recover(stage);
  if(frames!=165||resets!=4)$fatal(1,"Full159, trailing2 and recovery4 scope changed");
  if(STALLS&&(axis_stalls==0||ar_stalls==0))$fatal(1,"Random schedule did not exercise AXI/AXIS stalls");
  $display("PASS READER_FULL159_TRAILING2_RESET4_RECOVERY4 frames=%0d resets=%0d reads=%0d beats=%0d axis_stalls=%0d ar_stalls=%0d r_stalls=%0d",frames,resets,reads,beats,axis_stalls,ar_stalls,r_stalls);
  $finish;
 end
endmodule

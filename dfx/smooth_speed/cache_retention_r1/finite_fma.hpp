// Binary32 finite-input fused multiply/add, round-to-nearest ties-to-even.
// Independent integer datapath: 24x24 product, 50-bit aligned sum with jamming.
// Unlike the vendor FP core, subnormal inputs and gradual underflow survive.
#pragma once
#include <cstdint>
namespace finite_fma {
static uint8_t highest(uint64_t v) {
#pragma HLS inline
    uint8_t k=0;
    if(v>>32){v>>=32;k+=32;}
    if(v>>16){v>>=16;k+=16;}
    if(v>>8){v>>=8;k+=8;}
    if(v>>4){v>>=4;k+=4;}
    if(v>>2){v>>=2;k+=2;}
    if(v>>1)++k;
    return k;
}
static uint64_t jam(uint64_t v,unsigned shift) {
#pragma HLS inline
    if(!shift)return v;
    if(shift>=64)return v?1:0;
    return (v>>shift)|((v&((uint64_t(1)<<shift)-1))!=0);
}
static uint32_t round_even(uint64_t v,int shift) {
#pragma HLS inline
    if(shift<=0){
        unsigned left=unsigned(-shift);
        if(left>=32)return 0;
        return uint32_t(v)<<left;
    }
    if(shift>50)return 0;
    if(shift==50)return v>(uint64_t(1)<<49);
    uint32_t q=uint32_t(v>>shift)&0xffffffu;
    bool guard=(v>>(shift-1))&1;
    bool sticky=(v&((uint64_t(1)<<(shift-1))-1))!=0;
    return q+(guard&&(sticky||(q&1)));
}
static uint32_t bits(uint32_t a,uint32_t b,uint32_t c) {
#pragma HLS inline
    unsigned ae=(a>>23)&255,be=(b>>23)&255,ce=(c>>23)&255;
    // Medical callers reject nonfinite inputs; this leaf's supported domain is
    // exactly the finite IEEE values used by the independent frozen oracle.
    if(ae==255||be==255||ce==255)return 0x7fc00000u;
    uint32_t ma=(a&0x7fffffu)|(ae?0x800000u:0);
    uint32_t mb=(b&0x7fffffu)|(be?0x800000u:0);
    uint32_t mc=(c&0x7fffffu)|(ce?0x800000u:0);
    uint64_t p=uint64_t(ma)*mb;
    uint32_t ps=(a^b)&0x80000000u,cs=c&0x80000000u;
    if(!p)return mc?c:(ps&cs);
    int16_t pe=(ae?int(ae)-150:-149)+(be?int(be)-150:-149);
    int16_t ec=ce?int(ce)-150:-149;
    uint8_t kp=highest(p),kc=highest(mc);
    int16_t ep=pe+int(kp),et=mc?ec+int(kc):-2048;
    int16_t top=ep>et?ep:et,base=top-48;
    uint64_t ap=jam((p<<(48-kp))&((uint64_t(1)<<49)-1),unsigned(top-ep));
    // Normalize the 24-bit addend in 32 bits, then append 25 zero bits.
    // mc's highest bit is kc<=23, so no significant bit can be truncated.
    uint64_t c_normal=uint64_t(uint32_t(mc<<(23-kc)))<<25;
    uint64_t ac=jam(c_normal,unsigned(top-et));
    uint32_t sign;uint64_t value;
    if(ps==cs){sign=ps;value=ap+ac;}
    else if(ap>=ac){sign=ps;value=ap-ac;}
    else{sign=cs;value=ac-ap;}
    value&=(uint64_t(1)<<50)-1;
    if(!value)return 0; // Exact nonzero-term cancellation, RNE +0.
    uint8_t k=highest(value);top=base+int(k);
    // A single rounding datapath serves both normal and subnormal output.
    // Only its shift changes; RNE, tie and gradual-underflow rules are intact.
    bool subnormal=top<-126;
    int round_shift=subnormal?-149-base:int(k)-23;
    uint32_t significand=round_even(value,round_shift);
    if(subnormal)return sign|significand;
    if(significand==(uint64_t(1)<<24)){significand>>=1;++top;}
    if(top>127)return sign|0x7f800000u;
    return sign|(uint32_t(top+127)<<23)|(uint32_t(significand)&0x7fffffu);
}
}

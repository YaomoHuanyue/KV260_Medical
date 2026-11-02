#include "types.hpp"

// Eight packed rows use four physical arithmetic lanes in two batches.
constexpr unsigned NAV_EDT_COMPUTE_LANES=4;

// First integer coordinate where q is strictly better than p. q>p and weight>0
// imply 0<b<2^43. Build floor(a/b) one bit at a time using additions: no divider
// or repeated wide multiply, and identical strict integer cost ordering.
static unsigned switch_at(int64_t a,int64_t b,unsigned length){
#pragma HLS INLINE
    if(a<0)return 0;
    uint64_t scaled=uint64_t(b)<<10,cost=0;
    unsigned coordinate=0,step=1024;
    for(unsigned bit=0;bit<11;++bit){
#pragma HLS PIPELINE II=1
        unsigned candidate=coordinate+step;
        uint64_t trial=cost+scaled;
        if(candidate<length&&trial<=uint64_t(a)){coordinate=candidate;cost=trial;}
        step>>=1;scaled>>=1;
    }
    return coordinate+1<length?coordinate+1:length;
}

static void dt_line(const uint64_t f[NAV_MAX_LINE*2],uint64_t d[NAV_MAX_LINE*2],
                    unsigned length,uint32_t weight,unsigned mode,unsigned base){
#pragma HLS INLINE off
    if(mode==0){
        unsigned run=NAV_MAX_LINE+1;
        for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
            run=f[q+base]==0?0:run+1;
            d[q+base]=run>NAV_MAX_LINE?NAV_INF:uint64_t(weight)*run*run;
        }
        run=NAV_MAX_LINE+1;
        for(int q=int(length)-1;q>=0;--q){
#pragma HLS PIPELINE II=1
            run=f[q+base]==0?0:run+1;
            uint64_t value=run>NAV_MAX_LINE?NAV_INF:uint64_t(weight)*run*run;
            if(value<d[q+base])d[q+base]=value;
        }
        return;
    }
    uint16_t candidates[NAV_MAX_LINE],starts[NAV_MAX_LINE];
#pragma HLS BIND_STORAGE variable=candidates type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=starts type=ram_2p impl=bram
    int last=-1;
    for(unsigned q=0;q<length;++q){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
        if(f[q+base]==NAV_INF)continue;
        unsigned s=0;
        while(last>=0){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
            unsigned p=candidates[last];
            int64_t a=int64_t(f[q+base])-int64_t(f[p+base])+int64_t(weight)*(int64_t(q)*q-int64_t(p)*p);
            int64_t b=2*int64_t(weight)*(q-p);
            s=switch_at(a,b,length);
            if(s>starts[last])break;
            --last;
        }
        if(last<0)s=0;
        if(s<length){++last;candidates[last]=q;starts[last]=s;}
    }
    if(last<0){
        for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
            d[q+base]=NAV_INF;
        }
        return;
    }
    unsigned k=0;
    for(unsigned q=0;q<length;++q){
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
        while(k<unsigned(last)&&starts[k+1]<=q)++k;
        unsigned p=candidates[k];int64_t difference=int64_t(q)-p;
        d[q+base]=f[p+base]+uint64_t(weight)*uint64_t(difference*difference);
    }
}

static void lanes(const uint64_t input[NAV_EDT_COMPUTE_LANES][NAV_MAX_LINE*2],uint64_t output[NAV_EDT_COMPUTE_LANES][NAV_MAX_LINE*2],
                  unsigned length,uint32_t weight,unsigned mode,unsigned base){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    for(unsigned i=0;i<NAV_EDT_COMPUTE_LANES;++i){
#pragma HLS UNROLL
        dt_line(input[i],output[i],length,weight,mode,base);
    }
}

extern "C" void nav_edt(Stream<Packet>& input,Stream<Packet>& output,uint32_t length,uint32_t groups,
                        uint32_t weight,uint32_t mode,uint32_t& status){
#pragma HLS INTERFACE axis port=input register_mode=both
#pragma HLS INTERFACE axis port=output register_mode=both
#pragma HLS INTERFACE s_axilite port=length bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=groups bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=weight bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=mode bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=return bundle=control
    uint64_t f[NAV_EDT_COMPUTE_LANES][NAV_MAX_LINE*2],d[NAV_EDT_COMPUTE_LANES][NAV_MAX_LINE*2];
#pragma HLS ARRAY_PARTITION variable=f complete dim=1
#pragma HLS ARRAY_PARTITION variable=d complete dim=1
#pragma HLS BIND_STORAGE variable=f type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=d type=ram_2p impl=bram
    uint32_t count=length*groups,errors=0;
    bool bad=length<1||length>NAV_MAX_LINE||groups>NAV_MAX_GROUPS||weight==0||mode>1;
    if(bad){
        // The host validates bounds before starting movers. For malformed jobs
        // with a bounded count, drain and preserve one output per input packet.
        if(count<=NAV_MAX_LINE*NAV_MAX_GROUPS)for(uint32_t i=0;i<count;++i){Packet p=input.read();output.write(packet(p.data,i,count));}
        status=1;return;
    }
    for(uint32_t group=0;group<groups;++group){
#pragma HLS LOOP_TRIPCOUNT min=1 max=131072
        for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
            unsigned id=group*length+q;Packet p=input.read();
            if(p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0)||bool(p.last)!=(id+1==count)||bool(p.user)!=(id==0))errors|=2;
            for(unsigned l=0;l<NAV_LANES;++l){
#pragma HLS UNROLL
                f[l%(NAV_EDT_COMPUTE_LANES)][q+(l/(NAV_EDT_COMPUTE_LANES))*NAV_MAX_LINE]=lane(p.data,l);
            }
        }
        for(unsigned half=0;half<2;++half)lanes(f,d,length,weight,mode,half*NAV_MAX_LINE);
        for(unsigned q=0;q<length;++q){
#pragma HLS PIPELINE II=1
            Word word{};
            for(unsigned l=0;l<NAV_LANES;++l){
#pragma HLS UNROLL
                lane(word,l,d[l%(NAV_EDT_COMPUTE_LANES)][q+(l/(NAV_EDT_COMPUTE_LANES))*NAV_MAX_LINE]);
            }
            output.write(packet(word,group*length+q,count));
        }
    }
    status=errors;
}

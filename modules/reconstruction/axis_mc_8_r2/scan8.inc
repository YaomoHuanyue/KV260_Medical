// Eight adjacent X voxels per iteration. A row tail never crosses geometry
// rows; the 576-bit input reservoir independently handles 64-byte AXIS beats.
static void scan(McAxisStream& input,unsigned nx,unsigned ny,unsigned nz,
                 bool count_only,uint32_t input_words,Stream<Cell>& cells) {
#pragma HLS inline off
    constexpr unsigned HALF=mc_axis::MAX_DIM/2;
    static PlaneWord planes[2][2][2][HALF*HALF/64];
#pragma HLS array_partition variable=planes complete dim=1
#pragma HLS array_partition variable=planes complete dim=2
#pragma HLS array_partition variable=planes complete dim=3
#pragma HLS bind_storage variable=planes type=ram_2p impl=bram
    PlaneWord recent[2][2][2];
#pragma HLS array_partition variable=recent complete dim=0
    for(unsigned bz=0;bz<2;++bz)for(unsigned by=0;by<2;++by)for(unsigned bx=0;bx<2;++bx) {
#pragma HLS unroll
        recent[bz][by][bx]=0;
    }
    const uint32_t voxels=nx*ny*nz,needed=(voxels+63)/64;
    uint32_t errors=input_words!=needed?uint32_t(mc_axis::FRAME_LENGTH):0;
    uint32_t total=0,read_words=0;
    unsigned available=0;
#ifdef MC_AXIS_NATIVE
    uint8_t reservoir[72]={};
#else
    ap_uint<576> reservoir=0;
#endif
    for(unsigned z=0;z<nz;++z)for(unsigned y=0;y<ny;++y) {
        scan_groups:for(unsigned x=0;x<nx;x+=8) {
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            const unsigned n=nx-x<8?nx-x:8;
            if(available<n) {
                McAxisWord word=empty_word();
                if(read_words<input_words) {
                    word=input.read();errors|=framing(word,read_words,input_words);++read_words;
                }
#ifdef MC_AXIS_NATIVE
                for(unsigned b=0;b<64;++b)reservoir[available+b]=word.data[b];
#else
                reservoir|=ap_uint<576>(word.data)<<(available*8);
#endif
                available+=64;
            }
            uint8_t values[8]={};
#pragma HLS array_partition variable=values complete dim=1
            for(unsigned lane=0;lane<8;++lane) {
#pragma HLS unroll
                if(lane<n) {
#ifdef MC_AXIS_NATIVE
                    values[lane]=reservoir[lane];
#else
                    values[lane]=reservoir.range(lane*8+7,lane*8);
#endif
                    if(values[lane]>1)errors|=mc_axis::NON_BINARY;
                }
            }
#ifdef MC_AXIS_NATIVE
            for(unsigned b=0;b<available-n;++b)reservoir[b]=reservoir[b+n];
            for(unsigned b=available-n;b<72;++b)reservoir[b]=0;
#else
            reservoir>>=n*8;
#endif
            available-=n;
            PlaneWord right[2][2][2],left[2][2][2];
#pragma HLS array_partition variable=right complete dim=0
#pragma HLS array_partition variable=left complete dim=0
            for(unsigned bz=0;bz<2;++bz)for(unsigned by=0;by<2;++by)for(unsigned bx=0;bx<2;++bx) {
#pragma HLS unroll
                // These lanes always start at x%8==0. Each parity bank writes
                // four contiguous bits, with explicit bypass for the new word.
                const unsigned yy=(by==(y&1))?y:(y?y-1:0);
                const unsigned address=((yy/2)*HALF+x/2)/64;
                const unsigned prior=((yy/2)*HALF+(x?(x-1)/2:0))/64;
                if(bz==(z&1)&&by==(y&1)) {
                    const unsigned shift=(x/2)&63;
                    PlaneWord bits=0;
                    for(unsigned k=0;k<4;++k) {
#pragma HLS unroll
                        bits|=PlaneWord(values[k*2+bx]&1)<<k;
                    }
                    const PlaneWord updated=(shift==0?PlaneWord(0):recent[bz][by][bx])|(bits<<shift);
                    planes[bz][by][bx][address]=updated;
                    recent[bz][by][bx]=updated;right[bz][by][bx]=updated;
                }else right[bz][by][bx]=planes[bz][by][bx][address];
                left[bz][by][bx]=(prior==address)?right[bz][by][bx]:planes[bz][by][bx][prior];
            }
            Cell group{};group.x=uint16_t(x);group.y=uint16_t(y?y-1:0);group.z=uint16_t(z?z-1:0);
            unsigned counts[8]={};
#pragma HLS array_partition variable=counts complete dim=1
            for(unsigned lane=0;lane<8;++lane) {
#pragma HLS unroll
                const unsigned xx=x+lane;
                if(lane<n&&xx>0&&y>0&&z>0) {
                    unsigned code=0;
                    for(unsigned bz=0;bz<2;++bz)for(unsigned by=0;by<2;++by)for(unsigned bx=0;bx<2;++bx) {
#pragma HLS unroll
                        const unsigned dx=bx==(xx&1),dy=by==(y&1),dz=bz==(z&1);
                        const unsigned corner=xx-1+dx;
                        const PlaneWord word=corner<x?left[bz][by][bx]:right[bz][by][bx];
                        const unsigned bit=unsigned((word>>((corner/2)&63))&1);
                        code|=bit<<(dz*4+dy*2+dx);
                    }
                    group.code[lane]=uint8_t(code);counts[lane]=MC_COUNTS[code];
                    if(code!=0&&code!=255)group.active|=uint8_t(1u<<lane);
                }
            }
            total+=((counts[0]+counts[1])+(counts[2]+counts[3]))+
                   ((counts[4]+counts[5])+(counts[6]+counts[7]));
            if(!count_only&&group.active)cells.write(group);
        }
    }
    drain_extra:while(read_words<input_words) {
#pragma HLS pipeline II=1
        McAxisWord word=input.read();errors|=framing(word,read_words,input_words);++read_words;
    }
    Cell end{};end.last=true;end.total=total;end.errors=errors;cells.write(end);
}

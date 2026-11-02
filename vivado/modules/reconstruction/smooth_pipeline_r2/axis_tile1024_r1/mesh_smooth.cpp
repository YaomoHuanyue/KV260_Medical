#include "axis_kernel.hpp"
#include "medical_fma.hpp"
#include <cmath>
// Only cached scheduler state has bounded hardware widths.
// Native code retains the exact-value uint16 ABI; typed Csim and RTL
// must separately verify the actual ap_uint<9>/<13> implementation.
#ifdef SMOOTH_NATIVE
using CachedRowOwner=uint16_t;using CachedEdgeOffset=uint16_t;
#else
using CachedRowOwner=ap_uint<11>;using CachedEdgeOffset=ap_uint<15>;
#endif
#ifdef SMOOTH_NATIVE
#include <queue>
namespace hls {template<class T> struct stream {std::queue<T> q;void write(T v){q.push(v);} T read(){T v=q.front();q.pop();return v;}};}
#else
#include <hls_stream.h>
#endif

static SmoothPoint add(SmoothPoint a,SmoothPoint b){return {a.x+b.x,a.y+b.y,a.z+b.z,0};}
static SmoothPoint sub(SmoothPoint a,SmoothPoint b){return {a.x-b.x,a.y-b.y,a.z-b.z,0};}
static SmoothPoint scale(SmoothPoint a,float s){return {a.x*s,a.y*s,a.z*s,0};}
static float dot(SmoothPoint a,SmoothPoint b){return (a.x*b.x+a.y*b.y)+a.z*b.z;}
static SmoothPoint cross(SmoothPoint a,SmoothPoint b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x,0};}
static float norm(SmoothPoint a){return std::sqrt(dot(a,a));}
static bool finite(SmoothPoint a){return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);}
static uint32_t bits(float a){union {float f;uint32_t u;} b;b.f=a;return b.u;}



static SmoothPoint unpack_point(PointWord word){
#pragma HLS inline
#ifdef SMOOTH_NATIVE
    return word;
#else
    union {uint32_t u;float f;} a,b,c,d;
    a.u=word.range(31,0);b.u=word.range(63,32);c.u=word.range(95,64);d.u=word.range(127,96);
    return {a.f,b.f,c.f,d.f};
#endif
}
static SmoothPoint read_point(const PointWord* memory,uint32_t index){
#pragma HLS inline
    return unpack_point(memory[index]);
}
static PointWord pack_point(SmoothPoint point){
#pragma HLS inline
#ifdef SMOOTH_NATIVE
    return point;
#else
    union {uint32_t u;float f;} a,b,c,d;a.f=point.x;b.f=point.y;c.f=point.z;d.f=point.pad;
    PointWord word;word.range(31,0)=a.u;word.range(63,32)=b.u;word.range(95,64)=c.u;word.range(127,96)=d.u;return word;
#endif
}
static SmoothFace read_face(const FaceWord* memory,uint32_t index){
#pragma HLS inline
#ifdef SMOOTH_NATIVE
    return memory[index];
#else
    FaceWord word=memory[index];return {uint32_t(word.range(31,0)),uint32_t(word.range(63,32)),uint32_t(word.range(95,64)),uint32_t(word.range(127,96))};
#endif
}

// Requests are <=64 words and split at bank-relative 4 KiB offsets.
// Absolute physical 4 KiB boundaries are split by the AXI adapter; RTL verification is required.
// Every word is still consumed; zero-length intervals issue no request.
static uint32_t bounded_burst_count(uint32_t base,uint32_t remaining){
#pragma HLS inline
    uint32_t n=remaining<64?remaining:64,room=256-(base&255);
    return n<room?n:room;
}
#ifndef SMOOTH_NATIVE
static SmoothPoint read_point(PointMemory memory,uint32_t index){
#pragma HLS inline
    memory.read_request(index,1);return unpack_point(memory.read());
}
#endif
static void read_current_words(PointMemory current,hls::stream<PointWord>& words,uint32_t base,uint32_t count){
#pragma HLS inline off
    // At most four requests are in flight on this sole named port.
    // Each request remains <=64 words and bank-relative4KiB bounded.
    // Drain the exact consecutive requested range before reusing any port.
    current_read_groups:for(uint32_t offset=0;offset<count;){
        uint32_t batch_base=offset,batch_words=0;
        current_issue_requests:for(unsigned request=0;request<4 && offset<count;++request){
#pragma HLS loop_tripcount min=1 max=4
            uint32_t length=bounded_burst_count(base+offset,count-offset);
            SM_READ_BEGIN(current,base+offset,length);
            offset+=length;batch_words+=length;
        }
        current_read_words:for(uint32_t k=0;k<batch_words;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=256
            uint32_t j=base+batch_base+k;
            words.write(SM_READ_WORD(current,j));
        }
    }
}
static void read_half_words(PointMemory half,hls::stream<PointWord>& words,uint32_t base,uint32_t count){
#pragma HLS inline off
    // At most four requests are in flight on this sole named port.
    // Each request remains <=64 words and bank-relative4KiB bounded.
    // Drain the exact consecutive requested range before reusing any port.
    half_read_groups:for(uint32_t offset=0;offset<count;){
        uint32_t batch_base=offset,batch_words=0;
        half_issue_requests:for(unsigned request=0;request<4 && offset<count;++request){
#pragma HLS loop_tripcount min=1 max=4
            uint32_t length=bounded_burst_count(base+offset,count-offset);
            SM_READ_BEGIN(half,base+offset,length);
            offset+=length;batch_words+=length;
        }
        half_read_words:for(uint32_t k=0;k<batch_words;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=256
            uint32_t j=base+batch_base+k;
            words.write(SM_READ_WORD(half,j));
        }
    }
}
static void read_candidate_words(PointMemory candidate,hls::stream<PointWord>& words,uint32_t base,uint32_t count){
#pragma HLS inline off
    // At most four requests are in flight on this sole named port.
    // Each request remains <=64 words and bank-relative4KiB bounded.
    // Drain the exact consecutive requested range before reusing any port.
    candidate_read_groups:for(uint32_t offset=0;offset<count;){
        uint32_t batch_base=offset,batch_words=0;
        candidate_issue_requests:for(unsigned request=0;request<4 && offset<count;++request){
#pragma HLS loop_tripcount min=1 max=4
            uint32_t length=bounded_burst_count(base+offset,count-offset);
            SM_READ_BEGIN(candidate,base+offset,length);
            offset+=length;batch_words+=length;
        }
        candidate_read_words:for(uint32_t k=0;k<batch_words;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=256
            uint32_t j=base+batch_base+k;
            words.write(SM_READ_WORD(candidate,j));
        }
    }
}
static void read_lap_words(PointMemory lap,hls::stream<PointWord>& words,uint32_t base,uint32_t count){
#pragma HLS inline off
    // At most four requests are in flight on this sole named port.
    // Each request remains <=64 words and bank-relative4KiB bounded.
    // Drain the exact consecutive requested range before reusing any port.
    lap_read_groups:for(uint32_t offset=0;offset<count;){
        uint32_t batch_base=offset,batch_words=0;
        lap_issue_requests:for(unsigned request=0;request<4 && offset<count;++request){
#pragma HLS loop_tripcount min=1 max=4
            uint32_t length=bounded_burst_count(base+offset,count-offset);
            SM_READ_BEGIN(lap,base+offset,length);
            offset+=length;batch_words+=length;
        }
        lap_read_words:for(uint32_t k=0;k<batch_words;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=256
            uint32_t j=base+batch_base+k;
            words.write(SM_READ_WORD(lap,j));
        }
    }
}
static void read_next_lap_words(PointMemory next_lap,hls::stream<PointWord>& words,uint32_t base,uint32_t count){
#pragma HLS inline off
    // At most four requests are in flight on this sole named port.
    // Each request remains <=64 words and bank-relative4KiB bounded.
    // Drain the exact consecutive requested range before reusing any port.
    next_lap_read_groups:for(uint32_t offset=0;offset<count;){
        uint32_t batch_base=offset,batch_words=0;
        next_lap_issue_requests:for(unsigned request=0;request<4 && offset<count;++request){
#pragma HLS loop_tripcount min=1 max=4
            uint32_t length=bounded_burst_count(base+offset,count-offset);
            SM_READ_BEGIN(next_lap,base+offset,length);
            offset+=length;batch_words+=length;
        }
        next_lap_read_words:for(uint32_t k=0;k<batch_words;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=256
            uint32_t j=base+batch_base+k;
            words.write(SM_READ_WORD(next_lap,j));
        }
    }
}
static void unpack_local_words(hls::stream<PointWord>& words,SmoothPoint* local,uint32_t count){
#pragma HLS inline off
#pragma HLS aggregate variable=local compact=bit
    local_unpack:for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
        local[j]=unpack_point(words.read());
    }
}
static void unpack_four_cache(hls::stream<PointWord>& words,SmoothPoint points[4][16384],uint32_t begin,uint32_t count){
#pragma HLS inline off
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    four_cache_unpack:for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
        SmoothPoint p=unpack_point(words.read());
        for(unsigned copy=0;copy<4;++copy){
#pragma HLS unroll
            points[copy][(begin+j)&16383]=p;
        }
    }
}
static void load_local_current(PointMemory current,SmoothPoint* local,uint32_t base,uint32_t count){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_current_words(current,words,base,count);
    unpack_local_words(words,local,count);
}
static void load_local_half(PointMemory half,SmoothPoint* local,uint32_t base,uint32_t count){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_half_words(half,words,base,count);
    unpack_local_words(words,local,count);
}
static void load_local_candidate(PointMemory candidate,SmoothPoint* local,uint32_t base,uint32_t count){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_candidate_words(candidate,words,base,count);
    unpack_local_words(words,local,count);
}
static void load_local_lap(PointMemory lap,SmoothPoint* local,uint32_t base,uint32_t count){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_lap_words(lap,words,base,count);
    unpack_local_words(words,local,count);
}
static void load_local_next_lap(PointMemory next_lap,SmoothPoint* local,uint32_t base,uint32_t count){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_next_lap_words(next_lap,words,base,count);
    unpack_local_words(words,local,count);
}
static void load_cache_current(PointMemory current,SmoothPoint points[4][16384],uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS dataflow
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_current_words(current,words,begin,end-begin);
    unpack_four_cache(words,points,begin,end-begin);
}
static void load_cache_half(PointMemory half,SmoothPoint points[4][16384],uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS dataflow
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_half_words(half,words,begin,end-begin);
    unpack_four_cache(words,points,begin,end-begin);
}
static void load_cache_candidate(PointMemory candidate,SmoothPoint points[4][16384],uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS dataflow
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_candidate_words(candidate,words,begin,end-begin);
    unpack_four_cache(words,points,begin,end-begin);
}

// Select the loop, never a merged DDR pointer. Every call keeps the same
// named banks in the same argument positions and shares these four URAM copies.
static void refill_selected_tile(SmoothPoint points[4][16384],
    PointMemory current,PointMemory half,PointMemory candidate,
    uint32_t source_bank,uint32_t begin,uint32_t end){
#pragma HLS inline off
    if(source_bank==0)load_cache_current(current,points,begin,end);
    else if(source_bank==1)load_cache_half(half,points,begin,end);
    else load_cache_candidate(candidate,points,begin,end);
}
// Arbitrary-numbering/high-degree fallback remains a random-access path.
static SmoothPoint read_selected_point(PointMemory current,
    PointMemory half,PointMemory candidate,uint32_t bank,uint32_t index){
#pragma HLS inline
    if(bank==0)return read_point(current,index);
    if(bank==1)return read_point(half,index);
    return read_point(candidate,index);
}

#include "cache_window.hpp"
#include "apply_stream.inc"

// Four exact FMA lanes replenish completed contexts independently.
// Full HLS, RTL, resource, route and strongest PS4 board gates remain required.
// Exact CSR neighbor order and all mean/output/candidate bank selectors stay unchanged.
// Every row retains its CSR order with one correctly rounded FP32 fused multiply/add per neighbor.
// Four dual-port copies are shared with orientation checks at the top level.
static void average_stage(SmoothPoint points[4][16384],PointMemory current,PointMemory half,
    PointMemory candidate,PointMemory lap,PointMemory next_lap,uint32_t source_bank,uint32_t output_bank,
    const PointWord* original,const uint32_t* rows,GraphTask& edges,const uint32_t* frozen,
    uint32_t nv,uint32_t nnz,int expand,float coefficient,float limit,double& roughness){
#pragma HLS inline off
#pragma HLS allocation instances=accumulate_neighbor limit=2 function
    GraphPass pass(edges);
    const uint32_t TILE=1024,EDGE_CAP=16384,WINDOW=16384,LANES=4,SLOTS=8,GROUP=LANES*SLOTS;
    SmoothPoint initial[TILE];SmoothEdge graph[(LANES+1)/2][EDGE_CAP];
    uint32_t offsets[TILE+1],fixed[TILE];SmoothPoint mean[TILE];
    double totals[16]={0};
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS array_partition variable=graph complete dim=1
#pragma HLS array_partition variable=graph cyclic factor=4 dim=2
#pragma HLS array_partition variable=totals complete
#pragma HLS array_partition variable=offsets cyclic factor=4 dim=1
#pragma HLS bind_storage variable=offsets type=ram_t2p impl=bram
#pragma HLS aggregate variable=points compact=bit
#pragma HLS aggregate variable=initial compact=bit
#pragma HLS aggregate variable=mean compact=bit
#pragma HLS aggregate variable=graph compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
#pragma HLS bind_storage variable=graph type=ram_2p impl=uram
#pragma HLS array_partition variable=mean cyclic factor=4
#pragma HLS bind_storage variable=mean type=ram_2p impl=bram
    // Coordinates do not change during one average pass. A circular window
    // retains overlap between adjacent tiles; each newly needed index is loaded
    // into index modulo WINDOW. Only indices within the validated interval are
    // used, so no two required coordinates alias in this power-of-two cache.
    bool cache_valid=false;uint32_t cache_lo=0,cache_hi=0;
    const bool resident=nv<=WINDOW;
    if(resident){
        refill_selected_tile(points,current,half,candidate,source_bank,0,nv);
        cache_valid=true;cache_lo=0;cache_hi=nv-1;
    }
    for(uint32_t base=0;base<nv;base+=TILE){
#pragma HLS loop_tripcount min=1 max=977
        uint32_t count=nv-base<TILE?nv-base:TILE;
        uint32_t first=rows[base],lo=base,hi=base+count-1;
        for(uint32_t j=0;j<=count;++j){
#pragma HLS pipeline II=1
            offsets[j]=rows[base+j]-first;
        }
        if(expand){
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
                initial[j]=read_point(original,base+j);
            }
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
                fixed[j]=frozen[base+j];
            }
        }
        uint32_t edge_count=offsets[count];bool graph_cached=edge_count<=EDGE_CAP;
        if(graph_cached){
            load_graph:for(uint32_t e=0;e<edge_count;){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=0 max=4097
                smooth_graph_axis::Quarter packet=pass.next_up_to4(first+e,edge_count-e);
                load_four_edges:for(unsigned lane=0;lane<4;++lane){
#pragma HLS unroll
                    if(lane<packet.count){
                        uint64_t packed=packet.edges[lane];union{uint32_t u;float f;}weight;
                        weight.u=uint32_t(packed>>32);SmoothEdge item{uint32_t(packed),weight.f};
                        for(unsigned copy=0;copy<(LANES+1)/2;++copy){
#pragma HLS unroll
                            graph[copy][e+lane]=item;
                        }
                        if(item.index<lo)lo=item.index;
                        if(item.index>hi)hi=item.index;
                    }
                }
                e+=packet.count;
            }
        }
        bool cached=graph_cached && hi-lo<WINDOW;
        if(cached){
            if(!resident){
                uint32_t begin1=lo,end1=hi+1,begin2=0,end2=0;
                if(cache_valid && lo<=cache_hi && hi>=cache_lo){
                    end1=lo<cache_lo?cache_lo:lo;
                    begin2=hi>cache_hi?cache_hi+1:hi+1;end2=hi+1;
                }
                refill_selected_tile(points,current,half,candidate,source_bank,begin1,end1);
                refill_selected_tile(points,current,half,candidate,source_bank,begin2,end2);
                retain_cache_window(lo,hi,WINDOW,cache_valid,cache_lo,cache_hi);
            }
            // Each lane owns rows modulo four, preserving four-bank
            // mean writes. A completed context takes the next row in that lane.
            // Every row's FMA neighbors retain their original CSR order.
            SmoothPoint sums[LANES][SLOTS];
            static_assert(TILE<=65535 && EDGE_CAP<=65535,"Cached scheduler metadata must fit uint16_t");
            static_assert(TILE<=2047 && EDGE_CAP<=32767,"Cached metadata must fit its exact hardware widths");
            CachedRowOwner owner[LANES][SLOTS];
            CachedEdgeOffset start[LANES][SLOTS],degree[LANES][SLOTS],cursor[LANES][SLOTS];
            uint32_t next_row[LANES];
#pragma HLS array_partition variable=sums complete
#pragma HLS array_partition variable=owner complete dim=0
#pragma HLS array_partition variable=start complete
#pragma HLS array_partition variable=degree complete dim=0
#pragma HLS array_partition variable=cursor complete dim=0
#pragma HLS array_partition variable=next_row complete
#pragma HLS aggregate variable=sums compact=bit
            row_setup:for(unsigned slot=0;slot<SLOTS;++slot){
#pragma HLS pipeline II=1
                for(unsigned lane=0;lane<LANES;++lane){
#pragma HLS unroll
                    uint32_t row=slot*LANES+lane;
                    owner[lane][slot]=row<count?row:count;
                    start[lane][slot]=row<count?offsets[row]:0;
                    degree[lane][slot]=row<count?offsets[row+1]-offsets[row]:0;
                    cursor[lane][slot]=0;sums[lane][slot]={0,0,0,0};
                }
            }
            for(unsigned lane=0;lane<LANES;++lane){
#pragma HLS unroll
                next_row[lane]=GROUP+lane;
            }
            static_assert((TILE+LANES-1)/LANES<=65535,"Lane completion count must fit uint16_t");
            uint16_t completed[LANES]={0};uint32_t step=0;
#pragma HLS array_partition variable=completed complete
            row_rounds:while(completed[0]+completed[1]+completed[2]+completed[3]<count){
#pragma HLS pipeline II=2
#pragma HLS loop_tripcount min=1 max=65536
#pragma HLS dependence variable=sums inter true distance=8
#pragma HLS dependence variable=owner inter true distance=8
#pragma HLS dependence variable=start inter true distance=8
#pragma HLS dependence variable=degree inter true distance=8
#pragma HLS dependence variable=cursor inter true distance=8
                unsigned slot=step&(SLOTS-1);
                for(unsigned lane=0;lane<LANES;++lane){
#pragma HLS unroll
                    uint16_t row=owner[lane][slot];
                    if(row<count){
                        uint16_t k=cursor[lane][slot],n=degree[lane][slot];
                        SmoothPoint sum=sums[lane][slot];
                        if(k<n){
                            SmoothEdge item=graph[lane/2][start[lane][slot]+k];
                            SmoothPoint p=points[lane/2][item.index&(WINDOW-1)];
                            sum=accumulate_neighbor(sum,p,item.weight);++k;
                        }
                        if(k==n){
                            mean[(row/LANES)*LANES+lane]=sum;++completed[lane];
                            uint32_t next=next_row[lane];
                            owner[lane][slot]=next<count?next:count;
                            start[lane][slot]=next<count?offsets[(next/LANES)*LANES+lane]:0;
                            degree[lane][slot]=next<count?offsets[(next/LANES)*LANES+lane+1]-offsets[(next/LANES)*LANES+lane]:0;
                            next_row[lane]=next+LANES;
                            cursor[lane][slot]=0;sums[lane][slot]={0,0,0,0};
                        } else {
                            cursor[lane][slot]=k;sums[lane][slot]=sum;
                        }
                    }
                }
                ++step;
            }
        } else {
            // Preserve correctness for arbitrary numbering/high-degree graphs.
            // No topology changes, skipped edges, or artificial degree limits.
            for(uint32_t row=0;row<count;++row){
                SmoothPoint sum={0,0,0,0};
                fallback_neighbors:for(uint32_t e=offsets[row];e<offsets[row+1];++e){
#pragma HLS pipeline II=7
                    SmoothEdge item=graph_cached?graph[0][e]:pass.next(first+e);
                    sum=accumulate_neighbor(sum,read_selected_point(current,half,candidate,source_bank,item.index),item.weight);
                }
                mean[row]=sum;
            }
        }

        apply_store_tile(current,half,candidate,lap,next_lap,source_bank,output_bank,points[0],mean,initial,fixed,
                         base,count,cached,expand,coefficient,limit,totals);
    }
    // FP64 reduction order changes here only; coordinate arithmetic stays FP32.
    // Exact own-CT coordinates/decisions and bounded roughness error are gates.
    double total=0;for(unsigned j=0;j<16;++j)total+=totals[j];roughness=total/double(nv);
    pass.finish();
}
// Every call passes the identical physical banks in the same argument
// positions. Pass a scalar selector to fixed named read/write loops inside
// the shared stage; do not merge their AXI base pointers.
static void average_selected(SmoothPoint points[4][16384],PointMemory current,
    PointMemory half,PointMemory candidate,PointMemory lap,PointMemory next_lap,
    const PointWord* original,const uint32_t* rows,GraphTask& edges,
    const uint32_t* frozen,uint32_t source_bank,uint32_t output_bank,
    uint32_t nv,uint32_t nnz,int expand,float coefficient,float limit,double& roughness){
#pragma HLS inline off
    average_stage(points,current,half,candidate,lap,next_lap,source_bank,output_bank,
                  original,rows,edges,frozen,nv,nnz,expand,coefficient,limit,roughness);
}

static void unpack_orientation_words(hls::stream<PointWord>& words,SmoothPoint points[4][16384],uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    orientation_unpack:for(uint32_t j=begin;j<end;++j){
#pragma HLS pipeline II=1
        SmoothPoint p=unpack_point(words.read());points[2][j&16383]=p;points[3][j&16383]=p;
    }
}
static void load_orientation_current(SmoothPoint points[4][16384],PointMemory current,uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS dataflow
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_current_words(current,words,begin,end-begin);
    unpack_orientation_words(words,points,begin,end);
}
static void load_orientation_candidate(SmoothPoint points[4][16384],PointMemory candidate,uint32_t begin,uint32_t end){
#pragma HLS inline off
#pragma HLS dataflow
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    hls::stream<PointWord> words;
#pragma HLS stream variable=words depth=64
#pragma HLS bind_storage variable=words type=fifo impl=bram
    read_candidate_words(candidate,words,begin,end-begin);
    unpack_orientation_words(words,points,begin,end);
}
static bool face_valid(SmoothPoint a,SmoothPoint b,SmoothPoint c,SmoothPoint aa,SmoothPoint bb,SmoothPoint cc){
#pragma HLS inline
    SmoothPoint na=cross(sub(b,a),sub(c,a));
    SmoothPoint nb=cross(sub(bb,aa),sub(cc,aa));
    return finite(aa)&&finite(bb)&&finite(cc)&&finite(nb)&&
        (!(dot(na,na)>1e-24f)||(dot(na,nb)>0));
}
static bool orientation(SmoothPoint points[4][16384],const PointWord* original,
    PointMemory current,PointMemory candidate,bool active_in_second,const FaceWord* faces,uint32_t nf){
#pragma HLS inline off
    const uint32_t TILE=1024,WINDOW=16384;
    SmoothFace batch[TILE];
#pragma HLS aggregate variable=batch compact=bit
#pragma HLS bind_storage variable=batch type=ram_2p impl=bram
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    bool valid=true,cache_valid=false;uint32_t cache_lo=0,cache_hi=0;
    for(uint32_t base=0;base<nf;base+=TILE){
#pragma HLS loop_tripcount min=0 max=1954
        uint32_t count=nf-base<TILE?nf-base:TILE,lo=0xffffffffu,hi=0;
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            SmoothFace f=read_face(faces,base+j);batch[j]=f;
            uint32_t low=f.a<f.b?f.a:f.b;low=low<f.c?low:f.c;
            uint32_t high=f.a>f.b?f.a:f.b;high=high>f.c?high:f.c;
            if(low<lo)lo=low;if(high>hi)hi=high;
        }
        if(hi-lo<WINDOW){
            // Original and candidate stay unchanged for the whole check.
            // Retain overlap; absolute index modulo WINDOW prevents relabeling.
            uint32_t begin1=lo,end1=hi+1,begin2=0,end2=0;
            if(cache_valid && lo<=cache_hi && hi>=cache_lo){
                end1=lo<cache_lo?cache_lo:lo;
                begin2=hi>cache_hi?cache_hi+1:hi+1;end2=hi+1;
            }
            orientation_before_low:for(uint32_t j=begin1;j<end1;++j){
#pragma HLS pipeline II=1
                SmoothPoint p=read_point(original,j);points[0][j&(WINDOW-1)]=p;points[1][j&(WINDOW-1)]=p;
            }
            orientation_before_high:for(uint32_t j=begin2;j<end2;++j){
#pragma HLS pipeline II=1
                SmoothPoint p=read_point(original,j);points[0][j&(WINDOW-1)]=p;points[1][j&(WINDOW-1)]=p;
            }
            if(active_in_second)load_orientation_current(points,current,begin1,end1);
            else load_orientation_candidate(points,candidate,begin1,end1);
            if(active_in_second)load_orientation_current(points,current,begin2,end2);
            else load_orientation_candidate(points,candidate,begin2,end2);
            retain_cache_window(lo,hi,WINDOW,cache_valid,cache_lo,cache_hi);
            orientation_faces:for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
                SmoothFace f=batch[j];
                bool pass=face_valid(points[0][f.a&(WINDOW-1)],points[0][f.b&(WINDOW-1)],points[1][f.c&(WINDOW-1)],
                    points[2][f.a&(WINDOW-1)],points[2][f.b&(WINDOW-1)],points[3][f.c&(WINDOW-1)]);
                if(!pass)valid=false;
            }
        } else {
            // The unchanged DDR path covers arbitrary vertex numbering.
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=3
                SmoothFace f=batch[j];
                if(!face_valid(read_point(original,f.a),read_point(original,f.b),read_point(original,f.c),
                    active_in_second?read_point(current,f.a):read_point(candidate,f.a),
                    active_in_second?read_point(current,f.b):read_point(candidate,f.b),
                    active_in_second?read_point(current,f.c):read_point(candidate,f.c)))valid=false;
            }
        }
    }
    return valid;
}

// Separate loops let HLS issue bursts instead of alternating independent DDR
// addresses on the same AXI read/write channel for every vertex.
static void make_half(const PointWord* original,const uint32_t* frozen,
    PointMemory current,PointMemory candidate,PointMemory lap,PointMemory next_lap,
    PointMemory half,bool active_in_second,uint32_t nv,float coefficient){
#pragma HLS inline off
    SmoothPoint p[128],l[128],o[128];uint32_t fixed[128];
    for(uint32_t base=0;base<nv;base+=128){
        uint32_t count=nv-base<128?nv-base:128;
        if(active_in_second){load_local_candidate(candidate,p,base,count);load_local_next_lap(next_lap,l,base,count);}
        else {load_local_current(current,p,base,count);load_local_lap(lap,l,base,count);}
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            o[j]=read_point(original,base+j);
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            fixed[j]=frozen[base+j];
        }
    half_write_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(half,base+offset,length);
        half_write_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(half,j,pack_point(fixed[j-base]?o[j-base]:add(p[j-base],scale(l[j-base],coefficient))));
        }
        SM_WRITE_END(half);
        offset+=length;
    }
    }
}
// The active and last-attempt values may occupy either original work bank.
// Normalize both named outputs once, retaining even rejected retry contents.
// A swap first reads both tile slices, so no live value is overwritten.
static void normalize_coords(PointMemory current,PointMemory candidate,uint32_t nv,
    bool active_in_second,bool last_in_second){
#pragma HLS inline off
    if(!active_in_second && last_in_second)return;
    PointWord left[128],right[128];
    for(uint32_t base=0;base<nv;base+=128){
        uint32_t count=nv-base<128?nv-base:128;
        if(!active_in_second || !last_in_second){
    normalize_coords_first_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_READ_BEGIN(current,base+offset,length);
        normalize_coords_first_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            left[j-base]=SM_READ_WORD(current,j);
        }
        offset+=length;
    }
        }
        if(active_in_second){
    normalize_coords_second_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_READ_BEGIN(candidate,base+offset,length);
        normalize_coords_second_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            right[j-base]=SM_READ_WORD(candidate,j);
        }
        offset+=length;
    }
    normalize_coords_write_first_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(current,base+offset,length);
        normalize_coords_write_first_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(current,j,right[j-base]);
        }
        SM_WRITE_END(current);
        offset+=length;
    }
        }
        if(!last_in_second){
    normalize_coords_write_second_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(candidate,base+offset,length);
        normalize_coords_write_second_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(candidate,j,left[j-base]);
        }
        SM_WRITE_END(candidate);
        offset+=length;
    }
        }
    }
}
static void normalize_lap(PointMemory lap,PointMemory next_lap,uint32_t nv,
    bool active_in_second,bool last_in_second){
#pragma HLS inline off
    if(!active_in_second && last_in_second)return;
    PointWord left[128],right[128];
    for(uint32_t base=0;base<nv;base+=128){
        uint32_t count=nv-base<128?nv-base:128;
        if(!active_in_second || !last_in_second){
    normalize_lap_first_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_READ_BEGIN(lap,base+offset,length);
        normalize_lap_first_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            left[j-base]=SM_READ_WORD(lap,j);
        }
        offset+=length;
    }
        }
        if(active_in_second){
    normalize_lap_second_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_READ_BEGIN(next_lap,base+offset,length);
        normalize_lap_second_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            right[j-base]=SM_READ_WORD(next_lap,j);
        }
        offset+=length;
    }
    normalize_lap_write_first_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(lap,base+offset,length);
        normalize_lap_write_first_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(lap,j,right[j-base]);
        }
        SM_WRITE_END(lap);
        offset+=length;
    }
        }
        if(!last_in_second){
    normalize_lap_write_second_groups:for(uint32_t offset=0;offset<count;){
        uint32_t length=bounded_burst_count(base+offset,count-offset);
        SM_WRITE_BEGIN(next_lap,base+offset,length);
        normalize_lap_write_second_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t j=base+offset+k;
            SM_WRITE_WORD(next_lap,j,left[j-base]);
        }
        SM_WRITE_END(next_lap);
        offset+=length;
    }
        }
    }
}
extern "C" void mesh_smooth_axis(GraphInput& input,GraphOutput& output,const PointWord* original,
    const uint32_t* rows,uint64_t graph_address,const uint32_t* frozen,
    const FaceWord* faces,PointMemory current,PointMemory half,
    PointMemory candidate,PointMemory lap,PointMemory next_lap,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations){
#pragma HLS interface axis port=input register_mode=both
#pragma HLS interface axis port=output register_mode=both
#pragma HLS interface m_axi port=original bundle=row_mem depth=65537 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS interface m_axi port=current bundle=coords channel=0 depth=65537 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=1
#pragma HLS interface m_axi port=half bundle=coords channel=1 depth=65537 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=1
#pragma HLS interface m_axi port=candidate bundle=coords channel=2 depth=65537 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=1
#pragma HLS interface m_axi port=lap bundle=coords channel=3 depth=65537 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=1
#pragma HLS interface m_axi port=next_lap bundle=coords channel=4 depth=65537 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=1
#pragma HLS interface m_axi port=rows bundle=meta depth=65537 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS interface m_axi port=frozen bundle=meta depth=65537
#pragma HLS interface m_axi port=faces bundle=face_mem depth=8192 max_read_burst_length=64 num_read_outstanding=4
#pragma HLS interface m_axi port=report bundle=meta depth=16
#pragma HLS interface s_axilite port=original bundle=control offset=0x10
#pragma HLS interface s_axilite port=rows bundle=control offset=0x20
#pragma HLS interface s_axilite port=graph_address bundle=control offset=0x30
#pragma HLS interface s_axilite port=frozen bundle=control offset=0x40
#pragma HLS interface s_axilite port=faces bundle=control offset=0x50
#pragma HLS interface s_axilite port=current bundle=control offset=0x60
#pragma HLS interface s_axilite port=half bundle=control offset=0x70
#pragma HLS interface s_axilite port=candidate bundle=control offset=0x80
#pragma HLS interface s_axilite port=lap bundle=control offset=0x90
#pragma HLS interface s_axilite port=next_lap bundle=control offset=0xa0
#pragma HLS interface s_axilite port=report bundle=control offset=0xb0
#pragma HLS interface s_axilite port=nv bundle=control offset=0xc0
#pragma HLS interface s_axilite port=nf bundle=control offset=0xc8
#pragma HLS interface s_axilite port=nnz bundle=control offset=0xd0
#pragma HLS interface s_axilite port=limit bundle=control offset=0xd8
#pragma HLS interface s_axilite port=iterations bundle=control offset=0xe0
#pragma HLS interface s_axilite port=return bundle=control
    GraphTask edges(input,output,nv,nnz,graph_address);
    SmoothPoint points[4][16384];
#pragma HLS array_partition variable=points complete dim=1
#pragma HLS aggregate variable=points compact=bit
#pragma HLS bind_storage variable=points type=ram_t2p impl=uram
    for(unsigned i=0;i<16;++i)report[i]=0;
    if(!nv||nv>1000000||nf>2000000||nnz>12000000||iterations<1||iterations>16||!(limit>0)||!std::isfinite(limit)){report[0]=1;edges.errors|=smooth_graph_axis::BAD_CONFIG;edges.final();return;}
    initialize_current_groups:for(uint32_t offset=0;offset<nv;){
        uint32_t length=bounded_burst_count(0+offset,nv-offset);
        SM_WRITE_BEGIN(current,0+offset,length);
        initialize_current_words:for(uint32_t k=0;k<length;++k){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=64
            uint32_t i=0+offset+k;
            SM_WRITE_WORD(current,i,pack_point(read_point(original,i)));
        }
        SM_WRITE_END(current);
        offset+=length;
    }

    double current_roughness=0;
    average_selected(points,current,half,candidate,lap,next_lap,original,rows,edges,frozen,0,3,nv,nnz,0,0,limit,current_roughness);
    report[2]=bits(float(current_roughness));unsigned accepted=0,attempts=0;
    bool active_in_second=false,last_candidate_in_second=true,last_lap_in_second=true;
    for(unsigned iteration=0;iteration<iterations;++iteration){
        bool advanced=false;float step=1.f;
        for(unsigned retry=0;retry<4;++retry,step*=.5f){
            ++attempts;
            make_half(original,frozen,current,candidate,lap,next_lap,half,active_in_second,nv,.5f*step);
            double unused=0;
            last_candidate_in_second=!active_in_second;
            average_selected(points,current,half,candidate,lap,next_lap,original,rows,edges,frozen,
                1,active_in_second?0:2,nv,nnz,1,.53f*step,limit,unused);
            if(!orientation(points,original,current,candidate,active_in_second,faces,nf))continue;
            double next_roughness=0;
            last_lap_in_second=!active_in_second;
            average_selected(points,current,half,candidate,lap,next_lap,original,rows,edges,frozen,
                active_in_second?0:2,active_in_second?3:4,nv,nnz,0,0,limit,next_roughness);
            if(!std::isfinite(next_roughness)||!(next_roughness<current_roughness))continue;
            active_in_second=!active_in_second;
            current_roughness=next_roughness;++accepted;advanced=true;break;
        }
        if(!advanced)break;
    }
    normalize_coords(current,candidate,nv,active_in_second,last_candidate_in_second);
    normalize_lap(lap,next_lap,nv,active_in_second,last_lap_in_second);
    report[1]=accepted;report[3]=bits(float(current_roughness));report[4]=attempts;
    edges.final();
}

#include "native_abi.inc"

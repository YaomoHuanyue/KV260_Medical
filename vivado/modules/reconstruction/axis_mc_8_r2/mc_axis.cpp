#include "mc_axis.hpp"
#include "binary_lewiner.hpp"
#ifdef MC_AXIS_NATIVE
#include <queue>
template<class T> class Stream {
    std::queue<T> queue;
public:
    void write(const T& v) { queue.push(v); }
    T read() { T v=queue.front();queue.pop();return v; }
};
using PlaneWord=uint64_t;
#else
template<class T> using Stream=hls::stream<T>;
using PlaneWord=ap_uint<64>;
#endif

struct Cell {
    uint16_t x,y,z;
    uint8_t code[8],active;
    bool last;
    uint32_t total,errors;
};
struct Vertex {
    uint64_t value;
    bool last;
    uint32_t required,written,errors;
};

static uint32_t framing(const McAxisWord& w,uint32_t index,uint32_t words) {
#pragma HLS inline
    uint32_t error=0;
    if(uint64_t(w.keep)!=~uint64_t(0))error|=mc_axis::KEEP;
    if(uint64_t(w.strb)!=~uint64_t(0))error|=mc_axis::STRB;
    if(bool(w.user)!=(index==0))error|=mc_axis::USER;
    if(bool(w.last)!=(index+1==words))error|=mc_axis::LAST;
    return error;
}

static uint8_t next_byte(McAxisWord& w,unsigned offset) {
#pragma HLS inline
#ifdef MC_AXIS_NATIVE
    return w.data[offset];
#else
    const uint8_t v=w.data.range(7,0);
    w.data>>=8;
    return v;
#endif
}

static McAxisWord empty_word() {
#pragma HLS inline
    McAxisWord w{};
#ifndef MC_AXIS_NATIVE
    w.data=0;
#endif
    w.keep=w.strb=~uint64_t(0);
    return w;
}

static void put_u64(McAxisWord& w,unsigned lane,uint64_t value) {
#pragma HLS inline
#ifdef MC_AXIS_NATIVE
    for(unsigned b=0;b<8;++b)w.data[lane*8+b]=uint8_t(value>>(8*b));
#else
    w.data.range(64*lane+63,64*lane)=value;
#endif
}

static McAxisWord footer(uint32_t errors,uint32_t required,uint32_t written,
    uint32_t nx,uint32_t ny,uint32_t nz,uint32_t capacity,uint32_t mode,
    uint32_t expected,uint32_t inputs,uint32_t outputs) {
#pragma HLS inline
    McAxisWord w=empty_word();
    const uint32_t fields[16]={mc_axis::MAGIC,1,errors,required,written,nx,ny,nz,
        inputs,outputs,capacity,mode,expected,written*3,0,0};
    footer_fields:for(unsigned lane=0;lane<8;++lane) {
#pragma HLS unroll
        put_u64(w,lane,uint64_t(fields[lane*2])|(uint64_t(fields[lane*2+1])<<32));
    }
    w.user=outputs==1;w.last=true;
    return w;
}

#include "scan8.inc"
#include "triangulate8.inc"

static void pack(Stream<Vertex>& vertices,McAxisStream& output,
    uint32_t nx,uint32_t ny,uint32_t nz,uint32_t capacity,uint32_t mode,
    uint32_t expected,uint32_t input_words) {
#pragma HLS inline off
    const uint32_t triangles=mode?0:(capacity<expected?capacity:expected);
    const uint32_t target=triangles*3, beats=(target+7)/8;
    uint32_t emitted=0;
    unsigned lane=0;
    McAxisWord word=empty_word();
    Vertex end{};
    while(true) {
#pragma HLS pipeline II=1
        const Vertex v=vertices.read();
        if(v.last){end=v;break;}
        put_u64(word,lane,v.value);
        ++emitted;
        if(++lane==8) {
            word.user=emitted==8;word.last=false;output.write(word);
            word=empty_word();lane=0;
        }
    }
    // A changed mask between count and produce cannot leave the fixed DMA
    // writer waiting. Pad the declared transfer, flag mismatch, reject on host.
    pad_missing:for(uint32_t i=emitted;i<target;++i) {
#pragma HLS pipeline II=1
        put_u64(word,lane,0);
        if(++lane==8) {
            word.user=i<8;word.last=false;output.write(word);
            word=empty_word();lane=0;
        }
    }
    if(lane) {
        word.user=beats==1;word.last=false;output.write(word);
    }
    output.write(footer(end.errors,end.required,end.written,nx,ny,nz,capacity,
        mode,expected,input_words,beats+1));
}

static void execute(McAxisStream& input,McAxisStream& output,uint32_t nx,
    uint32_t ny,uint32_t nz,uint32_t capacity,uint32_t mode,uint32_t expected,uint32_t words) {
#pragma HLS dataflow
    Stream<Cell> cells;
    Stream<Vertex> vertices;
#pragma HLS stream variable=cells depth=64
#pragma HLS stream variable=vertices depth=64
    scan(input,nx,ny,nz,mode!=0,words,cells);
    triangulate(cells,vertices,capacity,mode!=0,expected);
    pack(vertices,output,nx,ny,nz,capacity,mode,expected,words);
}

extern "C" void binary_mc_axis(McAxisStream& input,McAxisStream& output,
    uint32_t nx,uint32_t ny,uint32_t nz,uint32_t capacity_triangles,
    uint32_t count_only,uint32_t expected_triangles,uint32_t input_words) {
#pragma HLS interface axis port=input register_mode=both
#pragma HLS interface axis port=output register_mode=both
#pragma HLS interface s_axilite port=nx bundle=control offset=0x10
#pragma HLS interface s_axilite port=ny bundle=control offset=0x18
#pragma HLS interface s_axilite port=nz bundle=control offset=0x20
#pragma HLS interface s_axilite port=capacity_triangles bundle=control offset=0x28
#pragma HLS interface s_axilite port=count_only bundle=control offset=0x30
#pragma HLS interface s_axilite port=expected_triangles bundle=control offset=0x38
#pragma HLS interface s_axilite port=input_words bundle=control offset=0x40
#pragma HLS interface s_axilite port=return bundle=control
    uint32_t errors=0;
    if(nx<2||ny<2||nz<2||nx>mc_axis::MAX_DIM||ny>mc_axis::MAX_DIM||nz>mc_axis::MAX_DIM)
        errors|=mc_axis::BAD_DIMENSIONS;
    if(count_only>1)errors|=mc_axis::BAD_MODE;
    if(input_words>mc_axis::MAX_INPUT_WORDS)errors|=mc_axis::INPUT_LIMIT;
    if(expected_triangles>mc_axis::MAX_TRIANGLES)errors|=mc_axis::EXPECTED_LIMIT;
    if(errors) {
        const uint32_t bounded=input_words<mc_axis::MAX_INPUT_WORDS?input_words:mc_axis::MAX_INPUT_WORDS;
        drain_invalid:for(uint32_t i=0;i<bounded;++i) {
#pragma HLS pipeline II=1
            const McAxisWord w=input.read();errors|=framing(w,i,bounded);
        }
        output.write(footer(errors,0,0,nx,ny,nz,capacity_triangles,count_only,
            expected_triangles,bounded,1));
        return;
    }
    execute(input,output,nx,ny,nz,capacity_triangles,count_only,expected_triangles,input_words);
}

#include "binary_mc.hpp"
#include "../generated/binary_lewiner.hpp"
#ifdef MC_NATIVE
#include <queue>
template<class T> class Stream {
    std::queue<T> q;
public:
    void write(const T& v) { q.push(v); }
    T read() { T v=q.front(); q.pop(); return v; }
};
typedef uint8_t bit_t;
#else
#include <ap_int.h>
#include <hls_stream.h>
template<class T> using Stream = hls::stream<T>;
typedef ap_uint<1> bit_t;
#endif

struct Cell {
    uint16_t x, y, z;
    uint8_t code;
    bool last, invalid;
    uint32_t total;
};

#ifdef MC_CHUNK_WRITER
struct VertexWord {uint64_t value;bool last;};
#endif

// Parity banking supplies all eight cell corners without duplicating RAM.
static const unsigned HALF = MC_MAX_DIM / 2;
#ifdef MC_PACKED_PLANES
#ifdef MC_NATIVE
typedef uint64_t plane_word_t;
#else
typedef ap_uint<64> plane_word_t;
#endif
typedef plane_word_t Planes[2][2][2][HALF * HALF / 64];
#else
typedef bit_t Planes[2][2][2][HALF * HALF];
#endif

static void scan(const uint8_t* volume, unsigned nx, unsigned ny, unsigned nz,
                 bool count_only, Stream<Cell>& cells) {
#pragma HLS INLINE off
    static Planes p;
#pragma HLS ARRAY_PARTITION variable=p complete dim=1
#pragma HLS ARRAY_PARTITION variable=p complete dim=2
#pragma HLS ARRAY_PARTITION variable=p complete dim=3
#ifdef MC_USE_URAM
#pragma HLS BIND_STORAGE variable=p type=ram_2p impl=uram
#ifdef MC_PACKED_PLANES
    // Same-word recent reads are forwarded from registers below. Any RAM read
    // is of an older row/plane or another word, never the preceding write.
    // This explicit bypass removes the URAM read-first dependency.
#pragma HLS DEPENDENCE variable=p inter false
#endif
#else
#pragma HLS BIND_STORAGE variable=p type=ram_2p impl=bram
#endif
    bool invalid = false;
#ifdef MC_PACKED_PLANES
    // Pack 64 binary voxels per RAM word. Recent partial words live in registers
    // so writes never need a RAM read/modify/write transaction.
    plane_word_t recent[2][2][2];
    uint16_t recent_address[2][2][2];
    bool recent_valid[2][2][2];
#pragma HLS ARRAY_PARTITION variable=recent complete dim=0
#pragma HLS ARRAY_PARTITION variable=recent_address complete dim=0
#pragma HLS ARRAY_PARTITION variable=recent_valid complete dim=0
    for(unsigned bz=0;bz<2;++bz)for(unsigned by=0;by<2;++by)for(unsigned bx=0;bx<2;++bx) {
#pragma HLS UNROLL
        recent[bz][by][bx]=0;recent_address[bz][by][bx]=0;recent_valid[bz][by][bx]=false;
    }
#endif
    unsigned x=0,y=0,z=0,total=0;
    const unsigned voxels=nx*ny*nz;
    // The incoming voxel supplies the last corner of a cell; all other corners
    // are already in the rolling parity banks. Bypass the just-written bank.
    for (unsigned index=0; index<voxels; ++index) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=8 max=134217728
        const uint8_t value=volume[index];
        invalid |= value>1;
#ifdef MC_PACKED_PLANES
        const unsigned address=((y/2)*HALF+x/2)/64,shift=(x/2)&63;
        for(unsigned bz=0;bz<2;++bz) {
#pragma HLS UNROLL
            for(unsigned by=0;by<2;++by) {
#pragma HLS UNROLL
                for(unsigned bx=0;bx<2;++bx) {
#pragma HLS UNROLL
                    if(bz==(z&1) && by==(y&1) && bx==(x&1)) {
                        const plane_word_t word=(shift==0 ? plane_word_t(0) : recent[bz][by][bx]) |
                                                (plane_word_t(value&1)<<shift);
                        p[bz][by][bx][address]=word;
                        recent[bz][by][bx]=word;recent_address[bz][by][bx]=address;recent_valid[bz][by][bx]=true;
                    }
                }
            }
        }
#else
        p[z&1][y&1][x&1][(y/2)*HALF+x/2]=value&1;
#endif
        if (x>0 && y>0 && z>0) {
            unsigned code=0;
            // Fix each access to one physical parity bank. Dynamically indexing
            // banks for all seven corners makes HLS infer several reads per
            // bank, defeating the banking and forcing II > 1.
            for (unsigned bz=0; bz<2; ++bz) {
#pragma HLS UNROLL
                for (unsigned by=0; by<2; ++by) {
#pragma HLS UNROLL
                    for (unsigned bx=0; bx<2; ++bx) {
#pragma HLS UNROLL
                        const unsigned dx=(bx==(x&1)),dy=(by==(y&1)),dz=(bz==(z&1));
                        const unsigned xx=x-1+dx,yy=y-1+dy;
#ifdef MC_PACKED_PLANES
                        const unsigned read_address=((yy/2)*HALF+xx/2)/64;
                        const plane_word_t word=(recent_valid[bz][by][bx] && recent_address[bz][by][bx]==read_address) ?
                            recent[bz][by][bx] : p[bz][by][bx][read_address];
                        const unsigned bit=unsigned((word>>((xx/2)&63))&1);
#else
                        const unsigned bit=(dx==1 && dy==1 && dz==1) ?
                            (value&1) : unsigned(p[bz][by][bx][(yy/2)*HALF+xx/2]);
#endif
                        code |= bit << (dz*4+dy*2+dx);
                    }
                }
            }
            total += MC_COUNTS[code];
            if (!count_only && code!=0 && code!=255) {
                Cell c={uint16_t(x-1),uint16_t(y-1),uint16_t(z-1),uint8_t(code),false,false,0};
                cells.write(c);
            }
        }
        if (++x==nx) {x=0;if (++y==ny) {y=0;++z;}}
    }
    Cell end = {0,0,0,0,true,invalid,total};
    cells.write(end);
}

#ifdef MC_CHUNK_WRITER
static void triangulate(Stream<Cell>& cells, Stream<VertexWord>& words, unsigned capacity,
#else
static void triangulate(Stream<Cell>& cells, uint64_t* vertices, unsigned capacity,
#endif
                        bool count_only, uint32_t& required, uint32_t& written,
                        uint32_t& status) {
#pragma HLS INLINE off
    unsigned total=0, stored=0;
    bool invalid=false;
    while (true) {
        Cell c=cells.read();
        if (c.last) { invalid=c.invalid; total=c.total; break; }
        const unsigned n=MC_COUNTS[c.code];
        if (!count_only) {
            // Only whole triangles are written; still count the entire volume
            // after overflow so the caller can retry with an exact allocation.
            unsigned emit = (capacity-stored < n) ? capacity-stored : n;
            for (unsigned i=0; i<emit*3; ++i) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=0 max=27
                uint8_t offsets=MC_VERTICES[c.code][i];
                uint64_t x=unsigned(c.x)*2+(offsets&3);
                uint64_t y=unsigned(c.y)*2+((offsets>>2)&3);
                uint64_t z=unsigned(c.z)*2+((offsets>>4)&3);
#ifdef MC_CHUNK_WRITER
                VertexWord word={x | (y<<16) | (z<<32),false};words.write(word);
#else
                vertices[stored*3+i] = x | (y<<16) | (z<<32);
#endif
            }
            stored += emit;
        }
    }
    required=total;
    written=stored;
    status=(invalid ? MC_NON_BINARY : MC_OK) |
           ((!count_only && total>capacity) ? MC_OVERFLOW : MC_OK);
#ifdef MC_CHUNK_WRITER
    VertexWord end={0,true};words.write(end);
#endif
}

#ifdef MC_CHUNK_WRITER
static void write_vertices(Stream<VertexWord>& words,uint64_t* vertices) {
#pragma HLS INLINE off
    uint64_t chunk[256];
#pragma HLS BIND_STORAGE variable=chunk type=ram_2p impl=bram
    bool done=false;
    unsigned base=0;
    while(!done) {
        unsigned size=0;
        for(unsigned i=0;i<256;++i) {
#pragma HLS PIPELINE II=1
            const VertexWord word=words.read();
            if(word.last){done=true;break;}
            chunk[size++]=word.value;
        }
        // A long contiguous transaction spans cell boundaries. The previous
        // cell-dependent writer could only infer short per-cell bursts.
        for(unsigned i=0;i<size;++i) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=0 max=256
            vertices[base+i]=chunk[i];
        }
        base+=size;
    }
}
#endif

static void execute(const uint8_t* volume, uint64_t* vertices,
                    unsigned nx, unsigned ny, unsigned nz,
                    unsigned capacity, bool count_only,
                    uint32_t& required, uint32_t& written, uint32_t& status) {
#pragma HLS DATAFLOW
    Stream<Cell> cells;
#pragma HLS STREAM variable=cells depth=64
    scan(volume, nx, ny, nz, count_only, cells);
#ifdef MC_CHUNK_WRITER
    Stream<VertexWord> words;
#pragma HLS STREAM variable=words depth=512
    triangulate(cells, words, capacity, count_only, required, written, status);
    write_vertices(words,vertices);
#else
    triangulate(cells, vertices, capacity, count_only, required, written, status);
#endif
}

extern "C" void binary_mc(const uint8_t* volume, uint64_t* vertices,
    uint32_t nx, uint32_t ny, uint32_t nz, uint32_t capacity_triangles,
    uint32_t count_only, uint32_t& triangles_required, uint32_t& triangles_written,
    uint32_t& status) {
// depth describes the C/RTL testbench allocation, not a hardware address limit.
#pragma HLS INTERFACE m_axi port=volume offset=slave bundle=input_mem depth=4096 max_read_burst_length=256
#pragma HLS INTERFACE m_axi port=vertices offset=slave bundle=output_mem depth=4096 max_write_burst_length=256
#pragma HLS INTERFACE s_axilite port=volume bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=vertices bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=nx bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=ny bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=nz bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=capacity_triangles bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=count_only bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=triangles_required bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=triangles_written bundle=control offset=0x68
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x78
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(nx<2 || ny<2 || nz<2 || nx>MC_MAX_DIM || ny>MC_MAX_DIM || nz>MC_MAX_DIM) {
        triangles_required=0; triangles_written=0; status=MC_BAD_DIMENSIONS; return;
    }
    if(count_only>1) {
        triangles_required=0; triangles_written=0; status=MC_BAD_MODE; return;
    }
    execute(volume, vertices, nx, ny, nz, capacity_triangles, count_only!=0,
            triangles_required, triangles_written, status);
}

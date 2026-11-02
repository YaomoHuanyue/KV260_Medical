// Serialize only active lanes, in original Z/Y/X order. Backpressure on this
// stage propagates through the batch FIFO to the voxel scanner and AXIS input.
static void triangulate(Stream<Cell>& cells,Stream<Vertex>& vertices,
    uint32_t capacity,bool count_only,uint32_t expected) {
#pragma HLS inline off
    const uint32_t limit=capacity<expected?capacity:expected;
    uint32_t stored=0;
    while(true) {
        const Cell group=cells.read();
        if(group.last) {
            uint32_t errors=group.errors;
            if(!count_only&&group.total>capacity)errors|=mc_axis::OVERFLOW;
            if(!count_only&&group.total!=expected)errors|=mc_axis::COUNT_MISMATCH;
            Vertex end={0,true,group.total,stored,errors};vertices.write(end);break;
        }
        uint8_t active=group.active;
        while(active) {
            unsigned lane=0;
            for(unsigned j=0;j<8;++j) {
#pragma HLS unroll
                if(active&(1u<<(7-j)))lane=7-j;
            }
            active&=uint8_t(~(1u<<lane));
            const unsigned n=MC_COUNTS[group.code[lane]];
            const unsigned emit=limit-stored<n?limit-stored:n;
            emit_vertices:for(unsigned i=0;i<emit*3;++i) {
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=0 max=27
                const uint8_t offsets=MC_VERTICES[group.code[lane]][i];
                const uint64_t x=(unsigned(group.x)+lane-1)*2+(offsets&3);
                const uint64_t y=unsigned(group.y)*2+((offsets>>2)&3);
                const uint64_t z=unsigned(group.z)*2+((offsets>>4)&3);
                Vertex v={x|(y<<16)|(z<<32),false,0,0,0};vertices.write(v);
            }
            stored+=emit;
        }
    }
}

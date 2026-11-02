#include <cmath>
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

struct Row {SmoothPoint point,original;uint32_t count,frozen;};
struct Neighbor {SmoothPoint point;float weight;};
struct MeanRow {Row row;SmoothPoint mean;};

// Prefetch a contiguous graph tile and its coordinate window in DDR bursts.
// Preserve the original CSR accumulation order. Unusually wide/high-degree
// tiles use direct reads, so the optimization does not restrict valid meshes.
static void gather_tiles(const SmoothPoint* source,const SmoothPoint* original,
    const uint32_t* rows,const SmoothEdge* edges,const uint32_t* frozen,
    uint32_t nv,int expand,hls::stream<Row>& commands,hls::stream<Neighbor>& neighbors){
#pragma HLS inline off
    const uint32_t TILE=2048,EDGE_CAP=16384,WINDOW=32768;
    SmoothPoint points[WINDOW],initial[TILE];SmoothEdge graph[EDGE_CAP];
    uint32_t ends[TILE],fixed[TILE];
#pragma HLS aggregate variable=points compact=bit
#pragma HLS aggregate variable=initial compact=bit
#pragma HLS aggregate variable=graph compact=bit
#pragma HLS bind_storage variable=points type=ram_2p impl=uram
#pragma HLS bind_storage variable=graph type=ram_2p impl=uram
    for(uint32_t base=0;base<nv;base+=TILE){
#pragma HLS loop_tripcount min=1 max=489
        uint32_t count=nv-base<TILE?nv-base:TILE;
        uint32_t first=rows[base];
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            ends[j]=rows[base+j+1];
        }
        if(expand){
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
                initial[j]=original[base+j];
            }
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
                fixed[j]=frozen[base+j];
            }
        }
        uint32_t edge_count=ends[count-1]-first,lo=base,hi=base+count-1;
        bool graph_cached=edge_count<=EDGE_CAP;
        if(graph_cached){
            for(uint32_t e=0;e<edge_count;++e){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=0 max=16384
                SmoothEdge item=edges[first+e];graph[e]=item;
                if(item.index<lo)lo=item.index;
                if(item.index>hi)hi=item.index;
            }
        }
        bool window_cached=graph_cached && hi-lo<WINDOW;
        if(window_cached){
            for(uint32_t j=0;j<=hi-lo;++j){
#pragma HLS pipeline II=1
#pragma HLS loop_tripcount min=1 max=32768
                points[j]=source[lo+j];
            }
        }
        uint32_t remaining=0,vertex=0,edge=0,begin=first;
        for(uint32_t token=0;token<count+edge_count;++token){
#pragma HLS pipeline II=4
#pragma HLS loop_tripcount min=1 max=18432
            uint32_t index;float weight=0;
            if(!remaining){
                remaining=ends[vertex]-begin;begin=ends[vertex];index=base+vertex;
                SmoothPoint p=expand?initial[vertex]:SmoothPoint{0,0,0,0};
                commands.write({{0,0,0,0},p,remaining,expand?fixed[vertex]:0});
                ++vertex;
            } else {
                SmoothEdge item=graph_cached?graph[edge]:edges[first+edge];
                index=item.index;weight=item.weight;++edge;--remaining;
            }
            SmoothPoint point=window_cached?points[index-lo]:source[index];
            neighbors.write({point,weight});
        }
    }
}
static void reduce_neighbors(hls::stream<Row>& commands,hls::stream<Neighbor>& neighbors,
    hls::stream<MeanRow>& means,uint32_t nv,uint32_t nnz){
#pragma HLS inline off
    Row row;SmoothPoint mean={0,0,0,0};uint32_t remaining=0;
    // One row-start token plus one token per edge, including isolated rows.
    // A single pipeline avoids draining/refilling the adder at every vertex.
    for(uint32_t token=0;token<nv+nnz;++token){
#pragma HLS pipeline II=4
#pragma HLS loop_tripcount min=1200 max=3500000
        if(!remaining){
            row=commands.read();row.point=neighbors.read().point;
            mean={0,0,0,0};remaining=row.count;
            if(!remaining)means.write({row,mean});
        } else {
            Neighbor neighbor=neighbors.read();
            mean={std::fma(neighbor.point.x,neighbor.weight,mean.x),
                  std::fma(neighbor.point.y,neighbor.weight,mean.y),
                  std::fma(neighbor.point.z,neighbor.weight,mean.z),0};
            --remaining;
            if(!remaining)means.write({row,mean});
        }
    }
}
static void apply_rows(hls::stream<MeanRow>& means,SmoothPoint* output,
    uint32_t nv,int expand,float coefficient,float limit,double& roughness){
#pragma HLS inline off
    double total=0;
    for(uint32_t i=0;i<nv;++i){
#pragma HLS pipeline II=8
#pragma HLS loop_tripcount min=192 max=500000
        MeanRow item=means.read();Row row=item.row;
        SmoothPoint delta=sub(item.mean,row.point);
        if(!expand){output[i]=delta;total+=double(norm(delta));}
        else {
            SmoothPoint trial=sub(row.point,scale(delta,coefficient));
            SmoothPoint displacement=sub(trial,row.original);
            float length=norm(displacement);
            float factor=length>limit ? limit/length : 1.f;
            trial=add(row.original,scale(displacement,factor));
            output[i]=row.frozen ? row.original : trial;
        }
    }
    roughness=total/double(nv);
}
static void average_stage(const SmoothPoint* source,const SmoothPoint* original,
    const uint32_t* rows,const SmoothEdge* edges,const uint32_t* frozen,
    SmoothPoint* output,uint32_t nv,uint32_t nnz,int expand,float coefficient,float limit,double& roughness){
#pragma HLS inline off
#pragma HLS dataflow
    hls::stream<Row> commands;
    hls::stream<Neighbor> neighbors;
    hls::stream<MeanRow> means;
#pragma HLS stream variable=commands depth=64
#pragma HLS stream variable=neighbors depth=256
#pragma HLS stream variable=means depth=64
    gather_tiles(source,original,rows,edges,frozen,nv,expand,commands,neighbors);
    reduce_neighbors(commands,neighbors,means,nv,nnz);
    apply_rows(means,output,nv,expand,coefficient,limit,roughness);
}
static bool face_valid(SmoothPoint a,SmoothPoint b,SmoothPoint c,SmoothPoint aa,SmoothPoint bb,SmoothPoint cc){
#pragma HLS inline
    SmoothPoint na=cross(sub(b,a),sub(c,a));
    SmoothPoint nb=cross(sub(bb,aa),sub(cc,aa));
    return finite(aa)&&finite(bb)&&finite(cc)&&finite(nb)&&
        (!(dot(na,na)>1e-24f)||(dot(na,nb)>0));
}
static bool orientation(const SmoothPoint* original,const SmoothPoint* candidate,const SmoothFace* faces,uint32_t nf){
#pragma HLS inline off
    const uint32_t TILE=4096,WINDOW=16384;
    SmoothFace batch[TILE];SmoothPoint before[WINDOW],after[WINDOW];
#pragma HLS aggregate variable=batch compact=bit
#pragma HLS aggregate variable=before compact=bit
#pragma HLS aggregate variable=after compact=bit
#pragma HLS bind_storage variable=batch type=ram_2p impl=bram
#pragma HLS bind_storage variable=before type=ram_2p impl=uram
#pragma HLS bind_storage variable=after type=ram_2p impl=uram
    bool valid=true;
    for(uint32_t base=0;base<nf;base+=TILE){
#pragma HLS loop_tripcount min=0 max=489
        uint32_t count=nf-base<TILE?nf-base:TILE,lo=0xffffffffu,hi=0;
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            SmoothFace f=faces[base+j];batch[j]=f;
            uint32_t low=f.a<f.b?f.a:f.b;low=low<f.c?low:f.c;
            uint32_t high=f.a>f.b?f.a:f.b;high=high>f.c?high:f.c;
            if(low<lo)lo=low;if(high>hi)hi=high;
        }
        if(hi-lo<WINDOW){
            for(uint32_t j=0;j<=hi-lo;++j){
#pragma HLS pipeline II=1
                before[j]=original[lo+j];
            }
            for(uint32_t j=0;j<=hi-lo;++j){
#pragma HLS pipeline II=1
                after[j]=candidate[lo+j];
            }
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=2
                SmoothFace f=batch[j];
                bool pass=face_valid(before[f.a-lo],before[f.b-lo],before[f.c-lo],
                    after[f.a-lo],after[f.b-lo],after[f.c-lo]);
                if(!pass)valid=false;
            }
        } else {
            // Arbitrary vertex numbering is supported without changing faces.
            for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=3
                SmoothFace f=batch[j];
                if(!face_valid(original[f.a],original[f.b],original[f.c],
                    candidate[f.a],candidate[f.b],candidate[f.c]))valid=false;
            }
        }
    }
    return valid;
}
// Separate loops let HLS issue bursts instead of alternating independent DDR
// addresses on the same AXI read/write channel for every vertex.
static void make_half(const SmoothPoint* original,const uint32_t* frozen,
    const SmoothPoint* current,const SmoothPoint* lap,SmoothPoint* half,uint32_t nv,float coefficient){
#pragma HLS inline off
    SmoothPoint p[128],l[128],o[128];uint32_t fixed[128];
    for(uint32_t base=0;base<nv;base+=128){
        uint32_t count=nv-base<128?nv-base:128;
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            p[j]=current[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            l[j]=lap[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            o[j]=original[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            fixed[j]=frozen[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            half[base+j]=fixed[j]?o[j]:add(p[j],scale(l[j],coefficient));
        }
    }
}
static void accept_candidate(const SmoothPoint* candidate,const SmoothPoint* next_lap,
    SmoothPoint* current,SmoothPoint* lap,uint32_t nv){
#pragma HLS inline off
    SmoothPoint p[128],l[128];
    for(uint32_t base=0;base<nv;base+=128){
        uint32_t count=nv-base<128?nv-base:128;
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            p[j]=candidate[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            l[j]=next_lap[base+j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            current[base+j]=p[j];
        }
        for(uint32_t j=0;j<count;++j){
#pragma HLS pipeline II=1
            lap[base+j]=l[j];
        }
    }
}
extern "C" void mesh_smooth(const SmoothPoint* original,
    const uint32_t* rows,const SmoothEdge* edges,const uint32_t* frozen,
    const SmoothFace* faces,SmoothPoint* current,SmoothPoint* half,
    SmoothPoint* candidate,SmoothPoint* lap,SmoothPoint* next_lap,uint32_t* report,
    uint32_t nv,uint32_t nf,uint32_t nnz,float limit,uint32_t iterations){
#pragma HLS interface m_axi port=original bundle=row_mem depth=4096 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS interface m_axi port=current bundle=coords depth=4096 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=16 num_write_outstanding=16
#pragma HLS interface m_axi port=half bundle=coords depth=4096
#pragma HLS interface m_axi port=candidate bundle=coords depth=4096
#pragma HLS interface m_axi port=lap bundle=coords depth=4096
#pragma HLS interface m_axi port=next_lap bundle=coords depth=4096
#pragma HLS interface m_axi port=rows bundle=meta depth=4096 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS interface m_axi port=edges bundle=graph depth=32768 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS interface m_axi port=frozen bundle=meta depth=4096
#pragma HLS interface m_axi port=faces bundle=face_mem depth=8192 max_read_burst_length=64 num_read_outstanding=16
#pragma HLS interface m_axi port=report bundle=meta depth=16
#pragma HLS aggregate variable=original compact=none
#pragma HLS aggregate variable=current compact=none
#pragma HLS aggregate variable=half compact=none
#pragma HLS aggregate variable=candidate compact=none
#pragma HLS aggregate variable=lap compact=none
#pragma HLS aggregate variable=next_lap compact=none
#pragma HLS aggregate variable=edges compact=none
#pragma HLS aggregate variable=faces compact=none
#pragma HLS interface s_axilite port=original bundle=control offset=0x10
#pragma HLS interface s_axilite port=rows bundle=control offset=0x20
#pragma HLS interface s_axilite port=edges bundle=control offset=0x30
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
    for(unsigned i=0;i<16;++i)report[i]=0;
    if(!nv||nv>1000000||nf>2000000||nnz>12000000||iterations<1||iterations>16||!(limit>0)||!std::isfinite(limit)){report[0]=1;return;}
    for(uint32_t i=0;i<nv;++i){
#pragma HLS pipeline II=1
        current[i]=original[i];
    }
    double current_roughness=0;
    average_stage(current,original,rows,edges,frozen,lap,nv,nnz,0,0,limit,current_roughness);
    report[2]=bits(float(current_roughness));unsigned accepted=0,attempts=0;
    for(unsigned iteration=0;iteration<iterations;++iteration){
        bool advanced=false;float step=1.f;
        for(unsigned retry=0;retry<4;++retry,step*=.5f){
            ++attempts;
            make_half(original,frozen,current,lap,half,nv,.5f*step);
            double unused=0;
            average_stage(half,original,rows,edges,frozen,candidate,nv,nnz,1,.53f*step,limit,unused);
            if(!orientation(original,candidate,faces,nf))continue;
            double next_roughness=0;
            average_stage(candidate,original,rows,edges,frozen,next_lap,nv,nnz,0,0,limit,next_roughness);
            if(!std::isfinite(next_roughness)||!(next_roughness<current_roughness))continue;
            accept_candidate(candidate,next_lap,current,lap,nv);
            current_roughness=next_roughness;++accepted;advanced=true;break;
        }
        if(!advanced)break;
    }
    report[1]=accepted;report[3]=bits(float(current_roughness));report[4]=attempts;
}

#include "route.hpp"
#include "audit.hpp"
#include <cmath>
#include <algorithm>

static double real(uint64_t bits){double x;std::memcpy(&x,&bits,8);return x;}
static uint64_t bits(double x){uint64_t v;std::memcpy(&v,&x,8);return v;}
static float single(uint32_t b){float x;std::memcpy(&x,&b,4);return x;}
static Word read_word(Stream<Packet>& in,unsigned count,unsigned& id,unsigned& error){
    Word w{};
    if(id>=count){error|=1;return w;}
    Packet p=in.read();
    if(p.keep!=~uint64_t(0)||p.strb!=~uint64_t(0)||bool(p.user)!=(id==0)||bool(p.last)!=(id+1==count))error|=1;
    ++id;return p.data;
}

// The sparse field is banked by XYZ parity. A trilinear query's eight corners
// use eight different value banks. Two floats per word avoid wasting URAM width.
static uint64_t values[8][ROUTE_BRICKS*4],tilemap[ROUTE_TILES/4];
static double nodes[3][ROUTE_NODES],radii[ROUTE_NODES];
static uint16_t component[ROUTE_NODES],head[ROUTE_NODES],neighbor[ROUTE_NODES*2],link[ROUTE_NODES*2];
static uint16_t edge_u[ROUTE_NODES],edge_v[ROUTE_NODES];
static unsigned nn=0,ne=0,root=0,dim[3],tiles[3];
static double origin[3],spacing[3],direction[3][3],min_spacing=0,resolution=0;
static uint64_t token=0;static bool loaded=false;
static bool edge_cache_valid=false,edge_inside_cache[ROUTE_NODES];
static double edge_cache_step=0;
static float edge_min_radius_cache[ROUTE_NODES];

static void index_point(const double p[3],double q[3]){
#pragma HLS INLINE off
    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
        q[a]=((p[0]-origin[0])*direction[0][a]+(p[1]-origin[1])*direction[1][a]+(p[2]-origin[2])*direction[2][a])/spacing[a];
    }
}
static float field(int x,int y,int z){
#pragma HLS INLINE
    if(x<0||y<0||z<0||x>=int(dim[0])||y>=int(dim[1])||z>=int(dim[2]))return 0;
    unsigned t=((unsigned(z)>>2)*tiles[1]+(unsigned(y)>>2))*tiles[0]+(unsigned(x)>>2);
    unsigned brick=unsigned((tilemap[t>>2]>>((t&3)*16))&65535);
    if(!brick)return 0;
    unsigned bank=(x&1)+2*(y&1)+4*(z&1),key=((z&3)>>1)*4+((y&3)>>1)*2+((x&3)>>1);
    uint64_t word=values[bank][(brick-1)*4+(key>>1)];return single(uint32_t(word>>((key&1)*32)));
}
static float radius_index(const double q[3],bool& inside){
#pragma HLS INLINE off
    // Share the closed-voxel coordinates even for out-of-bounds/tie fallback;
    // do not synthesize a second floating-point nearest-voxel calculation.
    bool bounded=q[0]>=0&&q[1]>=0&&q[2]>=0&&q[0]<=dim[0]-1&&q[1]<=dim[1]-1&&q[2]<=dim[2]-1;
    int xyz[3],nearest[3];bool tie[3];double f[3];bool shared=bounded;
#pragma HLS ARRAY_PARTITION variable=xyz complete
#pragma HLS ARRAY_PARTITION variable=nearest complete
#pragma HLS ARRAY_PARTITION variable=tie complete
#pragma HLS ARRAY_PARTITION variable=f complete
    for(unsigned a=0;a<3;++a){
        nearest[a]=int(std::floor(q[a]+.5+1e-7));tie[a]=std::abs(q[a]+.5-std::round(q[a]+.5))<1e-7;
        if(bounded){xyz[a]=int(std::floor(q[a]));f[a]=q[a]-xyz[a];shared&=nearest[a]<=xyz[a]+1&&nearest[a]-int(tie[a])>=xyz[a];}
    }
    inside=false;double answer=0;
    if(bounded){double terms[8];
#pragma HLS ARRAY_PARTITION variable=terms complete
        for(unsigned k=0;k<8;++k){
#pragma HLS PIPELINE
            unsigned x=k&1,y=(k>>1)&1,z=(k>>2)&1;
            double w=(x?f[0]:1-f[0])*(y?f[1]:1-f[1])*(z?f[2]:1-f[2]);
            float voxel=field(xyz[0]+x,xyz[1]+y,xyz[2]+z);terms[k]=double(voxel)*w;
            bool selected=(xyz[0]+int(x)>=nearest[0]-int(tie[0])&&xyz[0]+int(x)<=nearest[0])
                       &&(xyz[1]+int(y)>=nearest[1]-int(tie[1])&&xyz[1]+int(y)<=nearest[1])
                       &&(xyz[2]+int(z)>=nearest[2]-int(tie[2])&&xyz[2]+int(z)<=nearest[2]);
            inside|=selected&&voxel>0;
        }
#pragma HLS BIND_OP variable=answer op=dadd impl=fulldsp latency=5
        for(unsigned k=0;k<8;++k){
#pragma HLS PIPELINE II=6
            answer+=terms[k];
        }
    }
    if(!shared){inside=false;for(unsigned k=0;k<8;++k){
#pragma HLS PIPELINE
        int x=nearest[0]-int(tie[0]&&bool(k&1)),y=nearest[1]-int(tie[1]&&bool(k&2)),z=nearest[2]-int(tie[2]&&bool(k&4));
        inside|=field(x,y,z)>0;
    }}return float(answer);
}
static bool query_field(double x,double y,double z,float& radius){
#pragma HLS INLINE off
    double p[3]={x,y,z},q[3];bool inside;index_point(p,q);radius=radius_index(q,inside);
    return inside;
}
static bool valid(const double p[3],double required,double margin){
#pragma HLS INLINE
    float radius;bool inside=query_field(p[0],p[1],p[2],radius);return inside&&double(radius)-margin+1e-5>=required;
}
static double norm3_scalar(double x,double y,double z){
#pragma HLS INLINE off
    return std::sqrt(x*x+y*y+z*z);
}
static double norm3(const double p[3]){
#pragma HLS INLINE
    return norm3_scalar(p[0],p[1],p[2]);
}
static double distance(const double a[3],const double b[3]){
#pragma HLS INLINE
    return norm3_scalar(a[0]-b[0],a[1]-b[1],a[2]-b[2]);
}
static void node_point(unsigned i,double p[3]){
#pragma HLS INLINE
    for(unsigned a=0;a<3;++a)p[a]=nodes[a][i];
}
static unsigned load_scene(Stream<Packet>& in,unsigned count,unsigned& read,unsigned& error){
    Word w=read_word(in,count,read,error);uint64_t size=lane(w,4),tile=lane(w,5);
    nn=unsigned(lane(w,1));ne=unsigned(lane(w,2));root=unsigned(lane(w,3));unsigned nt=unsigned(lane(w,6)),nb=unsigned(lane(w,7));
    for(unsigned a=0;a<3;++a){dim[a]=unsigned((size>>(a*16))&65535);tiles[a]=unsigned((tile>>(a*16))&65535);}
    loaded=false;edge_cache_valid=false;
    if(lane(w,0)!=ROUTE_SCENE_MAGIC||!nn||nn>ROUTE_NODES||ne>=ROUTE_NODES||root>=nn||!nt||nt>ROUTE_TILES||!nb||nb>ROUTE_BRICKS)return 2;
    for(unsigned a=0;a<3;++a)if(!dim[a]||dim[a]>1024||tiles[a]!=(dim[a]+3)/4)return 2;
    if(nt!=tiles[0]*tiles[1]*tiles[2]||count!=4+nn+(ne+7)/8+(nt+31)/32+nb*4)return 2;
    w=read_word(in,count,read,error);for(unsigned a=0;a<3;++a){origin[a]=real(lane(w,a));spacing[a]=real(lane(w,a+3));}
    min_spacing=real(lane(w,6));resolution=real(lane(w,7));
    for(unsigned j=0;j<2;++j){w=read_word(in,count,read,error);for(unsigned k=0;k<8;++k)if(j*8+k<9)direction[(j*8+k)/3][(j*8+k)%3]=real(lane(w,k));if(j==1)token=lane(w,7);}
    for(unsigned i=0;i<nn;++i){
#pragma HLS PIPELINE
        w=read_word(in,count,read,error);for(unsigned a=0;a<3;++a)nodes[a][i]=real(lane(w,a));
        radii[i]=real(lane(w,3));component[i]=uint16_t(lane(w,4));head[i]=65535;
    }
    for(unsigned start=0;start<ne;start+=8){w=read_word(in,count,read,error);for(unsigned k=0;k<8;++k)if(start+k<ne){
        uint64_t e=lane(w,k);unsigned u=uint32_t(e),v=uint32_t(e>>32),i=start+k;
        if(u>=nn||v>=nn||u==v){error|=2;u=v=0;}
        edge_u[i]=uint16_t(u);edge_v[i]=uint16_t(v);
        neighbor[2*i]=uint16_t(v);link[2*i]=head[u];head[u]=uint16_t(2*i);
        neighbor[2*i+1]=uint16_t(u);link[2*i+1]=head[v];head[v]=uint16_t(2*i+1);
    }}
    for(unsigned start=0;start<nt;start+=32){
#pragma HLS PIPELINE
        w=read_word(in,count,read,error);for(unsigned k=0;k<8;++k){
#pragma HLS UNROLL
            if(start/4+k<(nt+3)/4)tilemap[start/4+k]=lane(w,k);
        }
    }
    for(unsigned b=0;b<nb;++b)for(unsigned z=0;z<4;++z){
#pragma HLS PIPELINE
        w=read_word(in,count,read,error);
        for(unsigned hy=0;hy<2;++hy)for(unsigned yp=0;yp<2;++yp)for(unsigned xp=0;xp<2;++xp){
#pragma HLS UNROLL
            unsigned j=(2*hy+yp)*4+xp;uint64_t low=lane(w,j/2)>>(32*(j&1)),high=lane(w,(j+2)/2)>>(32*((j+2)&1));
            values[xp+2*yp+4*(z&1)][b*4+(z>>1)*2+hy]=(low&0xffffffffULL)|(high<<32);
        }
    }
    loaded=!error;return error;
}

static double original[ROUTE_POINTS][3],candidate[ROUTE_POINTS][3],scratch[ROUTE_POINTS][3];
static double arcs[ROUTE_POINTS];static float path_radii[ROUTE_POINTS];
static double audit_radius[ROUTE_POINTS],audit_minimum[ROUTE_POINTS],audit_minimum_bend[ROUTE_POINTS],audit_spare[ROUTE_POINTS];
static uint8_t audit_states[ROUTE_POINTS];
static float smooth_radii[ROUTE_POINTS];static bool path_valid[ROUTE_POINTS],smooth_valid[ROUTE_POINTS];
static uint16_t parents[ROUTE_NODES],queue[ROUTE_NODES],ids[ROUTE_NODES];
static bool allowed[ROUTE_NODES];static double gaps[ROUTE_NODES];
static double target_buffer[ROUTE_TARGET_LANES][256/ROUTE_TARGET_LANES][3];

static void nearest_targets(Stream<Packet>& in,unsigned count,unsigned& read,unsigned& error,unsigned targets){
    for(unsigned i=0;i<nn;++i)gaps[i]=1e300;
    for(unsigned start=0;start<targets;start+=256){unsigned n=std::min(256U,targets-start);
        for(unsigned j=0;j<n;j+=2){Word w=read_word(in,count,read,error);for(unsigned k=0;k<2;++k)if(j+k<n)
            for(unsigned a=0;a<3;++a)target_buffer[(j+k)%ROUTE_TARGET_LANES][(j+k)/ROUTE_TARGET_LANES][a]=real(lane(w,k*3+a));}
        for(unsigned i=0;i<nn;++i){double lane_min[ROUTE_TARGET_LANES];
#pragma HLS ARRAY_PARTITION variable=lane_min complete
            for(unsigned lane_id=0;lane_id<ROUTE_TARGET_LANES;++lane_id)lane_min[lane_id]=gaps[i];
            for(unsigned block=0;block<(n+ROUTE_TARGET_LANES-1)/ROUTE_TARGET_LANES;++block){
#pragma HLS PIPELINE
                for(unsigned lane_id=0;lane_id<ROUTE_TARGET_LANES;++lane_id){
#pragma HLS UNROLL
                    if(block*ROUTE_TARGET_LANES+lane_id<n){double sum=0;
                        for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
                            double d=nodes[a][i]-target_buffer[lane_id][block][a];sum+=d*d;
                        }
                        if(sum<lane_min[lane_id])lane_min[lane_id]=sum;
                    }
                }
            }
            double best=gaps[i];for(unsigned l=0;l<ROUTE_TARGET_LANES;++l)if(lane_min[l]<best)best=lane_min[l];gaps[i]=best;
        }
    }
}
// Bounds are checked before narrowing. 13 bits retain the terminal count 4096.
#ifdef NAV_NATIVE
using DenseIndex=uint16_t;
#else
using DenseIndex=ap_uint<13>;
#endif
static unsigned dense(const double source[ROUTE_POINTS][3],unsigned n,double step,double dest[ROUTE_POINTS][3],unsigned& error){
#pragma HLS INLINE
    if(!n)return 0;
    if(n>ROUTE_POINTS||!std::isfinite(step)||step<=0){error|=4;return 0;}
    DenseIndex out=1;for(unsigned a=0;a<3;++a)dest[0][a]=source[0][a];
    for(DenseIndex i=0;unsigned(i)+1<n;++i){
        double requested=std::ceil(distance(source[i],source[unsigned(i)+1])/step);
        if(!std::isfinite(requested)||requested>=double(ROUTE_POINTS)){error|=4;return 0;}
        DenseIndex parts=std::max(1U,unsigned(requested));
        if(unsigned(parts)>ROUTE_POINTS-unsigned(out)){error|=4;return 0;}
        for(DenseIndex j=1;j<=parts;++j){
#pragma HLS PIPELINE II=4
            for(unsigned a=0;a<3;++a)dest[out][a]=j==parts?source[unsigned(i)+1][a]:source[i][a]+double(j)/double(parts)*(source[unsigned(i)+1][a]-source[i][a]);++out;
        }
    }return out;
}
static bool all_valid(unsigned which,unsigned n,double required,double margin){
#pragma HLS INLINE
    bool answer=true;
    for(unsigned i=0;i<n;++i){
        double p[3];for(unsigned a=0;a<3;++a)p[a]=which?scratch[i][a]:original[i][a];
        float radius;bool inside=query_field(p[0],p[1],p[2],radius);
        bool good=inside&&double(radius)-margin+1e-5>=required;answer&=good;
        if(which){smooth_radii[i]=radius;smooth_valid[i]=good;}
        else{path_radii[i]=radius;path_valid[i]=good;}
    }return answer;
}
static void interpolate(const double p[ROUTE_POINTS][3],unsigned n,double s,double value[3],unsigned& cursor,bool monotonic){
#pragma HLS INLINE off
    unsigned lo=0,hi=n-1;
    if(monotonic){lo=cursor;while(lo<hi&&arcs[lo]<s)++lo;cursor=lo;}
    else while(lo<hi){unsigned m=(lo+hi)/2;if(arcs[m]<s)lo=m+1;else hi=m;}
    if(!lo){for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
value[a]=p[0][a];}return;}
    double f=(s-arcs[lo-1])/(arcs[lo]-arcs[lo-1]);
    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
value[a]=p[lo-1][a]+f*(p[lo][a]-p[lo-1][a]);}
}
static void normalize(double p[3],double magnitude){double reciprocal=1./magnitude;for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
p[a]*=reciprocal;}}

extern "C" void nav_route(Stream<Packet>& input,Stream<Packet>& output,uint32_t operation,uint32_t input_count,uint32_t output_count,uint32_t& status){
#pragma HLS ALLOCATION instances=query_field limit=1 function
#pragma HLS ALLOCATION instances=radius_index limit=1 function
#pragma HLS ALLOCATION instances=index_point limit=1 function
#pragma HLS ALLOCATION instances=norm3_scalar limit=1 function
#pragma HLS ALLOCATION instances=dadd limit=3 operation
#pragma HLS ALLOCATION instances=dsub limit=3 operation
#pragma HLS ALLOCATION instances=dmul limit=3 operation
#pragma HLS ALLOCATION instances=ddiv limit=1 operation
#pragma HLS ALLOCATION instances=dsqrt limit=1 operation
#pragma HLS INTERFACE axis port=input register_mode=both
#pragma HLS INTERFACE axis port=output register_mode=both
#pragma HLS INTERFACE s_axilite port=operation bundle=control offset=0x10
#pragma HLS INTERFACE s_axilite port=input_count bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=output_count bundle=control offset=0x20
#pragma HLS INTERFACE s_axilite port=status bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ARRAY_PARTITION variable=values complete dim=1
#pragma HLS BIND_STORAGE variable=values type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=tilemap type=ram_2p impl=uram
#pragma HLS ARRAY_PARTITION variable=nodes complete dim=1
#pragma HLS BIND_STORAGE variable=nodes type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=radii type=ram_2p impl=uram
#pragma HLS ARRAY_PARTITION variable=original complete dim=2
#pragma HLS ARRAY_PARTITION variable=candidate complete dim=2
#pragma HLS ARRAY_PARTITION variable=scratch complete dim=2
#pragma HLS BIND_STORAGE variable=original type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=candidate type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=scratch type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=arcs type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=gaps type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=path_radii type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=smooth_radii type=ram_2p impl=uram
#pragma HLS ARRAY_PARTITION variable=target_buffer complete dim=1
#pragma HLS ARRAY_PARTITION variable=target_buffer complete dim=3
#pragma HLS BIND_STORAGE variable=target_buffer type=ram_2p impl=bram
#pragma HLS BIND_STORAGE variable=audit_radius type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=audit_minimum type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=audit_minimum_bend type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=audit_spare type=ram_2p impl=uram
#pragma HLS BIND_STORAGE variable=audit_states type=ram_2p impl=bram
    unsigned read=0,error=0;
    // Diagnostic raw-route audit for CPU/PL comparisons. The production
    // planner uses operation 1 and the already verified route buffers.
    if(operation==2){
        Word h=read_word(input,input_count,read,error);unsigned n=unsigned(lane(h,1));
        double window=real(lane(h,2)),audit_margin=real(lane(h,3)),audit_required=real(lane(h,4)),threshold=real(lane(h,5));
        if(lane(h,0)!=AUDIT_QUERY_TAG||lane(h,1)>ROUTE_POINTS||input_count!=n+1||output_count!=ROUTE_OUTPUT_WORDS||!std::isfinite(window)||window<0||!std::isfinite(audit_margin)||audit_margin<0||!std::isfinite(audit_required)||audit_required<0||!std::isfinite(threshold)||threshold<0)error|=2;
        if(!error)for(unsigned i=0;i<n;++i){
#pragma HLS PIPELINE II=1
            Word w=read_word(input,input_count,read,error);
            for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
                original[i][a]=real(lane(w,a));
                if(!std::isfinite(original[i][a]))error|=2;
            }
            arcs[i]=real(lane(w,3));double radius=real(lane(w,4));path_radii[i]=float(radius);
            if(!std::isfinite(arcs[i])||(i&&arcs[i]<arcs[i-1])||!std::isfinite(radius)||radius<0||radius>double(std::numeric_limits<float>::max()))error|=2;
        }
        while(read<input_count)read_word(input,input_count,read,error);
        if(error)n=0;
        audit_statistics(original,arcs,path_radii,n,window,audit_margin,audit_required,threshold,audit_radius,audit_minimum,audit_minimum_bend,audit_spare,audit_states);
        for(unsigned i=0;i<n+1;++i){Word w{};
            if(!i){lane(w,0,error);lane(w,1,n);lane(w,2,AUDIT_QUERY_TAG);}
            else{unsigned k=i-1;lane(w,0,bits(audit_radius[k]));lane(w,1,bits(audit_minimum[k]));lane(w,2,bits(audit_minimum_bend[k]));lane(w,3,bits(audit_spare[k]));lane(w,4,audit_state_bits(audit_states[k]));}
            output.write(packet(w,i,n+1));
        }
        status=error;return;
    }
    if(operation==0){error=load_scene(input,input_count,read,error);
        while(read<input_count)read_word(input,input_count,read,error);
        if(output_count!=1)error|=1;
        for(unsigned i=0;i<output_count;++i){Word w{};lane(w,0,error);lane(w,1,token);output.write(packet(w,i,output_count));}
        status=error;return;
    }
    Word command=read_word(input,input_count,read,error),parameters=read_word(input,input_count,read,error);
    unsigned targets=unsigned(lane(command,2)),kind=unsigned(lane(command,3));bool smooth=bool(lane(command,4));
    double diameter=real(lane(parameters,0)),safety=real(lane(parameters,1)),sample=real(lane(parameters,2)),lookahead=real(lane(parameters,4));
    bool audited=lane(command,6)==AUDIT_QUERY_TAG;
    double bend_limit=real(lane(parameters,5)),hud_window=real(lane(parameters,6));
    if(audited&&(!std::isfinite(bend_limit)||bend_limit<0||!std::isfinite(hud_window)||hud_window<0))error|=2;
    double required=diameter*.5+safety,margin=required>0?resolution:0,step=std::min(sample,min_spacing*.25);
    if(operation!=1||!loaded||lane(command,0)!=ROUTE_QUERY_MAGIC||lane(command,1)!=token||!targets||targets>65536||input_count!=2+2*((targets+1)/2)||output_count!=ROUTE_OUTPUT_WORDS||diameter<0||safety<0||sample<=0||lookahead<=0)error|=2;
    unsigned desired=0,end=0,reason=0,reachable=0,nids=0,npoints=0;bool smoothed=false,cache_hit=false,raw_scanned=false;double closest=0,final_gap=0,min_radius=0;
    if(!error){
        nearest_targets(input,input_count,read,error,targets);
        for(unsigned i=1;i<nn;++i)if(gaps[i]<gaps[desired])desired=i;closest=std::sqrt(gaps[desired]);
        if(kind==1&&closest>5)error|=8;
        bool root_ok=std::max(0.,radii[root]-margin)+1e-6>=required;
        cache_hit=edge_cache_valid&&edge_cache_step==step;
        if(root_ok&&!error&&!cache_hit){
            double max_length=0;
            for(unsigned e=0;e<ne;++e){double a[3],b[3];node_point(edge_u[e],a);node_point(edge_v[e],b);max_length=std::max(max_length,distance(a,b));}
            unsigned subdivisions=std::max(1U,unsigned(std::ceil(max_length/step)));
            if(subdivisions>4096)error|=4;
            if(!error)for(unsigned e=0;e<ne;++e){
                double a[3],b[3],p[3];node_point(edge_u[e],a);node_point(edge_v[e],b);
                bool inside=true;float minimum=1e30f;
                for(unsigned j=0;j<=subdivisions;++j){
                    for(unsigned k=0;k<3;++k)p[k]=a[k]+double(j)/subdivisions*(b[k]-a[k]);
                    float radius;inside&=query_field(p[0],p[1],p[2],radius);minimum=std::min(minimum,radius);
                }
                edge_inside_cache[e]=inside;edge_min_radius_cache[e]=minimum;
            }
            edge_cache_valid=!error;edge_cache_step=step;
        }
        if(!error)for(unsigned e=0;e<ne;++e){
            unsigned u=edge_u[e],v=edge_v[e];double adjusted=std::max(0.,std::min(radii[u],radii[v])-margin);
            allowed[e]=root_ok&&adjusted+1e-6>=required&&edge_inside_cache[e]&&double(edge_min_radius_cache[e])-margin+1e-5>=required;
        }
        for(unsigned i=0;i<nn;++i)parents[i]=65535;
        unsigned front=0,back=0;if(root_ok&&!error){parents[root]=uint16_t(root);queue[back++]=uint16_t(root);}
        while(front<back){unsigned u=queue[front++];++reachable;
            for(unsigned j=head[u];j!=65535;j=link[j]){unsigned v=neighbor[j];
                if(allowed[j/2]&&parents[v]==65535){parents[v]=uint16_t(u);queue[back++]=uint16_t(v);}
            }
        }
        if(component[desired]!=component[root])reason=1;else if(!root_ok)reason=2;else if(parents[desired]==65535)reason=3;
        end=desired;
        if(reason){end=ROUTE_NODES;for(unsigned i=0;i<nn;++i)if(parents[i]!=65535&&(end==ROUTE_NODES||gaps[i]<gaps[end]))end=i;}
        if(end<nn&&!error){unsigned u=end;while(nids<nn){ids[nids++]=uint16_t(u);if(u==root)break;u=parents[u];}
            for(unsigned i=0;i<nids/2;++i){uint16_t t=ids[i];ids[i]=ids[nids-1-i];ids[nids-1-i]=t;}
            for(unsigned i=0;i<nids;++i)node_point(ids[i],candidate[i]);npoints=dense(candidate,nids,step,original,error);
        }
        bool raw_good=false;
        if(smooth&&npoints>2&&!error){raw_good=all_valid(0,npoints,required,margin);raw_scanned=true;}
        if(smooth&&npoints>2&&!error&&raw_good){
            for(unsigned i=0;i<npoints;++i)for(unsigned a=0;a<3;++a)candidate[i][a]=original[i][a];
            for(unsigned iteration=0;iteration<8;++iteration){
                for(unsigned i=0;i<npoints;++i){
#pragma HLS PIPELINE II=2
                    double delta[3],value[3];
#pragma HLS ARRAY_PARTITION variable=delta complete
#pragma HLS ARRAY_PARTITION variable=value complete
                    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
                        value[a]=candidate[i][a];if(i&&i+1<npoints)value[a]+=.2*(.5*(candidate[i-1][a]+candidate[i+1][a])-candidate[i][a]);delta[a]=value[a]-original[i][a];}
                    double magnitude=norm3(delta),scale=magnitude>min_spacing*.15?min_spacing*.15/magnitude:1;
                    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
                        scratch[i][a]=original[i][a]+delta[a]*scale;}
                }
                for(unsigned i=0;i<npoints;++i){
#pragma HLS PIPELINE II=1
                    for(unsigned a=0;a<3;++a)candidate[i][a]=scratch[i][a];}
            }
            unsigned tested=dense(candidate,npoints,step,scratch,error);
            if(!error&&all_valid(1,tested,required,margin)){npoints=tested;for(unsigned i=0;i<npoints;++i)for(unsigned a=0;a<3;++a)original[i][a]=scratch[i][a];smoothed=true;}
        }
        if(!error&&!smoothed&&!raw_scanned)all_valid(0,npoints,required,margin);
        if(!error)for(unsigned i=0;i<npoints;++i)if(!(smoothed?smooth_valid[i]:path_valid[i])){npoints=i;reason=4;break;}
        if(!error)for(unsigned i=0;i<npoints;++i){
            if(smoothed)path_radii[i]=smooth_radii[i];
            if(i==0||path_radii[i]<min_radius)min_radius=path_radii[i];arcs[i]=i?arcs[i-1]+distance(original[i-1],original[i]):0;
        }
        double final[3]{};if(npoints)for(unsigned a=0;a<3;++a)final[a]=original[npoints-1][a];double best=1e300;
        for(unsigned start=0;start<targets;start+=2){Word w=read_word(input,input_count,read,error);
            for(unsigned j=0;j<2;++j)if(start+j<targets){double squared=0;for(unsigned a=0;a<3;++a){double d=final[a]-real(lane(w,j*3+a));squared+=d*d;}if(squared<best)best=squared;}
        }final_gap=npoints?std::sqrt(best):0;
    }
    while(read<input_count)read_word(input,input_count,read,error);
    if(audited&&!error){
        audit_statistics(original,arcs,path_radii,npoints,hud_window,margin,required,bend_limit,audit_radius,audit_minimum,audit_minimum_bend,audit_spare,audit_states);
    }
    double previous[3]={0,0,1};unsigned sent=0,ids_words=(nids+7)/8,ahead_cursor=0;
    unsigned emitted=2+ids_words+npoints*2;
    for(unsigned i=0;i<emitted;++i){Word w{};
        if(i==0){lane(w,0,error);lane(w,1,npoints);lane(w,2,nids);lane(w,3,desired);lane(w,4,end);lane(w,5,reason);lane(w,6,reachable);lane(w,7,smoothed);}
        else if(i==1){lane(w,0,bits(npoints?arcs[npoints-1]:0));lane(w,1,bits(min_radius));lane(w,2,bits(closest));lane(w,3,bits(final_gap));lane(w,4,bits(required));lane(w,5,bits(margin));lane(w,6,bits(audited?3.:2.));lane(w,7,bits(double(cache_hit)));}
        else if(i<2+ids_words){for(unsigned j=0;j<8;++j){unsigned k=(i-2)*8+j;lane(w,j,k<nids?ids[k]:65535);}}
        else{unsigned k=(i-2-ids_words)/2;bool first=((i-2-ids_words)&1)==0;
            if(k<npoints&&!error){
                if(first){double ahead[3],behind[3],forward[3];
                    if(npoints>1){interpolate(original,npoints,std::min(arcs[npoints-1],arcs[k]+lookahead),ahead,ahead_cursor,true);
                        for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
forward[a]=ahead[a]-original[k][a];}
                        double forward_norm=norm3(forward);
                        if(forward_norm<1e-9){unsigned behind_cursor=0;interpolate(original,npoints,std::max(0.,arcs[k]-lookahead),behind,behind_cursor,false);for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
forward[a]=original[k][a]-behind[a];}forward_norm=norm3(forward);}
                        normalize(forward,forward_norm);double d=0;for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
d+=previous[a]*forward[a];}double up[3];for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
up[a]=previous[a]-d*forward[a];}
                        double up_norm=norm3(up);
                        if(up_norm<1e-6){unsigned axis=0;for(unsigned a=1;a<3;++a)if(std::abs(forward[a])<std::abs(forward[axis]))axis=a;for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
up[a]=(a==axis?1.:0.)-forward[axis]*forward[a];}up_norm=norm3(up);}
                        normalize(up,up_norm);d=0;for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
d+=up[a]*previous[a];}for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
previous[a]=d<0?-up[a]:up[a];}
                    }else for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
forward[a]=0;}
                    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
lane(w,a,bits(original[k][a]));lane(w,a+5,bits(forward[a]));}lane(w,3,bits(arcs[k]));lane(w,4,bits(path_radii[k]));
                }else{
                    for(unsigned a=0;a<3;++a){
#pragma HLS UNROLL
                        lane(w,a,bits(previous[a]));
                    }
                    if(audited){
                        lane(w,3,bits(audit_radius[k]));lane(w,4,bits(audit_minimum[k]));
                        lane(w,5,bits(audit_minimum_bend[k]));lane(w,6,bits(audit_spare[k]));
                        lane(w,7,audit_state_bits(audit_states[k]));
                    }
                }
            }
        }
        output.write(packet(w,sent++,emitted));
    }status=error;
}

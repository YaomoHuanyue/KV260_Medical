#include "mc_axis.hpp"
#include "binary_lewiner.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>

static unsigned cases=0;
static void require(bool ok) {if(!ok)throw std::runtime_error("MC AXIS test mismatch");}
static std::vector<uint64_t> reference(const std::vector<uint8_t>& a,unsigned nx,unsigned ny,unsigned nz) {
    std::vector<uint64_t> words;
    for(unsigned z=0;z+1<nz;++z)for(unsigned y=0;y+1<ny;++y)for(unsigned x=0;x+1<nx;++x) {
        unsigned code=0;
        for(unsigned dz=0;dz<2;++dz)for(unsigned dy=0;dy<2;++dy)for(unsigned dx=0;dx<2;++dx)
            code|=(a[((z+dz)*ny+y+dy)*nx+x+dx]&1)<<(dz*4+dy*2+dx);
        for(unsigned i=0;i<3*MC_COUNTS[code];++i) {
            const uint8_t o=MC_VERTICES[code][i];
            words.push_back(uint64_t(x*2+(o&3))|(uint64_t(y*2+((o>>2)&3))<<16)|
                (uint64_t(z*2+((o>>4)&3))<<32));
        }
    }
    return words;
}

static void run(const std::vector<uint8_t>& a,unsigned nx,unsigned ny,unsigned nz,
    unsigned capacity,unsigned mode,unsigned expected,int declared=-1,unsigned mutation=0,unsigned at=0) {
    const unsigned inputs=declared<0?unsigned((a.size()+63)/64):unsigned(declared);
    McAxisStream input,output;
    for(unsigned i=0;i<inputs;++i) {
        McAxisWord w{};w.data=0;w.keep=w.strb=~uint64_t(0);w.user=i==0;w.last=i+1==inputs;
        for(unsigned b=0;b<64;++b)w.data.range(b*8+7,b*8)=i*64+b<a.size()?a[i*64+b]:0xa6;
        if(i==at) {
            if(mutation&1)w.keep=uint64_t(w.keep)^1;
            if(mutation&2)w.strb=uint64_t(w.strb)^1;
            if(mutation&4)w.user=!bool(w.user);
            if(mutation&8)w.last=!bool(w.last);
        }
        input.write(w);
    }
    unsigned errors=0;
    if(nx<2||ny<2||nz<2||nx>512||ny>512||nz>512)errors|=mc_axis::BAD_DIMENSIONS;
    if(mode>1)errors|=mc_axis::BAD_MODE;
    if(expected>mc_axis::MAX_TRIANGLES)errors|=mc_axis::EXPECTED_LIMIT;
    const bool bad=errors!=0;
    std::vector<uint64_t> all;
    if(!bad) {
        std::vector<uint8_t> volume(nx*ny*nz,0);
        for(unsigned i=0;i<volume.size()&&i<inputs*64&&i<a.size();++i)volume[i]=a[i];
        for(uint8_t v:volume)if(v>1)errors|=mc_axis::NON_BINARY;
        all=reference(volume,nx,ny,nz);
        if(inputs!=(volume.size()+63)/64)errors|=mc_axis::FRAME_LENGTH;
        if(!mode) {
            if(all.size()/3>capacity)errors|=mc_axis::OVERFLOW;
            if(all.size()/3!=expected)errors|=mc_axis::COUNT_MISMATCH;
        }
    }
    errors|=mutation*32;
    const unsigned target=mode||bad?0:3*(capacity<expected?capacity:expected);
    const unsigned beats=(target+7)/8+1;
    const unsigned stored=mode||bad?0:(all.size()<target?unsigned(all.size()):target);
    binary_mc_axis(input,output,nx,ny,nz,capacity,mode,expected,inputs);
    require(input.empty());
    for(unsigned i=0;i<beats;++i) {
        require(!output.empty());const McAxisWord w=output.read();
        require(uint64_t(w.keep)==~uint64_t(0)&&uint64_t(w.strb)==~uint64_t(0));
        require(bool(w.user)==(i==0)&&bool(w.last)==(i+1==beats));
        if(i+1==beats) {
            const uint32_t fields[16]={mc_axis::MAGIC,1,errors,unsigned(all.size()/3),stored/3,nx,ny,nz,
                inputs,beats,capacity,mode,expected,stored,0,0};
            for(unsigned lane=0;lane<16;++lane)
                require(uint32_t(w.data.range(32*lane+31,32*lane))==fields[lane]);
        }else {
            for(unsigned lane=0;lane<8;++lane) {
                const unsigned index=i*8+lane;
                require(uint64_t(w.data.range(64*lane+63,64*lane))==(index<stored?all[index]:0));
            }
        }
    }
    require(output.empty());
    std::cout<<"PASS MC_AXIS_CASE "<<++cases<<"\n";
}

int main() {
    for(unsigned code=0;code<256;++code) {
        std::vector<uint8_t> a(8);for(unsigned i=0;i<8;++i)a[i]=(code>>i)&1;
        const unsigned n=MC_COUNTS[code];
        run(a,2,2,2,0,1,0);run(a,2,2,2,n,0,n);
        if(n)run(a,2,2,2,n-1,0,n);
    }
    const unsigned shapes[][3]={{3,7,5},{17,2,2},{129,5,3},{131,4,3},{3,512,2},{512,2,3},{9,11,7}};
    uint32_t rng=20261018;
    for(const auto& shape:shapes) {
        std::vector<uint8_t> a(shape[0]*shape[1]*shape[2]);
        for(auto& v:a){rng=rng*1664525u+1013904223u;v=(rng>>16)&1;}
        const unsigned n=unsigned(reference(a,shape[0],shape[1],shape[2]).size()/3);
        run(a,shape[0],shape[1],shape[2],0,1,0);run(a,shape[0],shape[1],shape[2],n,0,n);
    }
    std::vector<uint8_t> a(5*7*9);
    for(auto& v:a){rng=rng*1664525u+1013904223u;v=(rng>>16)&1;}
    const unsigned n=unsigned(reference(a,9,7,5).size()/3);
    for(unsigned flags=1;flags<16;++flags)for(unsigned at:{0u,2u,4u})run(a,9,7,5,n,0,n,-1,flags,at);
    for(unsigned expected:{0u,n-1,n+1,n+8})run(a,9,7,5,expected,0,expected);
    for(unsigned declared:{0u,1u,4u,6u,7u})run(a,9,7,5,0,1,0,int(declared));
    run(a,1,3,3,0,1,0,2);run(a,513,2,2,0,1,0,2);run(a,2,2,2,0,2,0,2);
    run(a,2,2,2,0,0,mc_axis::MAX_TRIANGLES+1,2);run(a,0,0,0,0,3,0,2);
    a[3]=2;a[100]=3;run(a,9,7,5,0,1,0);
    const unsigned invalid_n=unsigned(reference(a,9,7,5).size()/3);run(a,9,7,5,invalid_n,0,invalid_n);
    for(uint8_t value:{uint8_t(0),uint8_t(1)}) {
        std::vector<uint8_t> empty(9*11*13,value);
        run(empty,13,11,9,0,1,0);run(empty,13,11,9,0,0,0);
    }
    std::cout<<"PASS MC_AXIS_ALL "<<cases<<"\n";
}

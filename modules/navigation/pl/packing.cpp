// CPU-side layout conversion. Eight neighboring lines are handled together so
// the Y/Z transpose keeps adjacent X voxels in the same cache transaction.
#include <cstdint>
#include <algorithm>
#ifdef _WIN32
#define NAV_EXPORT __declspec(dllexport)
#else
#define NAV_EXPORT
#endif
template<bool unpack> static void convert(const uint64_t* source,uint64_t* destination,
    unsigned nz,unsigned ny,unsigned nx,unsigned axis){
    unsigned dims[]={nz,ny,nx},length=dims[axis];
    uint64_t lines=uint64_t(nz)*ny*nx/length,groups=(lines+7)/8;
    uint64_t stride=axis==2?1:axis==1?nx:uint64_t(ny)*nx;
    for(uint64_t group=0;group<groups;++group){
        uint64_t base[8];unsigned valid=unsigned(std::min<uint64_t>(8,lines-group*8));
        for(unsigned lane=0;lane<valid;++lane){
            uint64_t line=group*8+lane;
            base[lane]=axis==2?line*nx:axis==1?(line/nx)*ny*nx+line%nx:line;
        }
        for(unsigned q=0;q<length;++q){
            uint64_t packed=(group*length+q)*8;
            for(unsigned lane=0;lane<valid;++lane){
                uint64_t voxel=base[lane]+q*stride;
                if(unpack)destination[voxel]=source[packed+lane];else destination[packed+lane]=source[voxel];
            }
            if(!unpack)for(unsigned lane=valid;lane<8;++lane)destination[packed+lane]=0;
        }
    }
}
extern "C" NAV_EXPORT void nav_pack(const uint64_t* source,uint64_t* destination,unsigned nz,unsigned ny,unsigned nx,unsigned axis){convert<false>(source,destination,nz,ny,nx,axis);}
extern "C" NAV_EXPORT void nav_unpack(const uint64_t* source,uint64_t* destination,unsigned nz,unsigned ny,unsigned nx,unsigned axis){convert<true>(source,destination,nz,ny,nx,axis);}

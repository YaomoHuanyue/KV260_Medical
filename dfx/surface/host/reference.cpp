// Independent dense-field ARM reference, up to four CPU cores.
#include <cstdint>
#include <vector>
#include <algorithm>
#include <omp.h>
static void sample(const int16_t* field,const uint8_t* target,int nx,int ny,int nz,
                   int xq,int yq,int zq,int& value,unsigned& selected){
 int x=xq>>16,y=yq>>16,z=zq>>16;
 unsigned fx=(unsigned(xq)>>8)&255,fy=(unsigned(yq)>>8)&255,fz=(unsigned(zq)>>8)&255;
 int a[8];unsigned b[8];
 for(unsigned k=0;k<8;++k){int xx=x+(k&1),yy=y+((k>>1)&1),zz=z+(k>>2);a[k]=-128;b[k]=0;
  if(xx>=0&&xx<nx&&yy>=0&&yy<ny&&zz>=0&&zz<nz){unsigned i=(zz*ny+yy)*nx+xx;a[k]=field[i];b[k]=target[i];}
 }
 int ax[4];unsigned bx[4];
 for(int k=0;k<4;++k){ax[k]=a[k*2]*int(256-fx)+a[k*2+1]*int(fx);bx[k]=b[k*2]*(256-fx)+b[k*2+1]*fx;}
 int lo=(ax[0]*int(256-fy)+ax[1]*int(fy))>>8,hi=(ax[2]*int(256-fy)+ax[3]*int(fy))>>8;
 value=(lo*int(256-fz)+hi*int(fz))>>8;
 unsigned bl=bx[0]*(256-fy)+bx[1]*fy,bh=bx[2]*(256-fy)+bx[3]*fy;
 selected=(bl*(256-fz)+bh*fz)>>8;
}
extern "C" void surface_reference(const int16_t* field,const uint8_t* target,int nx,int ny,int nz,const int32_t* p,const int32_t* matrix,uint64_t* output,int threads){
 int width=p[0],height=p[1],count=width*height;threads=std::max(1,std::min(4,threads));std::vector<uint32_t> raw(count),normals(count,0);
 #pragma omp parallel for num_threads(threads) schedule(dynamic,64)
 for(int i=0;i<count;++i){
  int px=i%width,py=i/width,dx=p[7]+px*p[10]+py*p[13],dy=p[8]+px*p[11]+py*p[14],dz=p[9]+px*p[12]+py*p[15];
  int x=p[4],y=p[5],z=p[6];unsigned depth=65535;bool inside=false,reached=false;
  for(int step=0;step<=p[2];++step){
   int value;unsigned selected;sample(field,target,nx,ny,nz,x,y,z,value,selected);
   bool state=value>0;
   if(!step)inside=state;
   else if(state!=inside){
    unsigned low=0,high=64;
    for(int k=0;k<6;++k){unsigned middle=(low+high)>>1;int v;unsigned s;
     sample(field,target,nx,ny,nz,x-dx+((dx*int(middle))>>6),y-dy+((dy*int(middle))>>6),z-dz+((dz*int(middle))>>6),v,s);
     if((v>0)==inside)low=middle;else high=middle;
    }
    depth=(step-1)*64+high;
    int hit[3]={x-dx+((dx*int(high))>>6),y-dy+((dy*int(high))>>6),z-dz+((dz*int(high))>>6)};
    int gradient[3];
    for(int axis=0;axis<3;++axis){
     int plus[3]={hit[0],hit[1],hit[2]},minus[3]={hit[0],hit[1],hit[2]};plus[axis]+=65536;minus[axis]-=65536;
     int pv,mv;unsigned unused;sample(field,target,nx,ny,nz,plus[0],plus[1],plus[2],pv,unused);sample(field,target,nx,ny,nz,minus[0],minus[1],minus[2],mv,unused);gradient[axis]=pv-mv;
    }
    uint32_t n=0xff000000;
    for(int row=0;row<3;++row){int64_t component=0;for(int axis=0;axis<3;++axis)component+=int64_t(gradient[axis])*matrix[row*3+axis];
     int c=int(component>>16);n|=uint32_t(128+std::max(-127,std::min(127,c)))<<(row*8);
    }
    normals[i]=n;break;
   }
   if(inside&&selected>42598)reached=true;x+=dx;y+=dy;z+=dz;
  }
  raw[i]=depth|(unsigned(reached&&inside)<<16);
 }
 std::vector<uint8_t> high5(count),low5(count),high7(count),gauss(count);
 #pragma omp parallel for num_threads(threads)
 for(int r=0;r<height;++r)for(int c=0;c<width;++c){unsigned hi=0,lo=1,outer=0,sum=0;
  for(int k=-3;k<=3;++k){unsigned v=(raw[r*width+std::max(0,std::min(width-1,c+k))]>>16)&1;outer|=v;if(k>=-2&&k<=2){hi|=v;lo&=v;}if(k>=-1&&k<=1)sum+=v*(k==0?2:1);}
  int i=r*width+c;high5[i]=hi;low5[i]=lo;high7[i]=outer;gauss[i]=sum;
 }
 #pragma omp parallel for num_threads(threads)
 for(int r=0;r<height;++r)for(int c=0;c<width;++c){unsigned hi=0,lo=1,outer=0,sum=0;
  for(int j=-3;j<=3;++j){int i=std::max(0,std::min(height-1,r+j))*width+c;outer|=high7[i];if(j>=-2&&j<=2){hi|=high5[i];lo&=low5[i];}if(j>=-1&&j<=1)sum+=gauss[i]*(j==0?2:1);}
  int i=r*width+c;unsigned edge=hi&&!lo?255:outer&&!hi?128:0;
  uint32_t normal=0;
  if((raw[i]&65535)!=65535){unsigned rgb[3]={0,0,0},weights=0;
   for(int j=-1;j<=1;++j)for(int k=-1;k<=1;++k){int index=std::max(0,std::min(height-1,r+j))*width+std::max(0,std::min(width-1,c+k));
    int difference=int(raw[index]&65535)-int(raw[i]&65535);
    if((normals[index]>>24)==255&&difference>=-128&&difference<=128){unsigned weight=(j==0?2:1)*(k==0?2:1);weights+=weight;for(int a=0;a<3;++a)rgb[a]+=((normals[index]>>(a*8))&255)*weight;}
   }
   normal=0xff000000;for(int a=0;a<3;++a)normal|=((rgb[a]+weights/2)/weights)<<(a*8);
  }
  output[i]=uint64_t((raw[i]&65535)|(((sum*255+8)/16)<<16)|(edge<<24))|(uint64_t(normal)<<32);
 }
}

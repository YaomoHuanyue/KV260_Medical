#pragma once
// Compare every available exact ordered PS path, including the existing CPU
// captures and a GPU-input path that reads colors only when PS needs them.
#include <omp.h>
#include "neon_ps.hpp"
namespace medical_render {
static uint32_t blendPixel(uint32_t carry,uint32_t source){
 uint32_t out=0xff000000,a=source>>24;
 for(unsigned shift:{0u,8u,16u})out|=((((source>>shift)&255)*a+((carry>>shift)&255)*(255-a)+127)/255)<<shift;
 return out;
}
static void fusedOrdered(const std::vector<std::vector<uint32_t>>&colors,std::vector<uint32_t>&out,unsigned threads){
 const int n=int(out.size());const int layers=int(colors.size());
 #pragma omp parallel for num_threads(threads) schedule(static)
 for(int pixel=0;pixel<n;++pixel){
  uint32_t carry=blendPixel(medical_live::background,colors[0][pixel]);
  for(int rank=layers-1;rank>0;--rank)carry=blendPixel(carry,colors[rank][pixel]);
  out[pixel]=carry;
 }
}
struct InputReadback {
 GLuint fbo=0;
 InputReadback(){glGenFramebuffers(1,&fbo);}
 ~InputReadback(){glDeleteFramebuffers(1,&fbo);}
 void read(GLuint texture,unsigned w,unsigned h,std::vector<uint32_t>&pixels){
  glBindFramebuffer(GL_FRAMEBUFFER,fbo);
  glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
  check(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE,"PS source readback FBO incomplete");
  glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data());
  check(glGetError()==GL_NO_ERROR,"PS source readback failed");
 }
};
// The PS can use the same GPU-imported BO without sampling rank planes,
// copying the carry back to GPU per batch, or doing full glReadPixels.
// Test that practical GPU-input alternative, not only cached diagnostic data.
static void sharedInputNeon(Context&context,unsigned w,unsigned h,GLuint opaque,
 const std::vector<GLuint>&textures,std::vector<uint32_t>&out,Session&session,
 medical_live::Readback&upload,medical_live::Readback&presentation,medical_live::Program&finalProgram,
 std::vector<std::vector<uint32_t>>&inputs){
 auto&shared=session.ensure(w,h);unsigned n=w*h,end=textures.size(),batch=0;
 do{
  unsigned first=end>3?end-2:1,count=end?end-first+1:0;
  if(!batch)shared.program.draw(opaque,shared.planes[0]->fbo,w,h);
  for(unsigned slot=1;slot<=count;++slot)shared.program.draw(textures[first+slot-2],shared.planes[2*slot]->fbo,w,h);
  glFinish();check(glGetError()==GL_NO_ERROR,"NEON shared source completion failed");
  check(!composite_sync(shared.handle.value,1),composite_error());
  if(!batch)std::memcpy(inputs[0].data(),shared.cpu,n*4);
  else std::swap(inputs[0],out);
  for(unsigned slot=1;slot<=count;++slot)std::memcpy(inputs[slot].data(),shared.cpu+2*slot*shared.stride,n*4);
  fusedOrderedNeon(inputs,out,4,count+1);++batch;end=count?first-1:0;
 }while(end);
 glBindTexture(GL_TEXTURE_2D,upload.texture);
 glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,out.data());
 finalProgram.draw(upload.texture,presentation.fbo,w,h);glFinish();
 check(glGetError()==GL_NO_ERROR,"NEON shared output upload failed");
}
static QJsonObject strongComparison(Context&context,unsigned w,unsigned h,GLuint opaque,
 const std::vector<GLuint>&textures,const std::vector<std::vector<uint32_t>>&cached,Session&session){
 using namespace medical_live;
 const unsigned n=w*h;constexpr unsigned backendCount=10,rounds=6;
 const char*names[] = {"PL_shared_GPU", "PS_existing_colors_fused1", "PS_existing_colors_fused4",
  "PS_GPU_readback_fused1", "PS_GPU_readback_fused4", "PS_existing_colors_NEON1", "PS_existing_colors_NEON4",
  "PS_GPU_readback_NEON1", "PS_GPU_readback_NEON4", "PS_GPU_shared_BO_NEON4"};
 std::vector<std::vector<uint32_t>>inputs(cached.size(),std::vector<uint32_t>(n));
 std::vector<std::vector<uint32_t>>sharedInputs(4,std::vector<uint32_t>(n));
 std::vector<uint32_t>out(n),sampled(n);
 auto expected=blend(std::vector<uint32_t>(n,background),cached[0]);
 for(size_t r=cached.size()-1;r;--r)expected=blend(std::move(expected),cached[r]);
 InputReadback source;Readback upload(w,h),presentation(w,h);Program program;
 std::array<std::vector<double>,backendCount>times;QJsonArray receipts;
 for(unsigned round=0;round<rounds;++round)for(unsigned position=0;position<backendCount;++position){
  unsigned backend=(round+position)%backendCount;
  double elapsed=0,readSeconds=0,blendSeconds=0,uploadSeconds=0;
  if(backend==0){
   auto result=compose(context,w,h,opaque,textures,cached,&out,session);
   elapsed=result["complete_composition_seconds"].toDouble();
   check(out==expected,"Strong comparison actual PL result differs");
  }else if(backend==9){
   auto start=Clock::now();sharedInputNeon(context,w,h,opaque,textures,out,session,upload,presentation,program,sharedInputs);elapsed=seconds(start);
   glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,sampled.data());
   check(glGetError()==GL_NO_ERROR&&sampled==expected,"PS shared-BO NEON result differs");
  }else{
   auto start=Clock::now(),part=start;
   bool readsGPU=backend==3||backend==4||backend==7||backend==8;
   unsigned threads=(backend==2||backend==4||backend==6||backend==8)?4:1;
   if(readsGPU){
    source.read(opaque,w,h,inputs[0]);
    for(size_t r=0;r<textures.size();++r)source.read(textures[r],w,h,inputs[r+1]);
    readSeconds=seconds(part);part=Clock::now();
   }
   if(backend>=5)fusedOrderedNeon(readsGPU?inputs:cached,out,threads);
   else fusedOrdered(readsGPU?inputs:cached,out,threads);
   blendSeconds=seconds(part);part=Clock::now();
   glBindTexture(GL_TEXTURE_2D,upload.texture);
   glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,out.data());
   program.draw(upload.texture,presentation.fbo,w,h);glFinish();
   check(glGetError()==GL_NO_ERROR,"Strong PS output upload/completion failed");
   uploadSeconds=seconds(part);elapsed=seconds(start);
   glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,sampled.data());
   check(glGetError()==GL_NO_ERROR&&sampled==expected,"Strong PS GPU-sampled output differs");
   if(readsGPU)check(inputs==cached,"GPU source colors differ from original captures");
  }
  if(round)times[backend].push_back(elapsed);
  receipts.append(QJsonObject{{"round",int(round)},{"backend",names[backend]},
   {"timed",round>0},{"complete_seconds",elapsed},{"source_readback_seconds",readSeconds},
   {"blend_seconds",blendSeconds},{"upload_and_GPU_complete_seconds",uploadSeconds},{"all_pixels_exact",true}});
 }
 QJsonObject medians;for(unsigned i=0;i<backendCount;++i){
  auto values=times[i];std::sort(values.begin(),values.end());medians[names[i]]=values[values.size()/2];
 }
 double pl=medians[names[0]].toDouble();
 double existing=1e30,gpuOnly=1e30;const char*existingName=nullptr,*gpuName=nullptr;
 for(unsigned i:{1u,2u,5u,6u})if(medians[names[i]].toDouble()<existing){existing=medians[names[i]].toDouble();existingName=names[i];}
 for(unsigned i:{3u,4u,7u,8u,9u})if(medians[names[i]].toDouble()<gpuOnly){gpuOnly=medians[names[i]].toDouble();gpuName=names[i];}
 return {{"status","passed_exact_fused_PS_GPU_completion_comparison"},{"frames",int(backendCount*rounds)},
  {"backend_median_seconds",medians},{"trials",receipts},{"PL_seconds",pl},
  {"best_existing_CPU_colors_PS_seconds",existing},{"best_GPU_input_PS_seconds",gpuOnly},
  {"best_existing_CPU_colors_PS_backend",existingName},{"best_GPU_input_PS_backend",gpuName},
  {"existing_colors_PS_over_PL",existing/pl},{"GPU_input_PS_over_PL",gpuOnly/pl},
  {"diagnostic_run_reads_all_color_layers",true},{"production_worker_reads_all_color_layers",false},{"common_geometry_excluded",true},
  {"GPU_completion_included",true},{"validation_and_capture_IO_excluded",true},
  {"full_original_geometry",true},{"HDMI_UI_integration",false},
  {"interpretation","Existing-color baseline applies to diagnostic CPU captures. Production keeps colors on GPU; its PS alternatives include GPU readback and shared-BO NEON, with all copies and GPU completion timed."}};
}
}

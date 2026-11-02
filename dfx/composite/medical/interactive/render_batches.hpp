#pragma once
// Reuse the tested shared-image primitives, with a single actual C7 pass.
// This candidate is separate from archived paired benchmark implementations.
#include "../shared_batches.hpp"
namespace medical_render {
struct SharedFrame {
 // Member order keeps the BO alive until all imported GPU images are released.
 medical_live::Handle handle;
 unsigned width,height;
 size_t strideBytes,stride,allocation;
 uint32_t*cpu=nullptr;
 std::vector<std::unique_ptr<Plane>>planes;
 medical_live::Program program;
 medical_live::Readback output;
 SharedFrame(Context&context,unsigned w,unsigned h):handle(w,h),width(w),height(h),
  strideBytes(composite_stride_bytes(handle.value)),stride(strideBytes/4),
  allocation(composite_allocation_bytes(handle.value)),output(w,h){
  int fd=composite_export_fd(handle.value);check(fd>=0,composite_error());
  struct Fd{int value;~Fd(){close(value);}}sharedFd{fd};
  for(unsigned p=0;p<9;++p)planes.emplace_back(new Plane(context.display,fd,w,h,p*strideBytes));
  cpu=static_cast<uint32_t*>(composite_map(handle.value));check(cpu,"Shared CPU map failed");
 }
 ~SharedFrame(){glFinish();}
};
struct Session {
 Context&context;std::unique_ptr<SharedFrame>frame;unsigned allocations=0;
 explicit Session(Context&c):context(c){}
 SharedFrame&ensure(unsigned w,unsigned h){
  if(!frame||frame->width!=w||frame->height!=h){
   close();frame.reset(new SharedFrame(context,w,h));++allocations;
  }
  return *frame;
 }
 void close(){
  if(frame){glFinish();check(!composite_select(frame->handle.value,"scope"),composite_error());frame.reset();}
 }
};
static QJsonObject compose(Context&context,unsigned w,unsigned h,GLuint opaque,
 const std::vector<GLuint>&layers,const std::vector<std::vector<uint32_t>>&colors,
 std::vector<uint32_t>*pixels,Session&session){
 using namespace medical_live;
 const bool validate=!colors.empty();
 check(layers.size()<=32&&(!validate||colors.size()==layers.size()+1),"Incomplete medical layers");
 const unsigned n=w*h;
 for(const auto&color:colors)check(color.size()==n,"Medical layer dimensions differ");
 auto referenceStart=Clock::now();
 std::vector<uint32_t>expected;
 if(validate){expected=blend(std::vector<uint32_t>(n,background),colors[0]);
  for(size_t r=layers.size();r;--r)expected=blend(std::move(expected),colors[r]);}
 double referenceSeconds=seconds(referenceStart);
 auto begin=Clock::now();unsigned previousAllocations=session.allocations;
 auto&shared=session.ensure(w,h);auto&handle=shared.handle;auto&planes=shared.planes;
 auto&program=shared.program;auto&output=shared.output;auto*cpu=shared.cpu;
 size_t stride=shared.stride,allocation=shared.allocation;
 double setup=seconds(begin),prepare=0,compute=0,hardware=0;
 unsigned batches=0,end=layers.size();
 auto compositionStart=Clock::now();
 do{
  unsigned first=end>3?end-2:1,count=end?end-first+1:0;
  auto start=Clock::now();
  if(batches){planes[8]->bind();program.draw(planes[8]->texture,planes[0]->fbo,w,h);}
  else program.draw(opaque,planes[0]->fbo,w,h,1);
  // Already ordered peels have constant rank. A transparent pixel blends
  // as an exact no-op, so its key need not sample the color alpha again.
  glBindFramebuffer(GL_FRAMEBUFFER,planes[1]->fbo);glClearColor(1,1,1,1);glClear(GL_COLOR_BUFFER_BIT);
  for(unsigned slot=1;slot<=3;++slot){
   if(slot<=count){unsigned rank=first+slot-1;
    program.draw(layers[rank-1],planes[2*slot]->fbo,w,h);
    glBindFramebuffer(GL_FRAMEBUFFER,planes[2*slot+1]->fbo);
    glClearColor(float(rank)/255.f,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
   }
  }
  glFinish();check(glGetError()==GL_NO_ERROR,"Shared medical source completion failed");prepare+=seconds(start);
  start=Clock::now();double hw=0,host=0;
  check(!composite_execute_layers(handle.value,background,count+1,&hw,&host),composite_error());
  hardware+=hw;compute+=seconds(start);++batches;end=count?first-1:0;
 }while(end);
 auto start=Clock::now();planes[8]->bind();program.draw(planes[8]->texture,output.fbo,w,h);glFinish();
 check(glGetError()==GL_NO_ERROR,"Medical output sampling failed");double sample=seconds(start);
 double composition=seconds(compositionStart);
 start=Clock::now();pixels->resize(n);glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,pixels->data());
 check(glGetError()==GL_NO_ERROR,"Actual C7 medical output readback failed");
 if(validate)check(*pixels==expected,"Actual C7 medical frame differs from exact integer reference");
 check(!composite_sync(handle.value,1),composite_error());
 for(unsigned p=0;p<9;++p)for(size_t i=n;i<stride;++i)check(cpu[p*stride+i]==0x5a5a5a5a,"Shared medical padding changed");
 for(size_t i=9*stride;i<allocation/4;++i)check(cpu[i]==0x5a5a5a5a,"Shared medical tail changed");
 check(!composite_echo(handle.value),composite_error());double validation=seconds(start);
 glDisableVertexAttribArray(0);
 return {{"status",validate?"passed_actual_single_medical_shared_C7_frame":"completed_actual_medical_C7_frame_without_CPU_layer_captures"},{"batches",int(batches)},
  {"transparent_layers",int(layers.size())},{"setup_seconds",setup},{"GPU_prepare_seconds",prepare},
  {"PL_compute_and_sync_seconds",compute},{"PL_core_seconds",hardware},{"GPU_sample_seconds",sample},
  {"complete_composition_seconds",composition},{"reference_seconds_separate",referenceSeconds},
  {"readback_and_validation_seconds_separate",validation},{"all_pixels_exact",validate},
  {"CPU_color_layer_captures_present",validate},{"rank_keys","constant GPU clear; alpha-zero is exact neutral blend"},
  {"guards_unchanged",true},{"surface_restored",false},{"composite_kept_loaded",true},
  {"shared_allocation_count",int(session.allocations)},
  {"shared_allocation_reused",session.allocations==previousAllocations},{"HDMI_UI_integration",false}};
}
}

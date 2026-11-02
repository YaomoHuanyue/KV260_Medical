#pragma once
// Medical textures -> shared BO -> C7 -> GPU sampling. The caller retains the
// original, complete peeled color textures; no CPU pixel upload feeds PL.
#include "gl.hpp"
#include <QJsonArray>
#include <QJsonObject>
extern "C" {
void* composite_open(unsigned,unsigned);
void composite_close(void*);
int composite_select(void*,const char*);
const char* composite_error();
int composite_echo(void*);
void* composite_map(void*);
size_t composite_stride_bytes(void*);
size_t composite_allocation_bytes(void*);
int composite_export_fd(void*);
int composite_sync(void*,unsigned);
int composite_execute(void*,uint32_t,double*,double*);
int composite_reference(const uint32_t*,uint32_t*,unsigned,unsigned,uint32_t,unsigned);
}
namespace medical_live {
constexpr uint32_t background=0xff1a0f06;
struct Handle {
 void*value=nullptr;
 Handle(unsigned w,unsigned h){value=composite_open(w,h);check(value,composite_error());if(composite_select(value,"composite")){std::string message=composite_error();composite_close(value);value=nullptr;throw std::runtime_error(message);}}
 ~Handle(){if(value){composite_select(value,"scope");composite_close(value);}}
};
struct Program {
 GLuint id=0;
 Program(){
  const char*vs="attribute vec2 p;varying vec2 uv;void main(){uv=(p+1.0)*.5;gl_Position=vec4(p,0.0,1.0);}";
  const char*fs="precision mediump float;varying vec2 uv;uniform sampler2D image;uniform float mode;uniform float rank;void main(){vec4 c=texture2D(image,uv);"
   "if(mode<.5)gl_FragColor=c;else if(mode<1.5)gl_FragColor=c.a>0.0?vec4(c.rgb,1.0):vec4(6.0/255.0,15.0/255.0,26.0/255.0,1.0);"
   "else if(mode<2.5)gl_FragColor=c.a>0.0?vec4(rank/255.0,0.0,0.0,1.0):vec4(0.0);else gl_FragColor=vec4(1.0);}";
  auto compile=[](GLenum type,const char*text){GLuint shader=glCreateShader(type);glShaderSource(shader,1,&text,nullptr);glCompileShader(shader);GLint ok=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);if(!ok){glDeleteShader(shader);throw std::runtime_error("Medical shared shader compile failed");}return shader;};
  GLuint vertex=compile(GL_VERTEX_SHADER,vs),fragment=compile(GL_FRAGMENT_SHADER,fs);id=glCreateProgram();glAttachShader(id,vertex);glAttachShader(id,fragment);glBindAttribLocation(id,0,"p");glLinkProgram(id);GLint ok=0;glGetProgramiv(id,GL_LINK_STATUS,&ok);glDeleteShader(vertex);glDeleteShader(fragment);check(ok,"Medical shared shader link failed");
 }
 void draw(GLuint texture,GLuint fbo,unsigned w,unsigned h,float mode=0,float rank=0){
  static const float quad[]={-1,-1,1,-1,-1,1,1,1};
  glBindFramebuffer(GL_FRAMEBUFFER,fbo);glViewport(0,0,w,h);glDisable(GL_BLEND);glDisable(GL_DEPTH_TEST);glDisable(GL_DITHER);glBindBuffer(GL_ARRAY_BUFFER,0);glDisableVertexAttribArray(1);glDisableVertexAttribArray(2);glEnableVertexAttribArray(0);glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,quad);
  glUseProgram(id);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);glUniform1i(glGetUniformLocation(id,"image"),0);glUniform1f(glGetUniformLocation(id,"mode"),mode);glUniform1f(glGetUniformLocation(id,"rank"),rank);glDrawArrays(GL_TRIANGLE_STRIP,0,4);
  check(glGetError()==GL_NO_ERROR,"Medical shared texture draw failed");
 }
 ~Program(){if(id)glDeleteProgram(id);}
};
struct Readback {
 GLuint texture=0,fbo=0;
 Readback(unsigned w,unsigned h){glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);check(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE,"Medical shared readback FBO failed");}
 ~Readback(){if(fbo)glDeleteFramebuffers(1,&fbo);if(texture)glDeleteTextures(1,&texture);}
};
static std::vector<uint32_t> blend(std::vector<uint32_t>carry,const std::vector<uint32_t>&source){
 for(size_t i=0;i<carry.size();++i){uint32_t value=0xff000000,a=source[i]>>24;for(unsigned shift:{0u,8u,16u})value|=((((source[i]>>shift)&255)*a+((carry[i]>>shift)&255)*(255-a)+127)/255)<<shift;carry[i]=value;}return carry;
}
// The extractor has already ordered these layers. A strong PS baseline can
// omit sorting/keys and start with the opaque carry, preserving exact bytes.
static void ordered_reference(const uint32_t*input,uint32_t*output,unsigned n,unsigned stride,unsigned threads,bool packed){
#pragma omp parallel for num_threads(threads) schedule(static)
 for(unsigned i=0;i<n;++i){
  uint32_t value=input[i];
  for(unsigned layer=3;layer;--layer){uint32_t source=input[(packed?layer:2*layer)*stride+i],a=source>>24,result=0xff000000;
   for(unsigned shift:{0u,8u,16u}){unsigned t=((source>>shift)&255)*a+((value>>shift)&255)*(255-a)+128;result|=((t+(t>>8))>>8)<<shift;}value=result;
  }
  output[i]=value;
 }
}
static QJsonObject compose(Context&context,unsigned w,unsigned h,GLuint opaque,const std::vector<GLuint>&layers,const std::vector<std::vector<uint32_t>>&colors,std::vector<uint32_t>*plPixels=nullptr){
 check(layers.size()<=32&&colors.size()==layers.size()+1,"Incomplete medical texture list");unsigned n=w*h;
 for(const auto&color:colors)check(color.size()==n,"Medical texture reference size mismatch");
 auto expected=blend(std::vector<uint32_t>(n,background),colors[0]);for(size_t i=layers.size();i;--i)expected=blend(std::move(expected),colors[i]);
 Handle handle(w,h);size_t strideBytes=composite_stride_bytes(handle.value),stride=strideBytes/4,allocation=composite_allocation_bytes(handle.value);int fd=composite_export_fd(handle.value);check(fd>=0,composite_error());
 struct Fd{int value;~Fd(){close(value);}}sharedFd{fd};
 std::vector<std::unique_ptr<Plane>>planes;for(unsigned p=0;p<9;++p)planes.emplace_back(new Plane(context.display,fd,w,h,p*strideBytes));
 auto*cpu=static_cast<uint32_t*>(composite_map(handle.value));check(cpu,"Medical shared CPU mapping unavailable");Program program;Readback readback(w,h);
 std::vector<std::vector<unsigned>>groups;for(unsigned end=layers.size();end;){unsigned begin=end>3?end-2:1;std::vector<unsigned>group;for(unsigned r=begin;r<=end;++r)group.push_back(r);groups.push_back(group);end=begin-1;}if(groups.empty())groups.push_back({});
 constexpr unsigned backendCount=8,roundCount=6;
 const char*backendNames[]={"PL","PS_sort_direct1","PS_sort_direct4","PS_sort_cached1","PS_sort_cached4","PS_ordered_cached1","PS_ordered_cached4","PS_ordered_direct4"};
 std::vector<uint32_t>cpuOutput(n),actual(n),cachedInput(8*n);QJsonArray receipts;std::vector<double>times[backendCount];
 for(unsigned round=0;round<roundCount;++round)for(unsigned position=0;position<backendCount;++position){
  unsigned backend=(position+round)%backendCount;bool usePL=backend==0,validateInputs=round==0,cached=backend>=3&&backend<=6,ordered=backend>=5;
  unsigned threads=(backend==1||backend==3||backend==5)?1:4;double prepare=0,compute=0,sample=0,hardware=0;
  std::vector<uint32_t>carryExpected;if(validateInputs)carryExpected=blend(std::vector<uint32_t>(n,background),colors[0]);
  auto loopStart=Clock::now();
  for(unsigned batch=0;batch<groups.size();++batch){auto start=Clock::now();
   if(batch){planes[8]->bind();program.draw(planes[8]->texture,planes[0]->fbo,w,h);}else program.draw(opaque,planes[0]->fbo,w,h,1);
   program.draw(opaque,planes[1]->fbo,w,h,3);
   for(unsigned slot=1;slot<=3;++slot){
    if(slot<=groups[batch].size()){unsigned rank=groups[batch][slot-1];program.draw(layers[rank-1],planes[2*slot]->fbo,w,h);program.draw(layers[rank-1],planes[2*slot+1]->fbo,w,h,2,float(rank));}
    else for(unsigned p:{2*slot,2*slot+1}){glBindFramebuffer(GL_FRAMEBUFFER,planes[p]->fbo);glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);}
   }
   glFinish();check(glGetError()==GL_NO_ERROR,"Medical GPU preparation failed");prepare+=seconds(start);
   std::vector<uint32_t>sourceSnapshot;
   if(validateInputs){
    check(!composite_sync(handle.value,1),composite_error());sourceSnapshot.assign(cpu,cpu+8*stride);
    for(unsigned i=0;i<n;++i){check(cpu[i]==carryExpected[i]&&cpu[stride+i]==0xffffffff,"GPU carry or ordinal key mismatch");for(unsigned slot=1;slot<=3;++slot){uint32_t color=0,depth=0;if(slot<=groups[batch].size()){unsigned rank=groups[batch][slot-1];color=colors[rank][i];depth=color>>24?0xff000000|rank:0;}check(cpu[2*slot*stride+i]==color&&cpu[(2*slot+1)*stride+i]==depth,"GPU medical color or ordinal key mismatch");}}
   }
   start=Clock::now();
   if(usePL){double hw=0,host=0;check(!composite_execute(handle.value,background,&hw,&host),composite_error());hardware+=hw;}
   else{
    check(!composite_sync(handle.value,1),composite_error());const uint32_t*input=cpu;unsigned inputStride=unsigned(stride);
    if(cached){unsigned count=ordered?4:8;for(unsigned p=0;p<count;++p)std::memcpy(cachedInput.data()+p*n,cpu+(ordered?2*p:p)*stride,n*4);input=cachedInput.data();inputStride=n;}
    if(ordered)ordered_reference(input,cpuOutput.data(),n,inputStride,threads,cached);
    else check(!composite_reference(input,cpuOutput.data(),n,inputStride,background,threads),"Medical optimized PS composition failed");
    std::memcpy(cpu+8*stride,cpuOutput.data(),n*4);check(!composite_sync(handle.value,0),composite_error());
   }
   compute+=seconds(start);
   if(validateInputs){
    for(auto rank=groups[batch].rbegin();rank!=groups[batch].rend();++rank)carryExpected=blend(std::move(carryExpected),colors[*rank]);
    planes[8]->bind();program.draw(planes[8]->texture,readback.fbo,w,h);glFinish();glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,actual.data());check(glGetError()==GL_NO_ERROR&&actual==carryExpected,"GPU sampled medical batch mismatch");
    check(!composite_sync(handle.value,1),composite_error());check(!std::memcmp(sourceSnapshot.data(),cpu,8*strideBytes),"Composition altered GPU-produced inputs");
   }
  }
  auto start=Clock::now();planes[8]->bind();program.draw(planes[8]->texture,readback.fbo,w,h);glFinish();check(glGetError()==GL_NO_ERROR,"Medical GPU sample completion failed");sample=seconds(start);double total=seconds(loopStart);
  glBindFramebuffer(GL_FRAMEBUFFER,readback.fbo);glReadPixels(0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,actual.data());check(glGetError()==GL_NO_ERROR&&actual==expected,"Complete GPU-sampled medical image mismatched integer reference");
  if(usePL&&plPixels)*plPixels=actual;
  check(!composite_sync(handle.value,1),composite_error());for(unsigned p=0;p<9;++p)for(size_t i=n;i<stride;++i)check(cpu[p*stride+i]==0x5a5a5a5a,"Medical shared padding changed");for(size_t i=9*stride;i<allocation/4;++i)check(cpu[i]==0x5a5a5a5a,"Medical shared tail guard changed");check(!composite_echo(handle.value),composite_error());
  if(round)times[backend].push_back(total);
  receipts.append(QJsonObject{{"backend",backendNames[backend]},{"round",int(round)},{"position_in_round",int(position)},{"GPU_prepare_seconds",prepare},{"compute_and_sync_seconds",compute},{"PL_core_seconds",hardware},{"GPU_sample_seconds",sample},{"complete_composition_seconds",total},{"warmup_with_input_and_batch_validation",validateInputs},{"all_pixels_exact",true}});
 }
 check(!composite_select(handle.value,"scope"),composite_error());glDisableVertexAttribArray(0);
 QJsonObject medians;double bestPS=std::numeric_limits<double>::infinity();const char*bestName=nullptr;
 for(unsigned backend=0;backend<backendCount;++backend){double value=median(times[backend]);medians.insert(backendNames[backend],value);if(backend&&value<bestPS){bestPS=value;bestName=backendNames[backend];}}
 return QJsonObject{{"status","passed_actual_medical_GPU_shared_PL_GPU"},{"width",int(w)},{"height",int(h)},{"transparent_layers",int(layers.size())},{"batches",int(groups.size())},{"trials",receipts},{"backend_median_seconds",medians},{"benchmark_order","interleaved_rounds_rotating_first_backend"},{"timed_rounds",int(roundCount-1)},{"GPU_completion_in_timing",true},{"validation_excluded_from_timing",true},{"PL_median_seconds",median(times[0])},{"best_PS_median_seconds",bestPS},{"best_PS_backend",bestName},{"composition_speedup",bestPS/median(times[0])},{"guards_unchanged",true},{"surface_restored",true},{"medical_extraction_common_and_separate",true},{"HDMI_UI_integration",false},{"clinical_frame_rate_verified",false}};
}
}

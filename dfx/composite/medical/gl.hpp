#pragma once
// Independent offscreen allocator; no window, swap, or KMS modeset.
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
using Clock=std::chrono::steady_clock;
extern "C" int composite_execute_layers(void*,uint32_t,unsigned,double*,double*);
static void check(bool b,const char*m){if(!b)throw std::runtime_error(m);}
static double seconds(Clock::time_point t){return std::chrono::duration<double>(Clock::now()-t).count();}
static double median(std::vector<double>v){std::sort(v.begin(),v.end());return v[v.size()/2];}
struct Context {
 int fd=-1;void*library=nullptr,*gbm=nullptr;void(*destroyGbm)(void*)=nullptr;
 EGLDisplay display=EGL_NO_DISPLAY;EGLContext context=EGL_NO_CONTEXT;EGLSurface surface=EGL_NO_SURFACE;
 Context(){
  library=dlopen("libgbm.so.1",RTLD_NOW|RTLD_GLOBAL);check(library,"GBM runtime unavailable");
  auto create=reinterpret_cast<void*(*)(int)>(dlsym(library,"gbm_create_device"));
  destroyGbm=reinterpret_cast<void(*)(void*)>(dlsym(library,"gbm_device_destroy"));check(create&&destroyGbm,"GBM functions unavailable");
  fd=open("/dev/dri/card0",O_RDWR|O_CLOEXEC);check(fd>=0,"Display allocator unavailable");gbm=create(fd);check(gbm,"GBM creation failed");
  display=eglGetDisplay(static_cast<EGLNativeDisplayType>(gbm));check(display!=EGL_NO_DISPLAY,"EGL display unavailable");
  check(eglInitialize(display,nullptr,nullptr)&&eglBindAPI(EGL_OPENGL_ES_API),"EGL initialization failed");
  const EGLint attributes[]={EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,
   EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_NONE};
  EGLConfig config=nullptr;EGLint count=0;check(eglChooseConfig(display,attributes,&config,1,&count)&&count,"Pbuffer config unavailable");
  const EGLint ca[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE},sa[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE};
  context=eglCreateContext(display,config,EGL_NO_CONTEXT,ca);surface=eglCreatePbufferSurface(display,config,sa);
  check(context!=EGL_NO_CONTEXT&&surface!=EGL_NO_SURFACE&&eglMakeCurrent(display,surface,surface,context),"Offscreen context failed");
  auto renderer=reinterpret_cast<const char*>(glGetString(GL_RENDERER));
  check(renderer&&std::string(renderer).find("Mali-400")!=std::string::npos,"Expected Mali hardware context");
 }
 ~Context(){
  if(display!=EGL_NO_DISPLAY){glFinish();eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
   if(surface!=EGL_NO_SURFACE)eglDestroySurface(display,surface);if(context!=EGL_NO_CONTEXT)eglDestroyContext(display,context);eglTerminate(display);}
  if(gbm&&destroyGbm)destroyGbm(gbm);if(fd>=0)close(fd);if(library)dlclose(library);
 }
};
struct Plane {
 EGLDisplay display;EGLImageKHR image=EGL_NO_IMAGE_KHR;GLuint texture=0,fbo=0;
 PFNEGLDESTROYIMAGEKHRPROC destroy;PFNGLEGLIMAGETARGETTEXTURE2DOESPROC target;
 Plane(EGLDisplay d,int fd,int w,int h,size_t offset):display(d){
  auto create=reinterpret_cast<PFNEGLCREATEIMAGEKHRPROC>(eglGetProcAddress("eglCreateImageKHR"));
  destroy=reinterpret_cast<PFNEGLDESTROYIMAGEKHRPROC>(eglGetProcAddress("eglDestroyImageKHR"));
  target=reinterpret_cast<PFNGLEGLIMAGETARGETTEXTURE2DOESPROC>(eglGetProcAddress("glEGLImageTargetTexture2DOES"));
  check(create&&destroy&&target,"Shared image entrypoints unavailable");
  const EGLint a[]={EGL_WIDTH,w,EGL_HEIGHT,h,EGL_LINUX_DRM_FOURCC_EXT,0x34324241,
   EGL_DMA_BUF_PLANE0_FD_EXT,fd,EGL_DMA_BUF_PLANE0_OFFSET_EXT,EGLint(offset),EGL_DMA_BUF_PLANE0_PITCH_EXT,w*4,EGL_NONE};
  image=create(d,EGL_NO_CONTEXT,EGL_LINUX_DMA_BUF_EXT,nullptr,a);check(image!=EGL_NO_IMAGE_KHR,"Shared plane import failed");
  glGenTextures(1,&texture);bind();glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glGenFramebuffers(1,&fbo);
  glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
  check(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE,"Shared plane FBO incomplete");
 }
 void bind(){glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);target(GL_TEXTURE_2D,image);}
 ~Plane(){glFinish();if(fbo)glDeleteFramebuffers(1,&fbo);if(texture)glDeleteTextures(1,&texture);if(image!=EGL_NO_IMAGE_KHR)destroy(display,image);}
};

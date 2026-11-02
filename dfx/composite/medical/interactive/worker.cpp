// GLES2 has no fragment highp on Mali-400. Extract surfaces by full hardware
// depth testing and excluding exact triangle identifiers at each pixel.
// No floating depth is sampled in a fragment shader; ranks preserve the
// resulting order. A thirty-third nonempty peel rejects the bounded thirty-two-layer path.
#include "../gl.hpp"
#include "../screen_tiles.hpp"
#include "render_batches.hpp"
#include "strong_ps.hpp"
#include "frame_controls.hpp"
#include <QCoreApplication>
#include <QTemporaryDir>
#include <signal.h>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QMatrix4x4>
#include <QCryptographicHash>
#include <QSaveFile>
#include <array>
#include <cmath>
#include <sys/resource.h>

static void checkGL(const char*stage){
 GLenum error=glGetError();if(error!=GL_NO_ERROR)throw std::runtime_error(std::string(stage)+" GL error "+std::to_string(error));
}

static GLuint makeShader(GLenum kind,const std::string&source){
 GLuint s=glCreateShader(kind);const char*p=source.c_str();glShaderSource(s,1,&p,nullptr);glCompileShader(s);GLint ok=0;glGetShaderiv(s,GL_COMPILE_STATUS,&ok);if(!ok){char log[2048];glGetShaderInfoLog(s,sizeof log,nullptr,log);throw std::runtime_error(log);}return s;
}
struct Shader {
 GLuint id;int analysisMode=0;bool analysis=false;
 Shader(const std::string&vs,const std::string&fs){GLuint v=makeShader(GL_VERTEX_SHADER,vs),f=makeShader(GL_FRAGMENT_SHADER,fs);id=glCreateProgram();glAttachShader(id,v);glAttachShader(id,f);glBindAttribLocation(id,0,"position");glBindAttribLocation(id,1,"normal");glBindAttribLocation(id,2,"identifier");glBindAttribLocation(id,3,"analysis");glLinkProgram(id);GLint ok=0;glGetProgramiv(id,GL_LINK_STATUS,&ok);check(ok,"Medical shader link failed");analysis=glGetAttribLocation(id,"analysis")>=0;glDeleteShader(v);glDeleteShader(f);}
 GLint uniform(const char*s){return glGetUniformLocation(id,s);}
 ~Shader(){glDeleteProgram(id);}
};
struct Image {
 GLuint texture=0,fbo=0;unsigned width,height;
 Image(unsigned w,unsigned h,GLuint depth):width(w),height(h){
  glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);if(depth)glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,depth);check(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE,"Medical FBO incomplete");
 }
 std::vector<uint32_t> read(){std::vector<uint32_t>p(width*height);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,p.data());check(glGetError()==GL_NO_ERROR,"Medical image readback failed");return p;}
 ~Image(){glDeleteFramebuffers(1,&fbo);glDeleteTextures(1,&texture);}
};
// Only submission/temporary buffer size differs between benchmark modes.
static unsigned medicalBatchVertices=60000;
struct Mesh {
 GLuint vertices=0,identifiers=0,elements=0;unsigned count=0,startId=0;QVector3D color;QString sha;
 std::vector<medical_tiles::Box> boxes;size_t submitted=0;
 FileStamp sourceStamp,analysisStamp;GLuint analysisBuffer=0;QString analysisPath,analysisSHA;std::vector<float>sourceAnalysis,compactAnalysis;
 QString sourcePath;QMatrix4x4 projected;unsigned projectedWidth=0,projectedHeight=0;
 bool streaming=false,cacheReady=false,cachedActive=false;unsigned cachedCount=0;
 std::vector<float>sourceVertices;std::vector<uint32_t>sourceIdentifiers;std::vector<unsigned>cachedMask;
 std::vector<float>compactVertices;std::vector<uint32_t>compactIdentifiers;
 Mesh(QString path,unsigned vertexCount,unsigned first,QVector3D c,const QMatrix4x4&mvp,unsigned width,unsigned height,bool stream=false):count(vertexCount),startId(first),color(c),streaming(stream){
  sourcePath=path;sourceStamp=FileStamp::read(path);projected=mvp;projectedWidth=width;projectedHeight=height;
  check(count&&count%3==0&&first+count/3<0x1000000,"Medical triangle identifier bound");QFile f(path);check(f.open(QIODevice::ReadOnly)&&f.size()==qint64(count)*24,"Medical mesh size mismatch");QCryptographicHash hash(QCryptographicHash::Sha256);check(hash.addData(&f),"Mesh hash failed");sha=hash.result().toHex();auto*bytes=f.map(0,f.size());check(bytes,"Medical mesh map failed");auto*v=reinterpret_cast<const float*>(bytes);for(size_t i=0;i<size_t(count)*6;++i)check(std::isfinite(v[i]),"Nonfinite mesh vertex");
  boxes.reserve(count/3);for(unsigned i=0;i<count/3;++i)boxes.push_back(medical_tiles::bounds(v+i*18,mvp,width,height));
  glGenBuffers(1,&elements);glGenBuffers(1,&vertices);glBindBuffer(GL_ARRAY_BUFFER,vertices);
  if(streaming){sourceVertices.assign(v,v+size_t(count)*6);glBufferData(GL_ARRAY_BUFFER,medicalBatchVertices*24,nullptr,GL_STREAM_DRAW);}else glBufferData(GL_ARRAY_BUFFER,f.size(),bytes,GL_STATIC_DRAW);f.unmap(bytes);
  std::vector<uint32_t>ids(count);for(unsigned i=0;i<count;++i)ids[i]=0xff000000|(first+i/3);glGenBuffers(1,&identifiers);glBindBuffer(GL_ARRAY_BUFFER,identifiers);
  if(streaming){sourceIdentifiers=std::move(ids);glBufferData(GL_ARRAY_BUFFER,medicalBatchVertices*4,nullptr,GL_STREAM_DRAW);}else glBufferData(GL_ARRAY_BUFFER,ids.size()*4,ids.data(),GL_STATIC_DRAW);
 }
 void loadAnalysis(const QString&path){
  if(!sourceAnalysis.empty()){check(analysisPath==path&&analysisStamp==FileStamp::read(path),"Analysis file changed; reload the scene");return;}
  QFile f(path);check(f.open(QIODevice::ReadOnly)&&f.size()==qint64(count)*16,"Analysis data size mismatch");auto bytes=f.readAll();
  auto*p=reinterpret_cast<const float*>(bytes.constData());for(size_t i=0;i<size_t(count)*4;++i)check(std::isfinite(p[i]),"Nonfinite analysis attribute");
  sourceAnalysis.assign(p,p+size_t(count)*4);analysisPath=path;analysisStamp=FileStamp::read(path);
  analysisSHA=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex();glGenBuffers(1,&analysisBuffer);glBindBuffer(GL_ARRAY_BUFFER,analysisBuffer);glBufferData(GL_ARRAY_BUFFER,medicalBatchVertices*16,nullptr,GL_STREAM_DRAW);cacheReady=false;
 }
 void reproject(const QMatrix4x4&mvp,unsigned w,unsigned h){
  if(projectedWidth==w&&projectedHeight==h&&!std::memcmp(projected.constData(),mvp.constData(),16*sizeof(float)))return;
  check(streaming,"Persistent medical worker requires bounded streamed mesh buffers");
  projected=mvp;projectedWidth=w;projectedHeight=h;boxes.clear();boxes.reserve(count/3);
  for(unsigned i=0;i<count/3;++i)boxes.push_back(medical_tiles::bounds(sourceVertices.data()+size_t(i)*18,mvp,w,h));
  cacheReady=false;cachedMask.clear();
 }
 void draw(Shader&s,const medical_tiles::Active*active=nullptr){
  auto attributes=[this,&s](unsigned base){
   if(s.analysis&&analysisBuffer){glBindBuffer(GL_ARRAY_BUFFER,analysisBuffer);glEnableVertexAttribArray(3);glVertexAttribPointer(3,4,GL_FLOAT,GL_FALSE,16,reinterpret_cast<void*>(size_t(base)*16));}
   else{glDisableVertexAttribArray(3);glVertexAttrib4f(3,0,0,-1,0);}
   glUniform1f(s.uniform("analysisMode"),analysisBuffer?s.analysisMode:0);

   glBindBuffer(GL_ARRAY_BUFFER,vertices);glEnableVertexAttribArray(0);glVertexAttribPointer(0,3,GL_FLOAT,GL_FALSE,24,reinterpret_cast<void*>(size_t(base)*24));glEnableVertexAttribArray(1);glVertexAttribPointer(1,3,GL_FLOAT,GL_FALSE,24,reinterpret_cast<void*>(size_t(base)*24+12));glBindBuffer(GL_ARRAY_BUFFER,identifiers);glEnableVertexAttribArray(2);glVertexAttribPointer(2,4,GL_UNSIGNED_BYTE,GL_TRUE,4,reinterpret_cast<void*>(size_t(base)*4));
  };
  glUniform3f(s.uniform("color"),color.x(),color.y(),color.z());
  if(streaming){
   if(!cacheReady||cachedActive!=bool(active)||(active&&cachedMask!=active->integral)){
    std::vector<std::pair<unsigned,unsigned>>ranges;
    const float*data=sourceVertices.data();const uint32_t*ids=sourceIdentifiers.data();cachedCount=count;
    if(active){
     cachedCount=0;
     for(unsigned begin=0;begin<count/3;){
      while(begin<count/3&&!active->intersects(boxes[begin]))++begin;
      unsigned end=begin;while(end<count/3&&active->intersects(boxes[end]))++end;
      if(end>begin){ranges.emplace_back(begin*3,end*3);cachedCount+=(end-begin)*3;}begin=end;
     }
     compactVertices.resize(size_t(cachedCount)*6);compactIdentifiers.resize(cachedCount);if(!sourceAnalysis.empty())compactAnalysis.resize(size_t(cachedCount)*4);size_t offset=0;
     for(auto range:ranges){size_t size=range.second-range.first;std::memcpy(compactVertices.data()+offset*6,data+size_t(range.first)*6,size*24);std::memcpy(compactIdentifiers.data()+offset,ids+range.first,size*4);if(!sourceAnalysis.empty())std::memcpy(compactAnalysis.data()+offset*4,sourceAnalysis.data()+size_t(range.first)*4,size*16);offset+=size;}
     cachedMask=active->integral;
    }else cachedMask.clear();
    cacheReady=true;cachedActive=bool(active);
   }
   attributes(0);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,0);
   const unsigned batchVertices=medicalBatchVertices;
   const float*data=active?compactVertices.data():sourceVertices.data();const uint32_t*ids=active?compactIdentifiers.data():sourceIdentifiers.data();
   for(unsigned base=0;base<cachedCount;base+=batchVertices){
    unsigned size=std::min(batchVertices,cachedCount-base);
    glBindBuffer(GL_ARRAY_BUFFER,vertices);glBufferSubData(GL_ARRAY_BUFFER,0,size_t(size)*24,data+size_t(base)*6);
    glBindBuffer(GL_ARRAY_BUFFER,identifiers);glBufferSubData(GL_ARRAY_BUFFER,0,size_t(size)*4,ids+base);
    if(s.analysis&&analysisBuffer){const float*analysisData=active?compactAnalysis.data():sourceAnalysis.data();glBindBuffer(GL_ARRAY_BUFFER,analysisBuffer);glBufferSubData(GL_ARRAY_BUFFER,0,size_t(size)*16,analysisData+size_t(base)*4);}
    checkGL("Bounded compacted mesh upload");glDrawArrays(GL_TRIANGLES,0,size);glFinish();checkGL("Compacted mesh batch completion");
   }
   submitted+=cachedCount/3;return;
  }
  if(!active){
   attributes(0);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,0);
   // Bound Mali tiler scratch memory. Retain depth/color and draw order across
   // batches; completion releases transient geometry without discarding data.
   const unsigned batchVertices=medicalBatchVertices;
   for(unsigned base=0;base<count;base+=batchVertices){glDrawArrays(GL_TRIANGLES,base,std::min(batchVertices,count-base));glFinish();checkGL("Unpruned mesh batch completion");}
   submitted+=count/3;return;
  }
  // Preserve source triangle order using contiguous ranges of the original
  // VBO. Avoid creating/copying an index buffer at each pass on Mali-400.
  attributes(0);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,0);
  const unsigned trianglesPerBatch=medicalBatchVertices/3;unsigned queued=0;
  for(unsigned begin=0;begin<count/3;){
   while(begin<count/3&&!active->intersects(boxes[begin]))++begin;
   unsigned end=begin;while(end<count/3&&active->intersects(boxes[end])&&end-begin<trianglesPerBatch-queued)++end;
   if(end>begin){glDrawArrays(GL_TRIANGLES,begin*3,(end-begin)*3);queued+=end-begin;submitted+=end-begin;}
   if(queued==trianglesPerBatch){glFinish();checkGL("Pruned contiguous batch completion");queued=0;}
   begin=end;
  }
  if(queued){glFinish();checkGL("Pruned contiguous final completion");}
 }
 ~Mesh(){glDeleteBuffers(1,&analysisBuffer);glDeleteBuffers(1,&elements);glDeleteBuffers(1,&vertices);glDeleteBuffers(1,&identifiers);}
};
struct MeshBank {
 std::array<std::unique_ptr<Mesh>,3>meshes;unsigned hits=0,misses=0;
 QByteArray pinnedScene;std::array<std::unique_ptr<Shader>,2>identifierVariants;std::array<std::unique_ptr<Shader>,4>colorVariants;
 void pinScene(const QByteArray&bytes){auto digest=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256);if(pinnedScene.isEmpty())pinnedScene=digest;else check(pinnedScene==digest,"Scene changed; restart the worker");}
 Mesh&get(unsigned slot,QString file,unsigned count,unsigned id,QVector3D color,const QMatrix4x4&mvp,unsigned w,unsigned h){
  auto&p=meshes[slot];
  if(!p||p->sourcePath!=file||p->count!=count||p->startId!=id){p.reset(new Mesh(file,count,id,color,mvp,w,h,true));++misses;}
  else{check(p->sourceStamp==FileStamp::read(file),"Mesh changed; restart the worker");p->reproject(mvp,w,h);++hits;}
  p->submitted=0;return *p;
 }
};
static QVector3D vector(const QJsonValue&v){auto a=v.toArray();check(a.size()==3,"Scene bound missing");return QVector3D(a[0].toDouble(),a[1].toDouble(),a[2].toDouble());}
static bool captureEvidence=false;
static void save(QString path,const std::vector<uint32_t>&pixels){if(!captureEvidence&&!path.endsWith("/live_complete_PL.rgba"))return;QSaveFile f(path);check(f.open(QIODevice::WriteOnly),"Output file unavailable");check(f.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()*4)==qint64(pixels.size()*4)&&f.commit(),"Output write failed");}
static void saveJson(QString path,const QJsonObject&object){QSaveFile f(path);check(f.open(QIODevice::WriteOnly),"Report unavailable");check(f.write(QJsonDocument(object).toJson())>0&&f.commit(),"Report write failed");}
struct Peel {
 std::unique_ptr<Image>identifier,color;
 std::vector<uint32_t>ids,pixels;
 Peel(unsigned w,unsigned h,GLuint depth):identifier(new Image(w,h,depth)),color(new Image(w,h,depth)){}
};
static const char*vertex=R"GLSL(
attribute highp vec3 position;attribute mediump vec3 normal;attribute mediump vec4 identifier;
uniform highp mat4 mvp;uniform mediump mat3 normalMatrix;
varying mediump vec4 token;varying mediump vec3 n;
void main(){gl_Position=mvp*vec4(position,1.0);token=identifier;n=normalMatrix*normal;}
)GLSL";
static std::string idFragment(){
 std::string s="precision mediump float;varying mediump vec4 token;uniform vec2 size;uniform float excluded;";
 for(int i=0;i<8;++i)s+="uniform sampler2D previous"+std::to_string(i)+";";
 s+="vec3 byteId(){return floor(clamp(token.rgb/max(token.a,.0001),0.0,1.0)*255.0+.5)/255.0;}bool same(vec4 a){return a.a>.5&&all(lessThan(abs(a.rgb-byteId()),vec3(.5/255.0)));}void main(){vec2 uv=gl_FragCoord.xy/size;";
 for(int i=0;i<32;++i){
  std::string tile="vec2((uv.x+"+std::to_string(i%2)+".0)*.5,(uv.y+"+std::to_string((i%4)/2)+".0)*.5)";
  s+="if(excluded>"+std::to_string(i)+".5){vec4 prior=texture2D(previous"+std::to_string(i/4)+","+tile+");if(same(prior))discard;if(excluded<"+std::to_string(i+1)+".5&&prior.a<.5)discard;}";
 }
 return s+"gl_FragColor=vec4(byteId(),1.0);}";
}
static const char*colorFragment=R"GLSL(
precision mediump float;varying mediump vec4 token;varying mediump vec3 n;
uniform sampler2D chosen;uniform vec2 size;uniform vec3 color;uniform float alpha;
void main(){vec3 byte=floor(clamp(token.rgb/max(token.a,.0001),0.0,1.0)*255.0+.5)/255.0;vec4 id=texture2D(chosen,gl_FragCoord.xy/size);if(id.a<.5||any(greaterThan(abs(id.rgb-byte),vec3(.5/255.0))))discard;
float light=.26+.74*abs(dot(normalize(n),normalize(vec3(.2,.35,1.))));gl_FragColor=vec4(color*light,alpha);}
)GLSL";
static std::string controlledVertex(bool clip,bool analysis){
 std::string source=vertex;if(!clip&&!analysis)return source;
 std::string declarations,assignments;
 if(clip){declarations+="uniform highp vec3 clipNormal;uniform highp float clipValue;varying mediump float cutDistance;";assignments+="cutDistance=dot(position,clipNormal)-clipValue;";}
 if(analysis){declarations+="attribute mediump vec4 analysis;varying mediump vec4 a;";assignments+="a=analysis;";}
 auto pos=source.find("void main()");source.insert(pos,declarations);source.insert(source.rfind('}'),assignments);return source;
}
static std::string controlledId(bool clip){auto source=idFragment();if(clip){source="varying mediump float cutDistance;"+source;auto pos=source.find("void main(){")+12;source.insert(pos,"if(cutDistance>0.0)discard;");}return source;}
static std::string controlledColor(bool clip,bool analysis){
 std::string source=colorFragment;if(!clip&&!analysis)return source;
 std::string declarations,operations;
 if(clip){declarations+="varying mediump float cutDistance;";operations+="if(cutDistance>0.0)discard;";}
 if(analysis){declarations+=R"GLSL(varying mediump vec4 a;uniform float analysisMode,requiredRadius,resolutionMargin;
vec3 hue(float h){return clamp(abs(fract(h+vec3(0.,.6667,.3333))*6.-3.)-1.,0.,1.);})GLSL";}
 source.insert(source.find("void main()"),declarations);source.insert(source.find("void main(){")+12,operations);
 if(analysis){std::string palette=R"GLSL(vec3 c=color;
if(analysisMode>.5){if(a.w<.5)c=vec3(.48,.48,.5);else if(analysisMode<1.5)c=hue(mod(max(a.x,0.),12.)/12.);
else if(analysisMode<2.5){float spare=max(0.,a.y-resolutionMargin)-requiredRadius;c=spare<0.?vec3(.95,.15,.15):spare<.4?vec3(1.,.72,.12):vec3(.16,.84,.36);}
else c=a.z<0.?vec3(.5):a.z<.45?vec3(.95,.2,.2):a.z<.70?vec3(1.,.72,.12):a.z<.90?vec3(.2,.8,.65):vec3(.24,.5,1.);}
gl_FragColor=vec4(c*light,alpha);)GLSL";
  std::string previous="gl_FragColor=vec4(color*light,alpha);";auto pos=source.find(previous);check(pos!=std::string::npos,"Controlled color source marker missing");source.replace(pos,previous.size(),palette);
 }
 return source;
}
static void setControls(Shader&s,const FrameControls&c){glUseProgram(s.id);QVector3D normal;normal[c.clipAxis]=1;
 glUniform3f(s.uniform("clipNormal"),normal.x(),normal.y(),normal.z());glUniform1f(s.uniform("clipValue"),c.clipValue);
 glUniform1f(s.uniform("requiredRadius"),c.requiredRadius);glUniform1f(s.uniform("resolutionMargin"),c.resolutionMargin);s.analysisMode=c.colorMode;
}
static void matrix(Shader&s,const QMatrix4x4&mvp,const QMatrix3x3&normal,unsigned w,unsigned h){glUseProgram(s.id);glUniformMatrix4fv(s.uniform("mvp"),1,GL_FALSE,mvp.constData());glUniformMatrix3fv(s.uniform("normalMatrix"),1,GL_FALSE,normal.constData());glUniform2f(s.uniform("size"),w,h);}
using Atlas=std::array<std::unique_ptr<Image>,8>;
static void images(Shader&s,const Atlas&atlas,unsigned count){
 glUniform1f(s.uniform("excluded"),float(count));for(int i=0;i<8;++i){glActiveTexture(GL_TEXTURE0+i);glBindTexture(GL_TEXTURE_2D,atlas[i]->texture);auto name="previous"+std::to_string(i);glUniform1i(s.uniform(name.c_str()),i);}
}
static void renderId(Peel&out,Shader&s,Mesh&airway,Mesh&nodule,Mesh&lung,bool opaque,const Atlas&atlas,unsigned count,const medical_tiles::Active*active,const FrameControls&controls){
 glBindFramebuffer(GL_FRAMEBUFFER,out.identifier->fbo);glClearColor(0,0,0,0);glDepthMask(GL_TRUE);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);glClearDepthf(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);glUseProgram(s.id);images(s,atlas,0);
 checkGL("Identifier framebuffer and samplers");
 if(opaque){if(controls.airway)airway.draw(s,active);checkGL("Opaque airway draw");if(controls.nodule)nodule.draw(s,active);checkGL("Opaque nodule draw");}else{
  // Seed the opaque depth limit without writing an opaque identifier. Thus
  // every retained lung fragment is strictly in front of an opaque object.
  glColorMask(GL_FALSE,GL_FALSE,GL_FALSE,GL_FALSE);if(controls.airway)airway.draw(s,active);checkGL("Opaque airway depth seed");if(controls.nodule)nodule.draw(s,active);checkGL("Opaque nodule depth seed");glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);images(s,atlas,count);checkGL("Lung samplers");lung.draw(s,active);checkGL("Lung identifier draw");
 }
 glFinish();auto stage="Identifier completion, opaque="+std::to_string(opaque)+", previous layers="+std::to_string(count);checkGL(stage.c_str());
}
static void renderColor(Peel&out,Shader&s,Mesh&airway,Mesh&nodule,Mesh&lung,bool opaque,const medical_tiles::Active*active,const FrameControls&controls){
 glBindFramebuffer(GL_FRAMEBUFFER,out.color->fbo);glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);glEnable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDepthFunc(GL_EQUAL);glUseProgram(s.id);glUniform1f(s.uniform("alpha"),opaque?1.f:float(controls.opacityByte)/255.f);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,out.identifier->texture);glUniform1i(s.uniform("chosen"),0);
 if(opaque){if(controls.airway)airway.draw(s,active);if(controls.nodule)nodule.draw(s,active);}else lung.draw(s,active);
 glFinish();check(glGetError()==GL_NO_ERROR,"Medical selected color extraction failed");glDepthMask(GL_TRUE);
}
static QJsonObject run(QString scenePath,QString output,unsigned width,unsigned height,bool full,float yaw,float pitch,bool prune,Context&context,MeshBank&cache,medical_render::Session&session,bool strongPS,const FrameControls&controls){
 const bool needCPUcolors=captureEvidence||strongPS;double colorReadback=0;QFile file(scenePath);check(file.open(QIODevice::ReadOnly),"Scene JSON unavailable");auto bytes=file.readAll();cache.pinScene(bytes);auto scene=QJsonDocument::fromJson(bytes).object();check(scene["schema"]=="kv260.ui.scene.v1","Scene schema mismatch");auto meshes=scene["meshes"].toObject();QDir root=QFileInfo(scenePath).dir();auto a=meshes["airway"].toObject(),l=meshes[full?"lung":"lung_preview"].toObject(),n=meshes["nodule"].toObject();
 auto center=(vector(a["bounds_min"])+vector(a["bounds_max"]))/2;float radius=(vector(a["bounds_max"])-vector(a["bounds_min"])).length()/2;
 if(controls.focus){center=controls.center;radius=controls.radius;}
 QMatrix4x4 view,projection;view.lookAt(center+QVector3D(0,-2.8f*radius/controls.zoom,0),center,QVector3D(0,0,1));view.translate(center);view.rotate(pitch,1,0,0);view.rotate(yaw,0,0,1);view.translate(-center);
 // Tighten only the overview depth range. All source bounding-box corners
 // remain inside the interval; positions, orientation and FOV are unchanged.
 float minimum=1e30f,maximumDepth=0;for(auto object:{a,l,n}){auto lo=vector(object["bounds_min"]),hi=vector(object["bounds_max"]);for(unsigned k=0;k<8;++k){QVector3D p((k&1)?hi.x():lo.x(),(k&2)?hi.y():lo.y(),(k&4)?hi.z():lo.z());float z=-(view*QVector4D(p,1)).z();minimum=std::min(minimum,z);maximumDepth=std::max(maximumDepth,z);}}
 float nearPlane=std::max(.1f,minimum-1),farPlane=std::max(nearPlane+1,maximumDepth+1);projection.perspective(42,float(width)/height,nearPlane,farPlane);auto mvp=projection*view;auto normal=view.normalMatrix();
 auto prepareStart=Clock::now();Mesh&airway=cache.get(0,root.filePath(a["file"].toString()),a["vertices"].toInt(),1,QVector3D(.18,.86,.77),mvp,width,height);Mesh&nodule=cache.get(1,root.filePath(n["file"].toString()),n["vertices"].toInt(),1+airway.count/3,QVector3D(1,.34,.30),mvp,width,height);Mesh&lung=cache.get(2,root.filePath(l["file"].toString()),l["vertices"].toInt(),1+(airway.count+nodule.count)/3,QVector3D(.32,.55,.82),mvp,width,height);if(controls.colorMode){auto attributes=a["attributes"].toObject();check(!attributes["file"].toString().isEmpty(),"Requested airway analysis is unavailable");airway.loadAnalysis(root.filePath(attributes["file"].toString()));}double preparation=seconds(prepareStart);
 glViewport(0,0,width,height);glDisable(GL_BLEND);glDisable(GL_DITHER);glDisable(GL_CULL_FACE);struct DepthCleanup{GLuint value=0;~DepthCleanup(){if(value)glDeleteRenderbuffers(1,&value);}}depthCleanup;GLuint&depth=depthCleanup.value;glGenRenderbuffers(1,&depth);glBindRenderbuffer(GL_RENDERBUFFER,depth);glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24_OES,width,height);check(glGetError()==GL_NO_ERROR,"24-bit hardware depth buffer unavailable");
 auto shaderStart=Clock::now();unsigned idVariant=controls.clip?1:0,colorVariant=(controls.clip?1:0)+(controls.colorMode?2:0);
 bool shadersReused=bool(cache.identifierVariants[idVariant])&&bool(cache.colorVariants[colorVariant]);
 if(!cache.identifierVariants[idVariant])cache.identifierVariants[idVariant].reset(new Shader(controlledVertex(controls.clip,false),controlledId(controls.clip)));
 if(!cache.colorVariants[colorVariant])cache.colorVariants[colorVariant].reset(new Shader(controlledVertex(controls.clip,controls.colorMode),controlledColor(controls.clip,controls.colorMode)));
 auto&ids=*cache.identifierVariants[idVariant];auto&colors=*cache.colorVariants[colorVariant];
 matrix(ids,mvp,normal,width,height);matrix(colors,mvp,normal,width,height);setControls(ids,controls);setControls(colors,controls);double shaderSetup=seconds(shaderStart);
 QDir().mkpath(output);Atlas atlas;for(auto&image:atlas){image.reset(new Image(2*width,2*height,0));glBindFramebuffer(GL_FRAMEBUFFER,image->fbo);glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);}std::vector<std::unique_ptr<Peel>>peels;Peel opaque(width,height,depth);auto start=Clock::now();renderId(opaque,ids,airway,nodule,lung,true,atlas,0,nullptr,controls);renderColor(opaque,colors,airway,nodule,lung,true,nullptr,controls);double render=seconds(start);opaque.ids=opaque.identifier->read();if(needCPUcolors){auto cstart=Clock::now();opaque.pixels=opaque.color->read();colorReadback+=seconds(cstart);}save(output+"/opaque.rgba",opaque.pixels);save(output+"/opaque.ids",opaque.ids);
 QJsonArray layers;bool overflow=false;double idReadback=0;std::vector<uint32_t>count(width*height,0);
 for(unsigned i=0;controls.lung&&controls.opacityByte&&i<=32;++i){
  std::unique_ptr<Peel>p(new Peel(width,height,depth));start=Clock::now();std::unique_ptr<medical_tiles::Active>active;if(prune&&!peels.empty())active.reset(new medical_tiles::Active(peels.back()->ids,width,height));renderId(*p,ids,airway,nodule,lung,false,atlas,peels.size(),active.get(),controls);double duration=seconds(start);start=Clock::now();p->ids=p->identifier->read();idReadback+=seconds(start);unsigned hits=0;
  for(unsigned k=0;k<width*height;++k){uint32_t id=p->ids[k]&0xffffff;if(!id){check(p->ids[k]==0,"Invalid empty identifier");continue;}
   if((p->ids[k]>>24)!=255||id<lung.startId||id>=lung.startId+lung.count/3)throw std::runtime_error("Unexpected triangle identifier "+std::to_string(id)+" alpha "+std::to_string(p->ids[k]>>24)+" at pixel "+std::to_string(k)+" rank "+std::to_string(i+1)+" expected "+std::to_string(lung.startId)+".."+std::to_string(lung.startId+lung.count/3-1));for(auto&prior:peels)check((prior->ids[k]&0xffffff)!=id,"Repeated triangle at pixel");++hits;++count[k];
  }
  if(!hits)break;if(i==32){overflow=true;layers.append(QJsonObject{{"rank",int(i+1)},{"hits",int(hits)},{"overflow",true}});break;}
  start=Clock::now();glBindFramebuffer(GL_FRAMEBUFFER,p->identifier->fbo);glBindTexture(GL_TEXTURE_2D,atlas[i/4]->texture);glCopyTexSubImage2D(GL_TEXTURE_2D,0,(i%2)*width,((i%4)/2)*height,0,0,width,height);renderColor(*p,colors,airway,nodule,lung,false,active.get(),controls);duration+=seconds(start);if(needCPUcolors){auto cstart=Clock::now();p->pixels=p->color->read();colorReadback+=seconds(cstart);}
  if(needCPUcolors)for(unsigned k=0;k<width*height;++k)check((p->ids[k]!=0)==((p->pixels[k]>>24)!=0),"Selected mesh color coverage mismatch");
  save(output+QString("/lung_%1.rgba").arg(i+1),p->pixels);save(output+QString("/lung_%1.ids").arg(i+1),p->ids);layers.append(QJsonObject{{"rank",int(i+1)},{"hits",int(hits)},{"geometry_seconds",duration}});render+=duration;
  // The atlas retains identifiers on GPU; complete CPU captures retain the
  // oracle and culling inputs. Old layer FBOs/textures need no longer stay live.
  p->identifier.reset();peels.push_back(std::move(p));
 }
 check(!overflow,"Incomplete 32-layer medical extraction; PL composition refused");
 // Drop the 32-slot identifier atlas before allocating shared color planes.
 for(auto&image:atlas)image.reset();opaque.identifier.reset();
 std::vector<GLuint>liveTextures;std::vector<std::vector<uint32_t>>liveColors;if(needCPUcolors)liveColors.push_back(opaque.pixels);
 for(auto&p:peels){check(bool(p->color),"Medical color texture released early");liveTextures.push_back(p->color->texture);if(needCPUcolors)liveColors.push_back(p->pixels);}
 std::vector<uint32_t>livePL;auto live=medical_render::compose(context,width,height,opaque.color->texture,liveTextures,liveColors,&livePL,session);
 save(output+"/live_complete_PL.rgba",livePL);QJsonObject strongerPS;if(strongPS)strongerPS=medical_render::strongComparison(context,width,height,opaque.color->texture,liveTextures,liveColors,session);
 unsigned maximum=*std::max_element(count.begin(),count.end()),moreThanThree=std::count_if(count.begin(),count.end(),[](uint32_t x){return x>3;});
 glDisableVertexAttribArray(0);glDisableVertexAttribArray(1);glDisableVertexAttribArray(2);glDisableVertexAttribArray(3);glBindBuffer(GL_ARRAY_BUFFER,0);glFinish();glDeleteRenderbuffers(1,&depth);depth=0;struct rusage usage;getrusage(RUSAGE_SELF,&usage);
 QJsonArray vm,pm;for(int k=0;k<16;++k){vm.append(view.constData()[k]);pm.append(projection.constData()[k]);}
 return QJsonObject{{"controls",controls.json()},{"analysis_attributes_sha256",airway.analysisSHA},{"CPU_color_layer_readback_seconds",colorReadback},{"CPU_color_layer_captures_present",needCPUcolors},{"strong_PS_comparison",strongerPS},{"shader_cache_reused",shadersReused},{"shader_setup_seconds",shaderSetup},{"mesh_cache_hits",int(cache.hits)},{"mesh_cache_misses",int(cache.misses)},{"batch_vertices",int(medicalBatchVertices)},{"live_shared_composition",live},{"status","complete_extraction_and_live_composition_pending_geometry_oracle"},{"kind","actual_own_CT_GPU_medical_identifier_peeling"},{"scene",scenePath},{"scene_sha256",QString(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())},{"ct_sha256",scene["input_sha256"]},{"width",int(width)},{"height",int(height)},{"yaw_degrees",yaw},{"pitch_degrees",pitch},{"full_lung",full},{"view_column_major",vm},{"projection_column_major",pm},{"near_mm",nearPlane},{"far_mm",farPlane},{"mesh_sha256",QJsonObject{{"airway",airway.sha},{"nodule",nodule.sha},{"lung",lung.sha}}},{"triangles",QJsonObject{{"airway",int(airway.count/3)},{"nodule",int(nodule.count/3)},{"lung",int(lung.count/3)}}},{"lung_layers",layers},{"maximum_lung_layers_per_pixel",int(maximum)},{"pixels_exceeding_three_lung_layers",int(moreThanThree)},{"thirty_two_layer_overflow",overflow},{"gpu_geometry_seconds",render},{"readback_and_validation_excluded",true},{"identifier_readback_seconds",idReadback},{"preparation_seconds",preparation},{"screen_tile_culling",prune},{"submitted_triangles",double(airway.submitted+nodule.submitted+lung.submitted)},{"peak_rss_mib",double(usage.ru_maxrss)/1024},{"fragment_float_depth_comparison",false},{"depth_order_policy","24-bit fixed-function depth; exact byte triangle identifiers; rank keys"},{"board_PL_test",true},{"production_UI_replaced",false}};
}
static volatile sig_atomic_t stopRequested=0;
static void stopSignal(int){stopRequested=1;}
static void event(QJsonObject object){std::cout<<QJsonDocument(object).toJson(QJsonDocument::Compact).constData()<<"\n"<<std::flush;}
int main(int argc,char**argv){
 try{
  check(argc==3,"Usage: medical_composite_worker scene.json frame.rgba");
  QCoreApplication application(argc,argv);signal(SIGTERM,stopSignal);signal(SIGINT,stopSignal);
  Context context;MeshBank cache;medical_render::Session session(context);GLint units=0;glGetIntegerv(GL_MAX_TEXTURE_IMAGE_UNITS,&units);
  check(units>=8,"Eight fragment texture units required");medicalBatchVertices=96000;
  QString scene=QString::fromUtf8(argv[1]),frame=QString::fromUtf8(argv[2]);
  QTemporaryDir scratch(QFileInfo(frame).absolutePath()+"/composite_worker_XXXXXX");check(scratch.isValid(),"Private frame staging directory unavailable");
  event({{"event","ready"},{"protocol",1},{"native_worker",true}});
  std::string line;
  while(!stopRequested&&std::getline(std::cin,line)){
   QJsonParseError error;auto document=QJsonDocument::fromJson(QByteArray::fromStdString(line),&error);
   check(error.error==QJsonParseError::NoError&&document.isObject(),"Invalid worker request");
   auto request=document.object();if(request["command"]=="stop")break;
   check(request["command"]=="frame","Unknown worker command");
   auto controls=FrameControls::parse(request);unsigned w=controls.width,h=controls.height;float yaw=controls.yaw,pitch=controls.pitch;
   bool full=controls.full;QString capture=controls.capture;
   captureEvidence=!capture.isEmpty();if(captureEvidence)check(!QFileInfo::exists(capture),"Fresh capture destination required");else capture=scratch.path();
   auto begin=Clock::now();auto report=run(scene,capture,w,h,full,yaw,pitch,true,context,cache,session,controls.benchmark,controls);
   // The immutable DMA library masks termination while hardware is active.
   // Re-arm cooperative handlers only after the fully completed frame.
   signal(SIGTERM,stopSignal);signal(SIGINT,stopSignal);
   if(captureEvidence)saveJson(capture+"/extraction.json",report);
   QFile pixels(capture+"/live_complete_PL.rgba");check(pixels.open(QIODevice::ReadOnly),"Completed medical frame unavailable");
   auto data=pixels.readAll();QSaveFile output(frame);check(output.open(QIODevice::WriteOnly)&&output.write(data)==data.size()&&output.commit(),"Worker frame publication failed");
   event({{"event","frame"},{"sequence",request["sequence"]},{"width",int(w)},{"height",int(h)},
    {"frame_path",frame},{"scene",scene},{"full_lung",full},{"yaw_degrees",yaw},{"pitch_degrees",pitch},
    {"round_trip_seconds",seconds(begin)},{"report",report},{"captured_evidence",capture},
    {"orientation_column_major",report["view_column_major"]},{"projection_column_major",report["projection_column_major"]}});
  }
  session.close();event({{"event","stopped"},{"normal_completion",true},{"surface_restored",true}});return 0;
 }catch(const std::exception&e){event({{"event","error"},{"text",e.what()}});return 1;}
}

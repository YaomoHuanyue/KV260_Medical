"""Derive the isolated dual-output C5 bridge from the unchanged formal host."""
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent;CORE=HERE.parent;ROOT=CORE.parents[2]

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    sys.path.insert(0,str(ROOT/'tools'));import project_storage
    project_storage.check(120_000_000)
    parent=ROOT/'dfx/medical/host_extended/ct_bridge.cpp';target=HERE/'ct_pool_bridge.cpp'
    assert not target.exists() and not (HERE/'derivation.json').exists()
    original=parent.read_text();text=original
    edits=[]
    def replace(before,after):
        nonlocal text
        assert text.count(before)==1,(before[:100],text.count(before));text=text.replace(before,after);edits.append([before,after])
    replace(' std::vector<std::vector<int8_t>> activation_luts;',
        ' std::vector<std::vector<int8_t>> activation_luts;\n std::vector<std::unique_ptr<xrt::bo>> pool_luts;')
    replace('output_pool.clear();quant_params.clear();weights.clear();',
        'output_pool.clear();quant_params.clear();pool_luts.clear();weights.clear();')
    replace(' std::vector<std::array<unsigned,5>> predicted_shape;',' std::vector<std::array<unsigned,6>> predicted_shape;')
    before='static int execute(void* handle,int id,const void* input,void* output,unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k,const int32_t* bias=nullptr,const float* scale=nullptr,float qscale=1,int zero=0,OutputBuffer* mapped=nullptr){'
    insert='''extern "C" unsigned ct_pool_abi(){return 0xc5000001u;}
extern "C" int ct_set_pool_lut(void* handle,int id,const int8_t* table){
 try{
  if(!handle||!table)throw std::runtime_error("Missing pool context or LUT");
  auto& c=*static_cast<Context*>(handle);
  std::lock_guard<std::recursive_mutex> operation(c.session->operation_mutex);
  if(!c.pl_quantization||id<0||size_t(id)>=c.weights.size())throw std::runtime_error("Invalid pool layer");
  if(c.activation_luts.size()>size_t(id)&&!c.activation_luts[id].empty())throw std::runtime_error("Pool must precede activation LUT");
  if(c.pool_luts.size()<=size_t(id))c.pool_luts.resize(id+1);
  if(c.pool_luts[id]){
   if(std::memcmp(c.pool_luts[id]->map<void*>(),table,256))throw std::runtime_error("Cannot change configured pool LUT");
   return 0;
  }
  auto b=std::make_unique<xrt::bo>(c.session->buffer(256,c.bo_flags));
  std::memcpy(b->map<void*>(),table,256);b->sync(XCL_BO_SYNC_BO_TO_DEVICE,256,0);c.pool_luts[id]=std::move(b);return 0;
 }catch(const std::exception& e){error=e.what();return -1;}
}
'''
    after=before.replace('OutputBuffer* mapped=nullptr)','OutputBuffer* mapped=nullptr,OutputBuffer* pooled=nullptr)')
    replace(before,insert+after)
    before='  size_t dma_inbytes=(inbytes+31)&~size_t(31);'
    after=before+'''
  const bool pooling=pooled!=nullptr;
  const size_t poolbytes=pooling?(((packets/4)+3)/4)*32:0;
  if(pooling){
   if(!quantized||!scale||!mapped||activation_lut||h<2||w<2||(h&1)||(w&1)||(co%8)||!input)
    throw std::runtime_error("Unsupported dual-output pool shape or quantization");
   if(pooled==mapped||pooled->owner!=&c||!pooled->leased||pooled->bo->size()<poolbytes)
    throw std::runtime_error("Invalid or aliased pooled output lease");
   if(c.pool_luts.size()<=size_t(id)||!c.pool_luts[id])throw std::runtime_error("Pool LUT was not configured");
   const uintptr_t source_begin=reinterpret_cast<uintptr_t>(input);
   if(source_begin+dma_inbytes<source_begin)throw std::runtime_error("Input range overflow");
   for(auto* buffer:{mapped,pooled}){
    const auto begin=reinterpret_cast<uintptr_t>(buffer->bo->map<void*>());
    if(source_begin<begin+buffer->bo->size()&&begin<source_begin+dma_inbytes)
     throw std::runtime_error("Pool input and output allocations overlap");
   }
  }
'''
    replace(before,after)
    before='  c.phases[6]=seconds(phase);'
    after='''  if(pooling){
   if(!c.skip_clean_sync||pooled->ps_written)pooled->bo->sync(XCL_BO_SYNC_BO_TO_DEVICE,poolbytes,0);
   else{c.skipped_sync[2]++;c.skipped_sync[3]+=poolbytes;}
  }
'''+before
    replace(before,after)
    replace('o.write_register(0x40,quantized?(activation_lut?2:1):0);','o.write_register(0x40,pooling?3:quantized?(activation_lut?2:1):0);')
    before='  if(r.read_register(0x20)!=h||v.read_register(0x38)!=co||o.read_register(0x20)!=packets||r.read_register(0x10)!=uint32_t(source->address())||v.read_register(0x14)!=uint32_t(c.weights[id].address()>>32))throw std::runtime_error("Control register readback mismatch");'
    after='''  if(pooling){
   ptr(o,0x60,pooled->bo->address());ptr(o,0x70,c.pool_luts[id]->address());o.write_register(0x80,(w<<16)|h);
   if(o.read_register(0x60)!=uint32_t(pooled->bo->address())||o.read_register(0x64)!=uint32_t(pooled->bo->address()>>32)||
      o.read_register(0x70)!=uint32_t(c.pool_luts[id]->address())||o.read_register(0x74)!=uint32_t(c.pool_luts[id]->address()>>32)||
      o.read_register(0x80)!=((w<<16)|h)||o.read_register(0x40)!=3)throw std::runtime_error("Pool register readback mismatch");
  }
'''+before
    replace(before,after)
    replace('  const std::array<unsigned,5> shape={h,w,ci,co,k};','  const std::array<unsigned,6> shape={h,w,ci,co,k,pooling?1u:0u};')
    before='  phase=Clock::now();target.sync(XCL_BO_SYNC_BO_FROM_DEVICE,outbytes,0);c.phases[4]=seconds(phase);'
    after='''  phase=Clock::now();target.sync(XCL_BO_SYNC_BO_FROM_DEVICE,outbytes,0);
  if(pooling)pooled->bo->sync(XCL_BO_SYNC_BO_FROM_DEVICE,poolbytes,0);
  c.phases[4]=seconds(phase);'''
    replace(before,after)
    replace('  if(mapped)mapped->ps_written=false;','  if(mapped)mapped->ps_written=false;\n  if(pooling)pooled->ps_written=false;')
    before='extern "C" double ct_last_phase(void* handle,unsigned index)'
    after='''extern "C" int ct_execute_pool_mapped(void* handle,int id,const void* input,void* output,void* pooled,
 unsigned h,unsigned w,unsigned ci,unsigned co,unsigned k,const int32_t* bias,const float* scale,float qscale,int zero){
 if(!handle||!output||!pooled||!bias||!scale||!(qscale>0)||!std::isfinite(qscale)||zero<-128||zero>127){error="Invalid pool outputs or quantization";return -1;}
 return execute(handle,id,input,nullptr,h,w,ci,co,k,bias,scale,qscale,zero,
  static_cast<OutputBuffer*>(output),static_cast<OutputBuffer*>(pooled));
}
'''+before
    replace(before,after)
    reverse=text
    for before,after in reversed(edits):assert reverse.count(after)==1;reverse=reverse.replace(after,before)
    assert reverse==original
    with target.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
    record=dict(status='dual_output_host_source_derived_not_hardware_qualified',parent=parent.relative_to(ROOT).as_posix(),
        parent_SHA256=sha(parent),literal_edits=edits,exact_original_reverse_verified=True,
        output=target.relative_to(ROOT).as_posix(),output_SHA256=sha(target),
        full_and_pooled_independent_leases_dirty_flush_completion_invalidate_and_no_extra_pool_DFX=True,
        original_DMA_active_buffer_retention_and_session_mutex_preserved=True,
        raw_bridge_requires_qualified_partial_hash_gate_in_Python_before_open=True,
        source_and_evidence_SHA256={p.relative_to(ROOT).as_posix():sha(p) for p in
            (Path(__file__),parent,ROOT/'dfx/medical/host_extended/shared_session.hpp',ROOT/'dfx/medical/host_extended/runtime.hpp',target)},
        PL_accessed=False,production_promoted=False,whole_goal_completed=False)
    with (HERE/'derivation.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
    print('PASS isolated dual-output host source; complete original bridge reverse verified',flush=True)

if __name__=='__main__':main()

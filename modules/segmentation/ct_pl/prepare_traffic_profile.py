"""Generate a diagnostic driver beside the release; production code stays intact."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];PL=ROOT/'ct_pl';OUT=PL/'build/bottleneck_profile'
OUT.mkdir(parents=True,exist_ok=False)
original=(PL/'xrt_bridge.cpp').read_text(encoding='utf8')
source=original
def replace(old,new):
    global source
    assert source.count(old)==1,old
    source=source.replace(old,new)
replace('#include "postprocess.hpp"','#include "postprocess.hpp"\n#include "traffic_monitor.hpp"')
replace('struct Context;','static volatile uint32_t* ct_profile_gpio_mapping=nullptr;\nstruct Context;')
replace('std::unique_ptr<xrt::device> device;','std::unique_ptr<CTTrafficMonitor> traffic;\n std::unique_ptr<xrt::device> device;')
replace('~Context(){writer.reset();','~Context(){traffic.reset();writer.reset();')
replace('  return ctx.release();','  if(const char* enabled=std::getenv("CT_PROFILE_COUNTERS")){\n   if(std::string(enabled)=="1"){\n    unsigned period=100;\n    if(const char* value=std::getenv("CT_PROFILE_SAMPLE_US")){char* end=nullptr;auto us=std::strtoul(value,&end,10);if(!*value||*end||us>10000)throw std::runtime_error("Invalid diagnostic sample period");period=unsigned(us);}\n    ctx->traffic=std::make_unique<CTTrafficMonitor>(period,ct_profile_gpio_mapping);\n   }\n  }\n  return ctx.release();')
replace('  auto start=Clock::now();o.write_register','  if(c.traffic)c.traffic->begin();\n  auto start=Clock::now();o.write_register')
replace('  c.phases[3]=c.last_seconds;','  c.phases[3]=c.last_seconds;\n  if(c.traffic)c.traffic->finish();')
source+='\nextern "C" unsigned ct_profile_read(void* handle,uint64_t* data,unsigned capacity){auto& c=*static_cast<Context*>(handle);return c.traffic?c.traffic->copy(data,capacity):0;}\n'
source+='extern "C" void ct_profile_set_gpio(void* mapping){ct_profile_gpio_mapping=static_cast<volatile uint32_t*>(mapping);}\n'
(OUT/'traffic_xrt.cpp').write_text(source,encoding='utf8',newline='\n')
hashes={'original_driver_sha256':hashlib.sha256((PL/'xrt_bridge.cpp').read_bytes()).hexdigest(),'diagnostic_driver_sha256':hashlib.sha256((OUT/'traffic_xrt.cpp').read_bytes()).hexdigest(),'monitor_header_sha256':hashlib.sha256((PL/'traffic_monitor.hpp').read_bytes()).hexdigest()}
(OUT/'sources.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf8')
print(json.dumps(hashes))

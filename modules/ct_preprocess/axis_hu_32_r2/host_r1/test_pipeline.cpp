#include "pipeline.hpp"
#include <atomic>
#include <chrono>
#include <iostream>
#include <vector>

static void check(bool value){if(!value)throw std::runtime_error("HU scheduler test failed");}
template<class F>static void refuses(F f){bool failed=false;try{f();}catch(const std::runtime_error&){failed=true;}check(failed);}
struct Job{unsigned id;};
struct Operations {
    unsigned active=0,waits=0,prepared=0,fail_prepare=0,fail_post=0,fail_validate=0;
    std::atomic<unsigned>validated{0};std::vector<unsigned>launches;
    void prepare_device(Job& job){check(!active);prepared++;if(job.id==fail_prepare)throw std::runtime_error("prepare");}
    void launch(Job& job)noexcept{active=job.id;launches.push_back(job.id);}
    void wait(Job& job)noexcept{if(active!=job.id)std::terminate();active=0;waits++;}
    void post_drain(Job& job){if(job.id==fail_post)throw std::runtime_error("post");}
    void validate(Job& job){std::this_thread::sleep_for(std::chrono::microseconds(10));if(job.id==fail_validate)throw std::runtime_error("validate");validated++;}
    [[noreturn]]void retain_active()noexcept{std::terminate();}
};

int main(){
    std::array<unsigned char,2048>memory{};
    auto span=[&](unsigned slot){return seed_overlap::Memory{{reinterpret_cast<uintptr_t>(memory.data()),128},{{
        {reinterpret_cast<uintptr_t>(memory.data()+256+slot*512),128},
        {reinterpret_cast<uintptr_t>(memory.data()+384+slot*512),32},
        {reinterpret_cast<uintptr_t>(memory.data()+416+slot*512),80}}}};};
    unsigned cases=0;
    for(unsigned order=0;order<2;order++)for(unsigned iteration=0;iteration<32;iteration++){
        Operations ops;hu_host::Pipeline<Job,Operations>p(ops);
        auto a=p.submit(span(0),[](unsigned){return std::make_shared<Job>(Job{1});});
        auto b=p.submit(span(1),[](unsigned){return std::make_shared<Job>(Job{2});});
        check(ops.waits==0&&ops.launches==std::vector<unsigned>{1}&&p.pending()==2);
        refuses([&]{p.submit(span(0),[](unsigned){return std::make_shared<Job>(Job{3});});});
        refuses([&]{p.collect(0);});check(ops.waits==0);
        bool foreign_failed=false;std::thread other([&]{try{p.collect(a);}catch(const std::runtime_error&){foreign_failed=true;}});other.join();check(foreign_failed&&ops.waits==0);
        if(order){p.collect(b);p.collect(a);}else{
            p.collect(a);check(ops.active==2&&ops.waits==1);
            p.collect(b);
        }
        p.drain();check(p.pending()==0&&ops.validated==2&&ops.waits==2&&ops.launches==std::vector<unsigned>({1,2}));cases++;
    }
    for(unsigned failure=0;failure<6;failure++){
        Operations ops;hu_host::Pipeline<Job,Operations>p(ops);
        if(failure==0)ops.fail_prepare=1;
        if(failure==1)ops.fail_prepare=2;
        if(failure==2)ops.fail_post=1;
        if(failure==3)ops.fail_post=2;
        if(failure==4)ops.fail_validate=1;
        if(failure==5)ops.fail_validate=2;
        auto a=p.submit(span(0),[](unsigned){return std::make_shared<Job>(Job{1});});
        if(failure==0){refuses([&]{p.collect(a);});p.drain();}
        else{
            auto b=p.submit(span(1),[](unsigned){return std::make_shared<Job>(Job{2});});
            if(failure==2||failure==4)refuses([&]{p.collect(a);});else p.collect(a);
            if(failure!=4)refuses([&]{p.collect(b);});else p.collect(b);
            p.drain();
        }
        check(!ops.active&&!p.pending());cases++;
    }
    {
        Operations ops;hu_host::Pipeline<Job,Operations>p(ops);
        auto a=p.submit(span(0),[](unsigned){return std::make_shared<Job>(Job{1});});
        refuses([&]{p.submit(span(1),[](unsigned)->std::shared_ptr<Job>{throw std::runtime_error("build");});});
        check(ops.waits==0&&p.pending()==1);p.collect(a);p.drain();cases++;
    }
    for(unsigned fail=0;fail<3;fail++){
        Operations ops;hu_host::Pipeline<Job,Operations>p(ops);ops.fail_prepare=fail==1?2:0;ops.fail_post=fail==2?1:0;
        p.submit(span(0),[](unsigned){return std::make_shared<Job>(Job{1});});
        p.submit(span(1),[](unsigned){return std::make_shared<Job>(Job{2});});
        if(fail)refuses([&]{p.drain();});else p.drain();check(!ops.active&&!p.pending());cases++;
    }
    for(unsigned output=0;output<3;output++){
        for(unsigned kind=0;kind<4;kind++){
            Operations ops;hu_host::Pipeline<Job,Operations>p(ops);
            auto a=span(0),b=span(1);
            if(kind==0){a.extra_input=a.writes[output];refuses([&]{p.submit(a,[](unsigned){return std::make_shared<Job>(Job{1});});});}
            if(kind==1){a.extra_input=b.writes[output];auto ticket=p.submit(a,[](unsigned){return std::make_shared<Job>(Job{1});});
                refuses([&]{p.submit(b,[](unsigned){return std::make_shared<Job>(Job{2});});});p.collect(ticket);}
            if(kind==2){b.extra_input=a.writes[output];auto ticket=p.submit(a,[](unsigned){return std::make_shared<Job>(Job{1});});
                refuses([&]{p.submit(b,[](unsigned){return std::make_shared<Job>(Job{2});});});p.collect(ticket);}
            if(kind==3){a.extra_input={~uintptr_t(0)-2,8};refuses([&]{p.submit(a,[](unsigned){return std::make_shared<Job>(Job{1});});});}
            p.drain();check(!ops.active&&!p.pending());cases++;
        }
    }
    check(cases==86);std::cout<<"PASS HU_NONBLOCKING_PIPELINE_86 actual waits only during collect/drain; both submits return before any completion\n";
}

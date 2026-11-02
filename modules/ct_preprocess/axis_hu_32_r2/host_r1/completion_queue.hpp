#pragma once
#include <array>
#include <cstdint>
#include <exception>
#include <future>
#include <limits>
#include <stdexcept>
#include <thread>

namespace seed_overlap {
// This scheduler owns CPU completion work only. The XRT caller must report
// hardware completion before publishing validation or releasing a slot.
struct Span {uintptr_t address=0;size_t bytes=0;};
struct Memory {Span input;std::array<Span,3> writes{};Span extra_input{};};
inline void require(bool condition,const char* text){if(!condition)throw std::runtime_error(text);}
inline void valid(Span a){require(!a.bytes||(a.address&&a.address<=std::numeric_limits<uintptr_t>::max()-a.bytes),"Null or wrapped pending range");}
inline bool overlap(Span a,Span b){valid(a);valid(b);return a.bytes&&b.bytes&&a.address<b.address+b.bytes&&b.address<a.address+a.bytes;}
inline void disjoint(const Memory& a,const Memory& b){
    for(auto write:a.writes){
        require(!overlap(write,b.input),"Pending write overlaps input");
        require(!overlap(write,b.extra_input),"Pending write overlaps model table");
        for(auto other:b.writes)require(!overlap(write,other),"Pending outputs overlap");
    }
    for(auto write:b.writes){require(!overlap(a.input,write),"Pending input overlaps output");require(!overlap(a.extra_input,write),"Pending model table overlaps output");}
}
class Queue {
    enum class Phase {free,prepared,dma,drained,validating};
    struct Slot {Phase phase=Phase::free;uint64_t ticket=0;Memory memory{};std::future<void> work;};
    std::array<Slot,2> slots;
    const std::thread::id owner=std::this_thread::get_id();
    uint64_t next=1;
    void check_owner()const{require(std::this_thread::get_id()==owner,"Wrong completion queue owner");}
    Slot& find(uint64_t ticket){for(auto& s:slots)if(s.phase!=Phase::free&&s.ticket==ticket)return s;throw std::runtime_error("Unknown completion ticket");}
    bool active_dma()const{for(const auto& s:slots)if(s.phase==Phase::dma)return true;return false;}
    void clear(Slot& s){s.work=std::future<void>{};s.memory=Memory{};s.ticket=0;s.phase=Phase::free;}
public:
    uint64_t reserve(const Memory& memory){
        check_owner();valid(memory.input);valid(memory.extra_input);
        for(size_t i=0;i<memory.writes.size();++i){
            valid(memory.writes[i]);require(!overlap(memory.input,memory.writes[i]),"Input overlaps output");
            require(!overlap(memory.extra_input,memory.writes[i]),"Model table overlaps output");
            for(size_t j=0;j<i;++j)require(!overlap(memory.writes[i],memory.writes[j]),"Outputs overlap");
        }
        Slot* free=nullptr;
        for(auto& s:slots){if(s.phase==Phase::free){if(!free)free=&s;}else disjoint(memory,s.memory);}
        require(free,"Two completion slots already occupied");require(next!=std::numeric_limits<uint64_t>::max(),"Completion ticket exhausted");
        free->memory=memory;free->ticket=next++;free->phase=Phase::prepared;return free->ticket;
    }
    unsigned index(uint64_t ticket){check_owner();return static_cast<unsigned>(&find(ticket)-slots.data());}
    void begin_dma(uint64_t ticket){check_owner();require(!active_dma(),"A hardware command is already active");auto& s=find(ticket);require(s.phase==Phase::prepared,"Command is not prepared");s.phase=Phase::dma;}
    void end_dma(uint64_t ticket){check_owner();auto& s=find(ticket);require(s.phase==Phase::dma,"Command was not active");s.phase=Phase::drained;}
    template<class Function>void publish(uint64_t ticket,Function function){
        check_owner();auto& s=find(ticket);require(s.phase==Phase::drained,"Hardware must drain before CPU validation");
        s.work=std::async(std::launch::async,function);s.phase=Phase::validating;
    }
    void cancel(uint64_t ticket){check_owner();auto& s=find(ticket);require(s.phase==Phase::prepared||s.phase==Phase::drained,"Cannot cancel DMA or validation");clear(s);}
    void collect(uint64_t ticket){
        check_owner();require(!active_dma(),"Hardware must drain before collecting");auto& s=find(ticket);
        require(s.phase==Phase::validating,"CPU validation was not published");
        try{s.work.get();}catch(...){clear(s);throw;}clear(s);
    }
    // The selected slot is drained, its worker owns only disjoint buffers,
    // and reserve() has already checked all cross-slot write ranges. Retain
    // collect()'s original global-DMA refusal for every original caller.
    void collect_completed(uint64_t ticket){
        check_owner();auto& s=find(ticket);
        require(s.phase==Phase::validating,"CPU validation was not published");
        try{s.work.get();}catch(...){clear(s);throw;}clear(s);
    }
    size_t pending()const{check_owner();size_t n=0;for(const auto& s:slots)n+=s.phase!=Phase::free;return n;}
    void drain(){
        check_owner();require(!active_dma(),"Hardware must drain before closing");
        for(const auto& s:slots)require(s.phase==Phase::free||s.phase==Phase::validating,"Unpublished completion cannot close");
        std::exception_ptr failure;
        for(auto& s:slots)if(s.phase==Phase::validating){try{collect(s.ticket);}catch(...){if(!failure)failure=std::current_exception();}}
        if(failure)std::rethrow_exception(failure);
    }
};
}

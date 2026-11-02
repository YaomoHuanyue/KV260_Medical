#include "completion_queue.hpp"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <iostream>
#include <string>

using namespace seed_overlap;
static unsigned negatives=0;
template<class Function>static void rejected(Function f,const char* expected){try{f();}catch(const std::runtime_error& e){require(std::string(e.what())==expected,"Wrong rejection reason");++negatives;return;}throw std::runtime_error("Invalid queue operation accepted");}
template<class T>static Span span(T& data){return Span{reinterpret_cast<uintptr_t>(&data),sizeof(data)};}

int main(){try{
    struct Buffer {std::array<uint64_t,16> input{},output{};std::array<uint64_t,8> status{};std::array<double,12> phases{};};
    std::array<Buffer,2> buffers;Queue queue;std::atomic<unsigned> checks{0};
    const auto owner=std::this_thread::get_id();
    auto memory=[&](unsigned slot){auto& b=buffers[slot];return Memory{span(b.input),{span(b.output),span(b.status),span(b.phases)}};};
    for(unsigned pair=0;pair<16000;++pair){
        std::array<uint64_t,2> tickets{};
        for(unsigned slot=0;slot<2;++slot){
            auto& b=buffers[slot];for(unsigned j=0;j<16;++j)b.input[j]=uint64_t(pair)*2654435761u+j+17;
            b.output.fill(0);b.status.fill(0);b.phases.fill(0);
            tickets[slot]=queue.reserve(memory(slot));require(queue.index(tickets[slot])==slot,"Wrong free slot");
            queue.begin_dma(tickets[slot]);queue.end_dma(tickets[slot]);
            queue.publish(tickets[slot],[&,slot]{auto& data=buffers[slot];require(std::this_thread::get_id()!=owner,"Validation ran on owner");
                std::copy(data.input.begin(),data.input.end(),data.output.begin());
                for(unsigned j=0;j<16;++j)require(data.output[j]==data.input[j],"Full completion output differs");
                data.status.fill(0x19283746);data.phases.fill(1);++checks;});
        }
        require(queue.pending()==2,"Queue not bounded to both slots");
        if(pair&1){queue.collect(tickets[1]);queue.collect(tickets[0]);}else{queue.collect(tickets[0]);queue.collect(tickets[1]);}
        require(queue.pending()==0,"Completion not released");
        for(const auto& b:buffers){require(std::all_of(b.status.begin(),b.status.end(),[](uint64_t x){return x==0x19283746;}),"Full status differs");
            require(std::all_of(b.phases.begin(),b.phases.end(),[](double x){return x==1;}),"Full phases differ");}
    }
    require(checks==32000,"Missing actual worker completions");
    auto a=queue.reserve(memory(0));
    rejected([&]{queue.reserve(memory(0));},"Pending outputs overlap");
    auto invalid=memory(1);invalid.writes[0]=span(buffers[0].input);
    rejected([&]{queue.reserve(invalid);},"Pending write overlaps input");
    invalid=memory(1);invalid.input=span(buffers[0].output);
    rejected([&]{queue.reserve(invalid);},"Pending input overlaps output");
    auto shared=memory(1);shared.input=span(buffers[0].input);auto b=queue.reserve(shared);
    rejected([&]{queue.reserve(Memory{});},"Two completion slots already occupied");
    rejected([&]{queue.publish(a,[]{});},"Hardware must drain before CPU validation");
    queue.begin_dma(a);
    rejected([&]{queue.begin_dma(b);},"A hardware command is already active");
    rejected([&]{queue.cancel(a);},"Cannot cancel DMA or validation");
    rejected([&]{queue.collect(b);},"Hardware must drain before collecting");
    rejected([&]{queue.drain();},"Hardware must drain before closing");
    queue.end_dma(a);queue.cancel(a);queue.cancel(b);
    rejected([&]{queue.collect(a);},"Unknown completion ticket");
    rejected([&]{queue.end_dma(b);},"Unknown completion ticket");
    invalid=memory(0);invalid.input=Span{std::numeric_limits<uintptr_t>::max()-2,8};
    rejected([&]{queue.reserve(invalid);},"Null or wrapped pending range");
    invalid=memory(0);invalid.input=Span{0,1};rejected([&]{queue.reserve(invalid);},"Null or wrapped pending range");
    invalid=memory(0);invalid.writes[0]=invalid.input;rejected([&]{queue.reserve(invalid);},"Input overlaps output");
    invalid=memory(0);invalid.writes[1]=invalid.writes[0];rejected([&]{queue.reserve(invalid);},"Outputs overlap");
    std::atomic<unsigned> foreign{0};std::thread other([&]{try{queue.pending();}catch(const std::runtime_error& e){if(std::string(e.what())=="Wrong completion queue owner")++foreign;}});other.join();
    require(foreign==1,"Wrong-thread operation accepted");
    a=queue.reserve(memory(0));b=queue.reserve(memory(1));
    queue.begin_dma(a);queue.end_dma(a);queue.publish(a,[]{throw std::runtime_error("Injected completed-validation failure");});
    queue.begin_dma(b);queue.end_dma(b);queue.publish(b,[&]{++checks;});
    rejected([&]{queue.drain();},"Injected completed-validation failure");
    require(queue.pending()==0&&checks==32001,"Failed validation did not drain the other slot");queue.drain();
    a=queue.reserve(Memory{});queue.cancel(a);
    std::cout<<"{\"complete_requests\":32000,\"actual_worker_completions\":32001,\"negative_cases\":"<<negatives+foreign
        <<",\"both_collection_orders_and_full_outputs_exact\":true,\"shared_readonly_input_allowed\":true,\"cross_slot_write_aliases_refused\":true"
        <<",\"exception_drains_other_completion\":true,\"all_CPU_workers_off_owner\":true,\"PL_accessed\":false}\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}

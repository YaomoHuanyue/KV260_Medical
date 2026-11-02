#pragma once
#include "completion_queue.hpp"
#include <memory>

namespace hu_host {
// A single caller owns XRT. Submission prepares a free BO set and can queue
// the second command without waiting for the first. collect() advances DMA
// and starts the prepared command before joining CPU completion work.
template<class Job,class Operations>class Pipeline {
    Operations& ops;
    seed_overlap::Queue queue;
    std::array<std::shared_ptr<Job>,2> jobs;
    uint64_t active=0,queued=0,rejected=0;
    std::exception_ptr rejection;

    void reject_queued(std::exception_ptr error) {
        if(!queued)return;
        const auto ticket=queued;const auto index=queue.index(ticket);
        queued=0;queue.cancel(ticket);jobs[index].reset();
        rejected=ticket;rejection=error;
    }
    void start_queued() {
        if(active||!queued)return;
        const auto ticket=queued;
        auto job=jobs[queue.index(ticket)];
        try {ops.prepare_device(*job);}
        catch(...) {reject_queued(std::current_exception());return;}
        queued=0;queue.begin_dma(ticket);active=ticket;
        ops.launch(*job); // Must retain buffers rather than throw after launch.
    }
    void finish_active() {
        if(!active)return;
        const auto ticket=active;
        auto job=jobs[queue.index(ticket)];
        ops.wait(*job); // Must not return while any engine is still active.
        queue.end_dma(ticket);active=0;
        std::exception_ptr failure;
        try{ops.post_drain(*job);}catch(...){failure=std::current_exception();}
        queue.publish(ticket,[this,job,failure]{
            if(failure)std::rethrow_exception(failure);
            ops.validate(*job);
        });
        if(failure)reject_queued(failure);else start_queued();
    }
public:
    explicit Pipeline(Operations& operations):ops(operations){}
    Pipeline(const Pipeline&)=delete;Pipeline& operator=(const Pipeline&)=delete;
    ~Pipeline(){if(active)ops.retain_active();}
    template<class Builder>uint64_t submit(const seed_overlap::Memory& memory,Builder build) {
        (void)queue.pending();
        seed_overlap::require(!rejected,"Collect the failed queued command before submitting");
        seed_overlap::require(!queued,"Two HU slots are already occupied");
        const auto ticket=queue.reserve(memory);const auto index=queue.index(ticket);
        try{jobs[index]=build(index);}catch(...){queue.cancel(ticket);throw;}
        queued=ticket;start_queued();return ticket;
    }
    void collect(uint64_t ticket) {
        (void)queue.pending();
        if(ticket&&ticket==rejected){auto error=rejection;rejected=0;rejection=nullptr;std::rethrow_exception(error);}
        const auto index=queue.index(ticket); // Validate before touching DMA.
        while(active && active!=ticket)finish_active();
        if(active==ticket)finish_active();
        // A preceding frame may reject this queued command during post-drain.
        if(ticket==rejected){auto error=rejection;rejected=0;rejection=nullptr;std::rethrow_exception(error);}
        try{queue.collect_completed(ticket);}catch(...){jobs[index].reset();throw;}
        jobs[index].reset();
    }
    size_t pending()const{return queue.pending()+(rejected?1:0);}
    void drain() {
        (void)queue.pending();
        while(active)finish_active();
        std::exception_ptr first=rejection;
        rejected=0;rejection=nullptr;
        try{queue.drain();}catch(...){if(!first)first=std::current_exception();}
        for(auto& job:jobs)job.reset();
        if(first)std::rethrow_exception(first);
    }
};
}

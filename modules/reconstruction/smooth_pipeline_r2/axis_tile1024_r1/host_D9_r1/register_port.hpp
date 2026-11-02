#pragma once
#include "driver.hpp"
#include <thread>

namespace smooth_d9 {
// Session is the existing exclusively locked medical-shell session, AFTER a
// separately qualified D9 partial switch. Memory supplies the already-uploaded
// immutable padded graph and an independent guarded 64-byte header BO.
// Keeping these types generic makes the actual MMIO sequence testable without
// replacing it in tests, and keeps XRT includes out of the protocol library.
template<class Session,class Memory>
class RegisterPort {
    Session& session;Memory& memory;
    uint32_t original_transactions=0;
    template<class IP>static void argument(IP& ip,unsigned offset,uint32_t value) {
        ip.write_register(offset,value);
        require(ip.read_register(offset)==value,"D9 static DMA argument readback mismatch");
    }
public:
    RegisterPort(Session& s,Memory& m):session(s),memory(m){}
    void preflight(Config config) {
        memory.validate(config);
        const auto state=session.gpio->read_register(8);
        require((state&0xff0f)==0xd900,"D9 active identity/isolation mismatch; C2 driver is incompatible");
        require(session.ip->read_register(0)&4,"D9 core not idle before start");
        require(session.reader->read_register(0)&4,"D9 reader not idle before start");
        require(session.writer->read_register(0)&4,"D9 writer not idle before start");
        require(session.ip->read_register(0xc0)==config.vertices&&session.ip->read_register(0xd0)==config.edges&&
                session.ip->read_register(0xe0)==config.iterations&&
                session.ip->read_register(0x30)==uint32_t(config.graph_address)&&
                session.ip->read_register(0x34)==uint32_t(config.graph_address>>32),
                "D9 programmed algorithm arguments disagree with stream owner");
        original_transactions=state>>16;
        const auto graph=memory.graph_address(),header=memory.header_address();
        require(graph==config.graph_address&&header&&header%64==0&&header<0x80000000ULL&&
                header<=0x80000000ULL-64,"D9 header physical range invalid");
        require(header+64<=graph||graph+uint64_t(config.beats())*64<=header,"D9 graph/header physical overlap");
        argument(*session.reader,0x10,uint32_t(graph));argument(*session.reader,0x14,uint32_t(graph>>32));
        argument(*session.reader,0x20,config.beats());
        argument(*session.writer,0x10,uint32_t(header));argument(*session.writer,0x14,uint32_t(header>>32));
        argument(*session.writer,0x20,1);
    }
    void arm_header(){session.writer->write_register(0,1);}
    void start_core(){session.ip->write_register(0,1);}
    void send_graph(uint64_t address,uint32_t beats) {
        require(address==memory.graph_address()&&beats>0,"D9 graph ownership changed");
        session.reader->write_register(0,1);
    }
    Poll poll() {
        const auto r=session.reader->read_register(0),w=session.writer->read_register(0),c=session.ip->read_register(0);
        return {bool(r&2),bool(r&4),bool(w&2),bool(w&4),bool(c&2),bool(c&4)};
    }
    std::array<uint32_t,16> read_header() {
        require(session.writer->read_register(0x28)==0,"D9 output AXIS sideband/framing failure");
        return memory.invalidate_and_copy_header();
    }
    void finish(uint32_t headers) {
        session.wait_status(0xffff0000,((original_transactions+headers)&65535)<<16);
        require((session.gpio->read_register(8)&0xff0f)==0xd900,"D9 identity changed during transaction");
        memory.check_guards();
    }
    void idle(){std::this_thread::sleep_for(std::chrono::microseconds(20));}
    [[noreturn]] void retain_active(const char* message){memory.retain_active(message);std::terminate();}
};
}

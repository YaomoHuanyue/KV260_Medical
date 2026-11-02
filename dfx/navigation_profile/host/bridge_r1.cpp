#include "runtime.hpp"
#include <array>
#include <cstdint>
#include <limits>

using namespace navigationprofile;
namespace {
constexpr size_t GUARD = 4096;
constexpr unsigned OUTPUT_WORDS = 8706;
constexpr unsigned MAX_INPUT_WORDS = 5 + 4096 + (4096 * 26 + 15) / 16;
constexpr unsigned char MARK = 0xa7;
thread_local std::string error;
struct Buffer {
    std::unique_ptr<xrt::bo> bo;
    size_t capacity = 0;
    std::vector<unsigned char> head, tail;
    void grow(Session& session, size_t bytes) {
        if (capacity >= bytes) return;
        require(bytes % 64 == 0, "Word alignment");
        bo = std::make_unique<xrt::bo>(session.buffer(bytes + 2 * GUARD, xrt::bo::flags::cacheable));
        capacity = bytes;
        head.resize(GUARD);
        tail.resize(GUARD);
    }
    uint64_t address() const { return bo->address() + GUARD; }
    void prepare(const void* source, size_t bytes) {
        auto* mapped = bo->map<unsigned char*>();
        std::memset(mapped, MARK, GUARD);
        std::memset(mapped + GUARD + capacity, MARK, GUARD);
        if (source) std::memcpy(mapped + GUARD, source, bytes);
        else std::memset(mapped + GUARD, 0xdb, capacity);
        bo->sync(XCL_BO_SYNC_BO_TO_DEVICE, capacity + 2 * GUARD, 0);
    }
    void check_full_guards() {
        bo->sync(XCL_BO_SYNC_BO_FROM_DEVICE, GUARD, 0);
        bo->sync(XCL_BO_SYNC_BO_FROM_DEVICE, GUARD, GUARD + capacity);
        auto* mapped = bo->map<const unsigned char*>();
        std::memcpy(head.data(), mapped, GUARD);
        std::memcpy(tail.data(), mapped + GUARD + capacity, GUARD);
        require(std::all_of(head.begin(), head.end(), [](unsigned char v) { return v == MARK; }) &&
                std::all_of(tail.begin(), tail.end(), [](unsigned char v) { return v == MARK; }),
                "Full 4096-byte DMA guard damaged");
    }
};
struct Handle {
    Session session;
    Buffer input, output;
};
void pointer(xrt::ip& ip, uint64_t address) {
    require(address % 64 == 0, "DMA address alignment");
    ip.write_register(0x10, uint32_t(address));
    ip.write_register(0x14, uint32_t(address >> 32));
    require(ip.read_register(0x10) == uint32_t(address) &&
            ip.read_register(0x14) == uint32_t(address >> 32), "DMA pointer readback");
}
}

extern "C" const char* profile_error_r1() { return error.c_str(); }
extern "C" void* profile_open_r1() {
    try { return new Handle(); }
    catch (const std::exception& e) { error = e.what(); return nullptr; }
}
extern "C" void profile_close_r1(void* raw) { delete static_cast<Handle*>(raw); }
extern "C" int profile_restore_r1(void* raw) {
    try {
        require(raw, "Profile handle");
        auto& s = static_cast<Handle*>(raw)->session;
        std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);
        s.select("mc"); s.echo(); s.select("scope");
        return 0;
    } catch (const std::exception& e) { error = e.what(); return -1; }
}
extern "C" int profile_transfer_r1(void* raw, const uint64_t* source, uint64_t* target,
                                   unsigned input_words, unsigned operation,
                                   uint32_t* core_status, double* phases) {
    try {
        require(raw && source && target && core_status && phases, "Profile pointers");
        require(input_words && input_words <= MAX_INPUT_WORDS && operation <= 1, "Profile transfer bounds");
        if (operation == 0) require(input_words >= 5, "Complete scene header required");
        else require(input_words >= 2 && input_words <= 65, "Complete query bounds");
        auto total = Clock::now();
        auto& handle = *static_cast<Handle*>(raw);
        auto& s = handle.session;
        std::lock_guard<std::recursive_mutex> lock(s.operation_mutex);
        std::fill(phases, phases + 10, 0.);
        auto stage = Clock::now();
        handle.input.grow(s, size_t(input_words) * 64);
        handle.output.grow(s, size_t(OUTPUT_WORDS) * 64);
        phases[0] = seconds(stage); stage = Clock::now();
        handle.input.prepare(source, size_t(input_words) * 64);
        handle.output.prepare(nullptr, size_t(OUTPUT_WORDS) * 64);
        phases[1] = seconds(stage);
        s.select("profile"); phases[2] = s.load_seconds; phases[3] = s.switch_seconds;
        require(s.reader->read_register(0) & 4, "Static reader not idle");
        require(s.writer->read_register(0) & 4, "Static writer not idle");
        require(s.ip->read_register(0) & 4, "Profile core not idle");
        pointer(*s.reader, handle.input.address()); pointer(*s.writer, handle.output.address());
        s.reader->write_register(0x20, input_words);
        s.writer->write_register(0x20, OUTPUT_WORDS);
        s.arg(0x10, operation); s.arg(0x18, input_words);
        s.arg(0x20, operation == 0 ? 1 : OUTPUT_WORDS);
        unsigned transactions = s.gpio->read_register(8) >> 16;
        {
            SignalGuard signals;
            stage = Clock::now();
            try {
                s.writer->write_register(0, 1); s.ip->write_register(0, 1); s.reader->write_register(0, 1);
                bool rd = false, wd = false, cd = false;
                while (!rd || !wd || !cd) {
                    if (!rd) rd = s.reader->read_register(0) & 2;
                    if (!wd) wd = s.writer->read_register(0) & 2;
                    if (!cd) cd = s.ip->read_register(0) & 2;
                    if (seconds(stage) > 60) retain("Profile DMA/core completion timeout");
                    if (!rd || !wd || !cd) std::this_thread::sleep_for(std::chrono::microseconds(20));
                }
            } catch (const std::exception& e) { retain(e.what()); }
            phases[4] = seconds(stage);
        }
        require(s.writer->read_register(0x28) == 0, "Profile output AXIS framing");
        s.wait_status(0xffff0000, ((transactions + 1) & 65535) << 16);
        *core_status = s.ip->read_register(0x28);
        stage = Clock::now();
        handle.input.check_full_guards(); handle.output.check_full_guards();
        handle.output.bo->sync(XCL_BO_SYNC_BO_FROM_DEVICE, OUTPUT_WORDS * 64, GUARD);
        phases[5] = seconds(stage); stage = Clock::now();
        auto* mapped = handle.output.bo->map<const unsigned char*>();
        std::memcpy(target, mapped + GUARD, OUTPUT_WORDS * 64);
        require(uint32_t(target[0]) == *core_status, "Profile control/output status mismatch");
        phases[6] = seconds(stage); phases[7] = seconds(total);
        return 0;
    } catch (const std::exception& e) { error = e.what(); return -1; }
}

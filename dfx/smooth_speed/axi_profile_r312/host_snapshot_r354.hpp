#pragma once
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <thread>

namespace medical_profile {
// These indices are the frozen RTL ABI, not a partition of execution time.
enum Counter : unsigned {
    observation_cycles, read_bursts, read_beats, read_requested_bytes,
    read_address_backpressure_cycles, read_response_gap_cycles,
    read_data_backpressure_cycles, write_bursts, write_beats, write_enabled_bytes,
    write_address_backpressure_cycles, write_data_backpressure_cycles,
    write_response_backpressure_cycles, response_errors,
    maximum_pending_reads, maximum_pending_writes
};
constexpr std::array<const char*,16> names{{
    "observation_cycles", "read_bursts", "read_beats", "read_requested_bytes",
    "read_address_backpressure_cycles", "read_response_gap_cycles",
    "read_data_backpressure_cycles", "write_bursts", "write_beats", "write_enabled_bytes",
    "write_address_backpressure_cycles", "write_data_backpressure_cycles",
    "write_response_backpressure_cycles", "response_errors",
    "maximum_pending_reads", "maximum_pending_writes"
}};
struct Snapshot {
    std::array<std::uint64_t,16> counts{};
    // This window includes host start/stop latency. Keep kernel/API timing separate.
    double observation_seconds(double actual_clock_hz) const {
        if (!std::isfinite(actual_clock_hz) || actual_clock_hz <= 0)
            throw std::invalid_argument("Actual PL clock frequency required");
        return static_cast<double>(counts[observation_cycles]) / actual_clock_hz;
    }
    double cycle_fraction(Counter field) const {
        if (field!=observation_cycles && field!=read_address_backpressure_cycles &&
            field!=read_response_gap_cycles && field!=read_data_backpressure_cycles &&
            field!=write_address_backpressure_cycles && field!=write_data_backpressure_cycles &&
            field!=write_response_backpressure_cycles)
            throw std::invalid_argument("A cycle fraction requires a cycle counter");
        if (!counts[observation_cycles]) throw std::runtime_error("Empty observation window");
        // Different channels can wait in the same cycle; fractions must not be added
        // or subtracted from one to invent a 'compute time'.
        return static_cast<double>(counts[field])/static_cast<double>(counts[observation_cycles]);
    }
};

// Registers supplies read_register/write_register. There is no hardware opener
// or bitstream loader here. The caller must verify the profiled partial's hash,
// select C2, and hold Session::operation_mutex for the complete start/run/stop.
// Default release construction is disabled and performs absolutely no MMIO.
template<class Registers> class OptionalProfile {
    Registers& registers;
    bool enabled, started=false;
    std::chrono::milliseconds timeout;
    static void require(bool ok,const char* message) {
        if (!ok) throw std::runtime_error(message);
    }
    void state(std::uint32_t expected) {
        const auto deadline=std::chrono::steady_clock::now()+timeout;
        for (;;) {
            const auto current=registers.read_register(0xf00c);
            require((current&~3u)==0,"Unknown diagnostic status bits");
            if (current==expected) return;
            require(std::chrono::steady_clock::now()<deadline,"Diagnostic status timeout");
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
    }
    void no_pending() {
        require(registers.read_register(0xf010)==0 && registers.read_register(0xf014)==0,
                "Diagnostic window has outstanding AXI transactions");
    }
public:
    explicit OptionalProfile(Registers& io,bool test_build=false,
            std::chrono::milliseconds status_timeout=std::chrono::milliseconds(100))
        :registers(io),enabled(test_build),timeout(status_timeout) {
        if (!enabled) return;
        require(timeout.count()>0,"Positive diagnostic status timeout required");
        require(registers.read_register(0xf004)==0x4d415850u,"Profiled partial ABI magic mismatch");
        require(registers.read_register(0xf008)==0x00011040u,"Profiled partial ABI capability mismatch");
        const auto current=registers.read_register(0xf00c);
        require(current==0 || current==2,"Profiled partial already active or unknown status");
    }
    bool start(bool medical_kernel_idle) {
        if (!enabled) return false;
        require(medical_kernel_idle && !started,"Start profiling only for an idle medical kernel");
        const auto current=registers.read_register(0xf00c);
        require(current==0 || current==2,"Another diagnostic observation is active");
        no_pending();
        registers.write_register(0xf000,1);
        state(1);started=true;return true;
    }
    Snapshot stop() {
        if (!enabled) return {};
        require(started,"No diagnostic observation was started");
        registers.write_register(0xf000,2);
        state(2);no_pending();
        Snapshot result;
        for (unsigned j=0;j<16;++j) {
            const auto low=registers.read_register(0xf020+j*8);
            const auto high=registers.read_register(0xf024+j*8);
            result.counts[j]=std::uint64_t(low) | (std::uint64_t(high)<<32);
        }
        // Frozen counters are coherent only while no other operation restarts
        // the observer; caller ownership is essential, including against ABA.
        require(registers.read_register(0xf00c)==2,"Diagnostic snapshot was restarted while reading");
        no_pending();started=false;return result;
    }
};
}

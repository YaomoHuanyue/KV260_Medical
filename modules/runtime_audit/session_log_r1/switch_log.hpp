#pragma once
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>

namespace medical_log {
// Separate every process AND every session. O_EXCL prevents an old audit from
// being truncated even if a PID, timestamp or session counter is reused.
inline std::filesystem::path open_switch_log(std::ofstream& output,
        const std::filesystem::path& directory, const std::string& prefix) {
    if (output.is_open() || prefix.empty() || prefix.size()>80 ||
        prefix.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")!=std::string::npos)
        throw std::runtime_error("Invalid DFX log destination or prefix");
    if (std::filesystem::is_symlink(directory) || !std::filesystem::is_directory(directory))
        throw std::runtime_error("DFX log directory must already exist");
    static std::atomic<unsigned long long> sequence{0};
    auto stamp=std::chrono::steady_clock::now().time_since_epoch().count();
    for (unsigned attempt=0;attempt<64;++attempt) {
        auto name=prefix+"_"+std::to_string(stamp)+"_"+std::to_string(sequence.fetch_add(1))+"_"+std::to_string(getpid())+".csv";
        auto path=directory/name;
        int descriptor=::open(path.string().c_str(),O_CREAT|O_EXCL|O_WRONLY,0600);
        if (descriptor<0) {
            if (errno==EEXIST) continue;
            throw std::runtime_error("Cannot create owned DFX session log");
        }
        if (::close(descriptor)!=0) throw std::runtime_error("Cannot close new DFX session log");
        output.open(path,std::ios::out|std::ios::app|std::ios::binary);
        if (!output) throw std::runtime_error("Cannot open owned DFX session log");
        output<<"switch,rm,partial_ms,switch_ms,static_transactions,sentinel_address\n";
        output.flush();
        if (!output) throw std::runtime_error("Cannot write DFX session log header");
        return path;
    }
    throw std::runtime_error("Cannot obtain a unique DFX session log");
}
}

#pragma once
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <regex>
#include <stdexcept>
#include <string>

// Must run before constructing an XRT device: a different metadata UUID can
// trigger the board's known ZOCL teardown failure even for identical hardware.
inline void require_package_identity(const std::filesystem::path& metadata,
    const std::filesystem::path& manifest,const std::filesystem::path& marker,
    const std::filesystem::path& installed_metadata){
    std::ifstream mf(manifest),loaded(marker);
    std::string contents((std::istreambuf_iterator<char>(mf)),{}),active;
    std::getline(loaded,active);
    std::smatch digest;
    if(!mf||!loaded||!std::regex_search(contents,digest,
        std::regex("\"bit_bin_sha256\"\\s*:\\s*\"([0-9a-f]{64})\""))||active!=digest[1].str())
        throw std::runtime_error("Loaded bit hash does not match package; no XRT device or registers accessed");
    std::ifstream a(metadata,std::ios::binary),b(installed_metadata,std::ios::binary);
    if(!a||!b||!std::equal(std::istreambuf_iterator<char>(a),std::istreambuf_iterator<char>(),
        std::istreambuf_iterator<char>(b),std::istreambuf_iterator<char>()))
        throw std::runtime_error("Loaded metadata identity does not match package; no XRT device or registers accessed");
}
inline void require_loaded_smooth_package(const std::filesystem::path& metadata){
    require_package_identity(metadata,metadata.parent_path()/"manifest.json",
        "/run/kv260-mc-loaded.sha256",
        std::filesystem::path("/lib/firmware/xilinx/kv260-mc-smooth-v1")/metadata.filename());
}

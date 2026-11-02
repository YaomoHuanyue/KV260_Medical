#include "hu_axis.hpp"
#include <array>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool ok) { if (!ok) throw std::runtime_error("HU AXIS mismatch"); }

static void run_case(const std::array<uint8_t,1401>& table, uint32_t n,
                     unsigned mutation=0, unsigned mutation_word=0) {
    HuAxisStream input, output;
    HuMemoryWord memory[hu_axis::MEMORY_WORDS]{};
    const uint32_t words=n/32+(n%32!=0), out_words=n/64+(n%64!=0);
    for (unsigned i=0;i<table.size();++i) memory[i/16].range(8*(i%16)+7,8*(i%16))=table[i];
    for (unsigned i=1401;i<1408;++i) memory[i/16].range(8*(i%16)+7,8*(i%16))=0x9a;
    for (uint32_t i=0;i<words;++i) {
        HuAxisWord word{};
        word.keep=word.strb=~uint64_t(0);word.user=i==0;word.last=i+1==words;
        for(unsigned lane=0;lane<32;++lane) {
            uint16_t bits=uint16_t(i*32+lane); // All signed patterns, including endpoints.
            word.data.range(16*lane+15,16*lane)=bits;
        }
        if (i==mutation_word) {
            if(mutation&1)word.keep=uint64_t(word.keep)^1;
            if(mutation&2)word.strb=uint64_t(word.strb)^1;
            if(mutation&4)word.user=!bool(word.user);
            if(mutation&8)word.last=!bool(word.last);
        }
        input.write(word);
    }
    ct_hu_axis(input,output,memory,n);
    require(input.empty());
    for(uint32_t i=0;i<out_words;++i) {
        require(!output.empty());const HuAxisWord word=output.read();
        require(uint64_t(word.keep)==~uint64_t(0)&&uint64_t(word.strb)==~uint64_t(0));
        require(bool(word.user)==(i==0)&&bool(word.last)==(i+1==out_words));
        for(unsigned lane=0;lane<64;++lane) {
            const uint32_t position=i*64+lane;
            const uint16_t bits=uint16_t(position);
            const int hu=bits<32768?int(bits):int(bits)-65536;
            const unsigned index=hu<=-1000?0:hu>=400?1400:unsigned(hu+1000);
            const uint8_t expected=position<n?table[index]:0;
            require(uint8_t(word.data.range(8*lane+7,8*lane))==expected);
        }
    }
    require(output.empty());
    for(unsigned i=0;i<1401;++i)require(uint8_t(memory[i/16].range(8*(i%16)+7,8*(i%16)))==table[i]);
    for(unsigned i=1401;i<1408;++i)require(uint8_t(memory[i/16].range(8*(i%16)+7,8*(i%16)))==0x9a);
    const uint32_t expected[8]={hu_axis::MAGIC,1,mutation,n,words,out_words,n,0};
    for(unsigned i=0;i<8;++i)require(uint32_t(memory[88+i/4].range(32*(i%4)+31,32*(i%4)))==expected[i]);
    std::cout<<"PASS HU_AXIS "<<n<<" "<<mutation<<" "<<mutation_word<<"\n";
}

int main() {
    const char* path=std::getenv("HU_AXIS_LUT_FILE");require(path!=nullptr);
    std::ifstream file(path,std::ios::binary);require(bool(file));
    std::array<uint8_t,1401> table{};file.read(reinterpret_cast<char*>(table.data()),table.size());
    require(file.gcount()==1401&&file.peek()==std::ifstream::traits_type::eof());
    const uint32_t sizes[]={0,1,2,7,8,15,16,17,31,32,33,63,64,65,95,96,97,127,128,129,1023,1024,1025,65535,65536,65537};
    for(uint32_t n:sizes)run_case(table,n);
    for(unsigned error=1;error<16;++error)for(unsigned beat:{0u,1u,3u})run_case(table,97,error,beat);
    for(unsigned n:{1u,33u,65u,1025u}) {
        std::array<uint8_t,1401> changed=table;
        for(unsigned i=0;i<changed.size();++i)changed[i]=uint8_t((i*37+n)&255);
        run_case(changed,n);run_case(table,n);
    }
    // Invalid dimensions must produce a report without reading any stream word.
    HuAxisStream input,output;HuMemoryWord memory[hu_axis::MEMORY_WORDS]{};
    ct_hu_axis(input,output,memory,hu_axis::MAX_VOXELS+1);
    require(input.empty()&&output.empty());
    const uint32_t invalid_expected[]={hu_axis::MAGIC,1,hu_axis::COUNT,hu_axis::MAX_VOXELS+1,0,0,hu_axis::MAX_VOXELS+1,0};
    for(unsigned i=0;i<8;++i)require(uint32_t(memory[88+i/4].range(32*(i%4)+31,32*(i%4)))==invalid_expected[i]);
    std::cout<<"PASS HU_AXIS_INVALID_COUNT\nPASS HU_AXIS_ALL_80\n";
    return 0;
}

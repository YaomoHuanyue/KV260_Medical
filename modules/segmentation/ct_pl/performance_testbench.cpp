// Shared numerical oracle. These larger tiles isolate throughput from startup.
// Use identical no-random-stall co-simulation settings for both implementations.
#define main ct_correctness_main
#include "testbench.cpp"
#undef main
int main(){try{
 test(8,16,5,8,3);
 test(8,16,8,8,3);
 test(8,16,16,16,3);
 test(8,16,32,32,3);
 test(8,16,64,64,3);
 test(8,16,8,3,1);
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}

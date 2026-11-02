// Preserve AXI/AXIS ordering across shapes, tails and repeated transactions.
#define main ct_original_test_main
#include "testbench.cpp"
#undef main
int main(){try{
 test(8,16,16,3,1);test(8,16,32,16,1);
 test(8,16,32,32,1);test(8,16,64,32,1);
 test(3,7,17,13,1);test(1,1,1,1,1);
 test(2,512,16,3,1);test(3,5,32,32,3);
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}

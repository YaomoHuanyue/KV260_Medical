#define main ct_original_test_main
#include "testbench.cpp"
#undef main
int main(){try{
 // Each channel group count, including packets crossing pixel boundaries and
 // final beats with 8/16/24 valid bytes. Also exercise odd spatial tails.
 for(unsigned ci:{1,9,17,25,33,41,49,57})test(1,3,ci,13,1);
 test(1,1,1,3,1);test(1,1,16,3,1);test(1,1,24,3,1);
 test(8,16,64,32,1);test(8,16,32,16,1);test(8,16,16,3,1);
 test(3,5,5,16,3);test(3,5,16,16,3);test(3,5,32,32,3);
 test(3,5,64,64,3);test(3,7,17,13,3);test(3,7,33,17,3);
 test(1,1,1,1,3);test(2,512,5,16,3);test(2,5,63,63,3);
 test(7,1,1,3,3);test(1,7,1,9,3);test(5,2,8,17,3);
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}

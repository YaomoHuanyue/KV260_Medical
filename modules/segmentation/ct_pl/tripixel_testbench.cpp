#define main ct_original_test_main
#include "testbench.cpp"
#undef main
int main(){try{
 // Both incomplete triples, exact triples, row crossings and channel tails.
 for(unsigned width:{1,2,3,4,5,7})test(1,width,16,17,3);
 for(unsigned ci:{1,5,8,17,32,33,63,64})test(3,5,ci,13,3);
 test(3,7,32,32,3);test(3,7,64,64,3);test(3,7,33,17,3);
 test(7,1,1,3,3);test(5,2,8,17,3);test(2,512,5,16,3);
 test(3,512,16,16,3);test(2,5,63,63,3);
 for(unsigned ci:{1,9,17,25,33,41,49,57})test(1,3,ci,13,1);
 test(8,16,64,32,1);test(8,16,32,16,1);test(8,16,16,3,1);
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}

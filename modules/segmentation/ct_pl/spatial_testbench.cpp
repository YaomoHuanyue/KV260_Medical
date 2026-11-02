// Real channel layouts, odd tails, frame boundaries and retained 1x1 path.
#define main ct_original_test_main
#include "testbench.cpp"
#undef main
int main(){try{
 test(8,16,5,16,3);test(8,16,16,16,3);
 test(8,16,32,16,3);test(8,16,32,32,3);
 test(3,5,64,64,3);test(3,7,17,13,3);
 test(3,7,33,17,3);test(1,1,1,1,3);
 test(2,512,5,16,3);test(2,5,63,63,3);
 test(8,16,16,3,1);test(8,16,64,32,1);
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}

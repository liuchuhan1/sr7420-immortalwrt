#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <sys/mman.h>
int main(void){int f=open("/dev/mem",O_RDONLY|O_SYNC);if(f<0)return 2;const unsigned char*p=mmap(0,4096,PROT_READ,MAP_SHARED,f,0xb52ff000);if(p==MAP_FAILED)return 3;p+=0xf00;uint32_t w[64];memcpy(w,p,256);printf("HANDOVER signature=%.8s stable=%u clocks=%08x rx_before=%08x,%08x tx_before=%08x,%08x irq_mask_before=%08x\n",p,w[2],w[3],w[4],w[5],w[6],w[7],w[8]);for(int i=0;i<19;i++)printf("HANDOVER_COUNTER offset=%03x before=%08x after=%08x\n",0xa8+i*4,w[12+i],w[32+i]);return memcmp(p,"SRWARMQ1",8)||w[2]!=1?4:0;}
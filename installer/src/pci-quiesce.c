#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
static const char *paths[]={"/sys/bus/pci/devices/0000:01:00.0/config","/sys/bus/pci/devices/0001:01:00.0/config"};
static uint16_t get16(unsigned char *p){return p[0]|((uint16_t)p[1]<<8);}
static int put16(int fd,unsigned off,uint16_t v){unsigned char b[2]={v,v>>8};return pwrite(fd,b,2,off)==2?0:-1;}
static int put32(int fd,unsigned off,uint32_t v){unsigned char b[4]={v,v>>8,v>>16,v>>24};return pwrite(fd,b,4,off)==4?0:-1;}
int main(int argc,char **argv){
 int fd[2]={-1,-1},cap[2]={0},i,save=-1,rc=1,modified=0;unsigned char before[2][256],after[256];
 int change=argc==3 && !strcmp(argv[1],"--quiesce");
 if(argc!=1 && !change){fprintf(stderr,"usage: pci-quiesce [--quiesce RAM_BACKUP_FILE]\n");return 2;}
 for(i=0;i<2;i++){
  fd[i]=open(paths[i],change?O_RDWR:O_RDONLY);if(fd[i]<0||pread(fd[i],before[i],256,0)!=256)goto fail;
  if(get16(before[i])!=0x17cb||get16(before[i]+2)!=0x1109){fprintf(stderr,"unexpected endpoint %d\n",i);goto fail;}
  unsigned c=before[i][0x34],hops=0;
  while(c>=0x40 && c<=0xf0 && hops++<48){if(before[i][c]==5){cap[i]=c;break;}c=before[i][c+1];}
  if(!cap[i]){fprintf(stderr,"requires MSI capability\n");goto fail;}
  printf("domain=%d command=%04x msi_ctrl=%04x cap=%02x\n",i,get16(before[i]+4),get16(before[i]+cap[i]+2),cap[i]);
 }
 if(!change){rc=0;goto out;}
 save=open(argv[2],O_CREAT|O_EXCL|O_WRONLY,0600);if(save<0||write(save,before,sizeof(before))!=sizeof(before))goto fail;close(save);save=-1;
 for(i=0;i<2;i++){
  modified=i+1;
  if(put16(fd[i],cap[i]+2,get16(before[i]+cap[i]+2)&~1U))goto fail;
  if(put16(fd[i],4,get16(before[i]+4)&~4U))goto fail;
 }
 usleep(200000);
 for(i=0;i<2;i++){
  if(pread(fd[i],after,256,0)!=256 || (get16(after+4)&4) || (get16(after+cap[i]+2)&1)){fprintf(stderr,"quiesce readback failed\n");goto fail;}
  printf("domain=%d bus_master=0 msi_enable=0 verified=1\n",i);
 }
 rc=0;goto out;
fail:
 perror("pci-quiesce");
 for(i=0;i<modified;i++){put16(fd[i],cap[i]+2,get16(before[i]+cap[i]+2));put16(fd[i],4,get16(before[i]+4));}
 if(modified)fprintf(stderr,"restored saved PCI command/MSI control after error\n");
out:
 for(i=0;i<2;i++)if(fd[i]>=0)close(fd[i]);if(save>=0)close(save);return rc;
}

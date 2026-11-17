// SPDX-License-Identifier: GPL-2.0-or-later
/* Import each device's own radio firmware, BDF and full calibration to USB.
 * Never reads flash directly or includes calibration in a public release. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#include <unistd.h>
static void die(const char *s){perror(s);exit(1);}
static unsigned char *readfile(const char *p,size_t *n){
 FILE *f=fopen(p,"rb");struct stat st;
 if(!f)die(p);if(fstat(fileno(f),&st)||st.st_size<=0||st.st_size>32*1024*1024)die("file size");
 *n=(size_t)st.st_size;unsigned char *b=malloc(*n);if(!b)die("malloc");
 if(fread(b,1,*n,f)!=*n||fgetc(f)!=EOF||ferror(f)||fclose(f))die("read");return b;
}
static void writeall(FILE *f,const void *b,size_t n){if(fwrite(b,1,n,f)!=n)die("write");}
static void u32(FILE *f,uint32_t x){unsigned char b[4]={x,x>>8,x>>16,x>>24};writeall(f,b,4);}
static size_t padded(size_t n){return (n+3)&~(size_t)3;}
static void tlv(FILE *f,uint32_t tag,const void *b,size_t n){
 const unsigned char zero[3]={0};u32(f,tag);u32(f,(uint32_t)n);writeall(f,b,n);writeall(f,zero,padded(n)-n);
}
static void closeout(FILE *f){if(fflush(f)||fsync(fileno(f))||fclose(f))die("flush");}
static void path(char *out,size_t n,const char *base,const char *name){if(snprintf(out,n,"%s/%s",base,name)>=(int)n){errno=ENAMETOOLONG;die("path");}}
static void copy(const char *src,const char *dst){
 size_t n,m;unsigned char *b=readfile(src,&n),*check=readfile(src,&m);
 if(n!=m||memcmp(b,check,n)){errno=EIO;die("source changed between reads");}free(check);
 FILE *f=fopen(dst,"wb");if(!f)die(dst);writeall(f,b,n);closeout(f);free(b);
 if(chmod(dst,0600))die(dst);
}
static uint32_t be32(const unsigned char *b){return (uint32_t)b[0]<<24|(uint32_t)b[1]<<16|(uint32_t)b[2]<<8|b[3];}
static void dtbmac(const char *dtb,const char *macpath){
 FILE *f=fopen(macpath,"r");unsigned x[6];unsigned char mac[6];
 if(!f||fscanf(f,"%x:%x:%x:%x:%x:%x",x,x+1,x+2,x+3,x+4,x+5)!=6)die("stock MAC");fclose(f);
 for(unsigned i=0;i<6;i++){if(x[i]>255)die("MAC range");mac[i]=(unsigned char)x[i];}
 if((mac[0]&1)||!(mac[0]|mac[1]|mac[2]|mac[3]|mac[4]|mac[5]))die("invalid MAC");
 size_t n;unsigned char *b=readfile(dtb,&n);if(n<40||be32(b)!=0xd00dfeed||be32(b+4)!=n)die("DTB header");
 uint32_t so=be32(b+8),ss=be32(b+12),slen=be32(b+32),len=be32(b+36);size_t pos=so,end=(size_t)so+len;unsigned changed=0;
 if(end>n||(size_t)ss+slen>n)die("DTB bounds");
 while(pos+4<=end){uint32_t t=be32(b+pos);pos+=4;
  if(t==1){size_t z=pos;while(pos<end&&b[pos])pos++;if(pos>=end)die("DTB node");pos=z+padded(pos-z+1);}
  else if(t==3){if(pos+8>end)die("DTB prop");uint32_t sz=be32(b+pos),off=be32(b+pos+4);pos+=8;
   if(off>=slen||pos+sz>end||!memchr(b+ss+off,0,slen-off))die("DTB prop bounds");
   if(!strcmp((char *)b+ss+off,"local-mac-address")){if(sz!=6)die("DTB MAC size");memcpy(b+pos,mac,6);changed++;}pos+=padded(sz);
  }else if(t==2||t==4)continue;else if(t==9)break;else die("DTB token");
 }
 if(changed!=1)die("expected one LAN MAC property");f=fopen(dtb,"wb");if(!f)die(dtb);writeall(f,b,n);closeout(f);free(b);
}
int main(int argc,char **argv){
 if(argc!=3&&argc!=5){fprintf(stderr,"Usage: %s STOCK_RADIO_DIR OUTPUT_RADIO_DIR [DTB STOCK_MAC_SYSFS]\n",argv[0]);return 2;}
 const char *src=argv[1],*dst=argv[2];char a[1024],b[1024];
 const char *required[]={"amss.bin","m3.bin","bdwlan.b01","bdwlan.b02","caldata_0.bin","caldata_1.bin","fw_ini_cfg.bin"};
 for(unsigned i=0;i<7;i++){path(a,sizeof(a),src,required[i]);if(access(a,R_OK))die(a);}
 if(mkdir(dst,0700)&&errno!=EEXIST)die(dst);
 path(b,sizeof(b),dst,"firmware-2.bin");FILE *fw=fopen(b,"wb");if(!fw)die(b);
 const unsigned char magic[16]="QCOM-ATH12K-FW";writeall(fw,magic,16);unsigned char features=3;tlv(fw,1,&features,1);
 for(unsigned i=0;i<2;i++){size_t n;path(a,sizeof(a),src,required[i]);unsigned char *data=readfile(a,&n);tlv(fw,i+2,data,n);free(data);}closeout(fw);chmod(b,0600);
 path(b,sizeof(b),dst,"board-2.bin");fw=fopen(b,"wb");if(!fw)die(b);const unsigned char bm[20]="QCA-ATH12K-BOARD";/* 17-byte magic including NUL, padded to four bytes. */writeall(fw,bm,20);
 const char *names[]={"bus=pci,qmi-chip-id=0,qmi-board-id=255,variant=zte-sr7420-2g","bus=pci,qmi-chip-id=0,qmi-board-id=255,variant=zte-sr7420-5g"};
 for(unsigned i=0;i<2;i++){size_t n;path(a,sizeof(a),src,required[i+2]);unsigned char *data=readfile(a,&n);u32(fw,0);u32(fw,(uint32_t)(8+padded(strlen(names[i]))+8+padded(n)));tlv(fw,0,names[i],strlen(names[i]));tlv(fw,1,data,n);free(data);}closeout(fw);chmod(b,0600);
 const char *out[]={"cal-pci-0001:01:00.0.bin","cal-pci-0000:01:00.0.bin","fw_ini_cfg.bin"};
 for(unsigned i=0;i<3;i++){path(a,sizeof(a),src,required[i+4]);path(b,sizeof(b),dst,out[i]);copy(a,b);}
 path(a,sizeof(a),src,"regdb.bin");if(!access(a,R_OK)){path(b,sizeof(b),dst,"regdb.bin");copy(a,b);}
 if(argc==5)dtbmac(argv[3],argv[4]);
 puts("Imported separate 2.4/5 GHz board data and full calibration from this device only");return 0;
}

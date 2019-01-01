//
//  main.c
//  ios_kdp_server
//
//  Created by tihmstar on 28.07.17.
//  Copyright © 2017 tihmstar. All rights reserved.
//

#include <stdio.h>
#include <stdint.h>


#define SERIAL_READ_MEM     'r'
#define SERIAL_ECHO         'e'
#define SERIAL_INIT_KDP     'i'
#define SERIAL_WRITE_MEM    'w'
#define SERIAL_EXECUTE      'x'


//KDP
char debuggerInitialized[] = "Serial Debugger initialized!\n";
char hello[] = "helloKDP";
char done[] = "doneKDP";
char shello[] = "helloPDK";
char sdone[] = "donePDK";
char initKDP[] = "initKDP";
char gotHello[] = "got hello message\n";
//--KDP

//opModes
char kbase[] = "kbase=";
char writeMemDone[] = "wroteData=";
char funcRet[] = "return=";
//--opModes

//Error
char modeerror[] = "error=mode error;";
char msgTooLong[] = "error=message too long;";
char unhexFail[] = "error=unhexlify failed;";
char notReadingMem[] = "error=not reading mem;";
char writeMemCancel[] = "error=not writing mem;";
char writeMemAbrt[] = "error=aborting writing mem;";
char badPtrOrSize[] = "error=bad pointer or size;";
char notEnoughData[] = "error=not enough data;";
char notExecFunc[] = "error=not executing function;";
char tooManyFuncArgs_unfinished[] = "error=too many function arguments, ignoring parameters starting from ";
//--Error



#ifdef DEBUG
unsigned char serial_getc_(){
    return getc(stdin);
}
int serial_putc(char c){
    return putc(c, stdout);
}
#else
unsigned char (*serial_getc_)() = (void*)0x41424344;
int (*serial_putc)(char) = (void*)0x51525354;
#endif

void serial_puts(const char *str);
void serial_write(char *str, size_t len);
char serial_getc();
void serial_read(unsigned char *buf, size_t len);
int readHello();
int readUntilDone(char *buf, uint32_t *readlen, uint32_t bufsize);
int unhexlify(char *hex, int size, char *output);
void hexlify(char *hex, int zahl, char *ouput);
uint32_t readmem(char *ptr, uint32_t size);
uint32_t writemem(char *ptr, char *data, uint32_t size);
void server();
char *unhexptr(char *hexptr);
void doInitKdp(uint32_t kernelbase);
uint32_t execFunc(char *func, uint8_t paramCnt, uint32_t params[paramCnt]);



void server(){
    uint32_t kernelBase = (uint32_t)__builtin_return_address(1);
    kernelBase = ((kernelBase-0xcd200)&0xffffff00);
    
    for (int i=0; i<100; i++) {
        serial_putc('A');
    }
    serial_putc('\n');
    serial_puts(debuggerInitialized);
    serial_puts(shello);
    doInitKdp(kernelBase);
    serial_puts(sdone);
    serial_putc('\n');
    
    char buffer[0x200];
    while (1) {
        uint32_t inlen = 0;
        if (!readHello()){
            continue;
        }
        serial_puts(gotHello);
        
        if (!readUntilDone(buffer, &inlen, sizeof(buffer))){
            serial_puts(shello);
            serial_putc('\n');
            serial_puts(msgTooLong);
            serial_puts(sdone);
            serial_putc('\n');
            continue;
        }
        inlen -= sizeof(done)-1; //only real message size
        
        serial_puts(shello);
        switch (buffer[0]) {
            case SERIAL_READ_MEM: //4B-where 4B-size
            {
                if (inlen >=17) {
                    char *ptr = (char*)unhexptr(&buffer[1]);
                    uint32_t s = (uint32_t)unhexptr(&buffer[9]);
                    if (ptr && s){
                        uint32_t red = readmem(ptr, s);
                        hexlify((char*)&red, 4, buffer);
                        serial_write(buffer, 8);
                        break;
                    }else{
                        serial_puts(badPtrOrSize);
                    }
                }else{
                    serial_puts(notEnoughData);
                }
                serial_puts(notReadingMem);
            }
                break;
            case SERIAL_WRITE_MEM: //4B-where 4B-size xB-what
            {
                if (inlen >=17) {
                    char *ptr = (char*)unhexptr(&buffer[1]);
                    uint32_t s = (uint32_t)unhexptr(&buffer[9]);
                    if (ptr && s){
                        if (inlen-17 >= s*2) {
                            uint32_t wrt = writemem(ptr, &buffer[17], s);
                            hexlify((char*)&wrt, 4, buffer);
                            serial_puts(writeMemDone);
                            serial_write(buffer, 8);
                            break;
                        }else{
                            serial_puts(notEnoughData);
                        }
                    }else{
                        serial_puts(badPtrOrSize);
                    }
                }else{
                    serial_puts(notEnoughData);
                }
                serial_puts(writeMemCancel);
            }
                break;
            case SERIAL_EXECUTE: //4B-where 1B-paramCnt xB-params
            {
                if (inlen >=1+(4+1)*2) {
                    char *ptr = (char*)unhexptr(&buffer[1]);
                    uint8_t paramCnt = 0;
                    if (!unhexlify(&buffer[9], 2, (char*)&paramCnt) || !ptr){
                        serial_puts(badPtrOrSize);
                    }else{
                        uint32_t params[paramCnt];
                        for (int i=0; i<paramCnt; i++) {
                            params[i] = (uint32_t)unhexptr(&buffer[11+8*i]);
                        }
                        uint32_t ret = execFunc(ptr, paramCnt, params);
                        serial_puts(funcRet);
                        hexlify((char*)&ret, 4, buffer);
                        serial_write(buffer, 8);
                        break;
                    }
                }else{
                    serial_puts(notEnoughData);
                }
                serial_puts(notExecFunc);
            }
                break;
            case SERIAL_ECHO: //repeates everything
                serial_write(buffer, inlen);
                break;
            case SERIAL_INIT_KDP:
                doInitKdp(kernelBase);
                break;
            default:
                serial_puts(modeerror);
                break;
        }
        serial_puts(sdone);
        serial_putc('\n');
    }
}

void doInitKdp(uint32_t kernelBase){
    char buf[8];
    serial_puts(initKDP);
    serial_puts(kbase);
    hexlify((char*)&kernelBase, 4, buf);
    serial_write(buf, 8);
    serial_putc('|');
}

char *unhexptr(char *hexptr){
    char *ptr;
    if(!unhexlify(hexptr, 8, (char*)&ptr)){
        *hexptr = '\0'; //signalize error
        serial_puts(unhexFail);
        serial_write(hexptr, 8);
        serial_putc('\n');
        return NULL;
    }
    return ptr;
}

void serial_puts(const char *str){
    char c;
    while ((c = *str++))
        serial_putc(c);
}

void serial_write(char *str, size_t len){
    while (len--)
        serial_putc((char)*str++);
}

char serial_getc(){
    unsigned char c;
    while ((c = serial_getc_()) == 0xff);
    return c;
}


void serial_read(unsigned char *buf, size_t len){
    while (len)
        if ((*buf = serial_getc_()) != 0xff)
            buf++,len--;
}

int readHello(){
    for (int i=0; i<sizeof(hello)-1; i++) {
        if (hello[i] != serial_getc())
            return 0;
    }
    return 1;
}

int readUntilDone(char *buf, uint32_t *readlen, uint32_t bufsize){
    *readlen = 0;
    while (*readlen < bufsize) {
        for (int i=0; i<sizeof(done)-1; i++) {
            if (*readlen >= bufsize)
                return 0;
            (*readlen)++;
            if ((*buf++ = serial_getc()) != done[i]){
                if (*readlen && buf[-2] == done[i] && buf[-1] == done[i+1])
                    i++;
                else
                    goto doneNotFound;
            }
        }
        return 1;
    doneNotFound:
        continue;
    }
    
    return 0;
}

int unhexlify(char *orig, int size, char *output){
    unsigned char *hex = (unsigned char*)orig;
    
    for (;size;output++) {
        if (size == 1)
            return 0;//ERROR parsing failed
        
        char c = (size--,*(hex++));
        if (c >= '0' && c<='9') {
            *output = c - '0';
        }else if (c >= 'a' && c <= 'f'){
            *output = 10 + c - 'a';
        }else if (c >= 'A' && c <= 'F'){
            *output = 10 + c - 'A';
        }else{
            return 0; //ERROR parsing failed
        }
        c = (size--,*(hex++));
        *output <<=4;
        if (c >= '0' && c<='9') {
            *output += c - '0';
        }else if (c >= 'a' && c <= 'f'){
            *output += 10 + c - 'a';
        }else if (c >= 'A' && c <= 'F'){
            *output += 10 + c - 'A';
        }else{
            return 0; //ERROR parsing failed
        }
    }
    return 1;
}

void hexlify(char *hex_, int zahl, char *ouput){
    unsigned char *hex = (unsigned char*)hex_;
    while (zahl--) {
        ouput[1] = *hex&0xf;
        ouput[1] += (ouput[1] < 10) ? '0' : 'a' - 10;
        
        ouput[0] = *hex>>4;
        ouput[0] += (ouput[0] < 10) ? '0' : 'a' - 10;
        ouput+=2;
        hex++;
    }
}

uint32_t readmem(char *ptr, uint32_t size){
    char recp[8];
    uint32_t read = 0;
    while (size >= 4){
        uint32_t mem = *(uint32_t*)ptr;
        hexlify((char*)&mem, 4, recp);
        serial_write(recp, 8);
        read+=4;
        ptr+=4;
        size-=4;
    }
    return read;
}

uint32_t writemem(char *ptr, char *data, uint32_t size){
    uint32_t write = 0;
    ptr-=4; //to match first pre-increment
    data-=8; //to match first pre-increment
    while (size >= 4){
        uint32_t mem = (uint32_t)unhexptr(data+=8); //pre-increment
        if (!mem && !*data){
            serial_puts(writeMemAbrt);
            return write;
        }
        *(uint32_t*)(ptr+=4) = mem;
        
        write+=4;
        size-=4;
    }
    if (size){
        uint32_t mem;
        if (!unhexlify((data+=8), size*2, (char*)&mem)){
            serial_puts(writeMemAbrt);
            return write;
        }
        mem <<= (4-size)*8;
        mem >>= (4-size)*8;
        uint32_t omem = *(uint32_t*)(ptr+=4);
        omem >>= size*8;
        omem <<= size*8;
        
        *(uint32_t*)ptr = omem | mem;
        write +=size;
    }
    return write;
}

uint32_t execFunc(char *func, uint8_t paramCnt, uint32_t params[paramCnt]){
#define MAX_FUNC_PARAMS     10
    uint32_t realParams[MAX_FUNC_PARAMS];
    for (int i=0; i<MAX_FUNC_PARAMS; i++) {
        realParams[i] = (i<paramCnt) ? params[i] : 0;
    }
    if (paramCnt > MAX_FUNC_PARAMS){
        serial_puts(tooManyFuncArgs_unfinished);
        serial_putc('1');
        serial_putc('0');
        serial_putc(';');
    }
    
    return ((uint32_t(*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))(func))
            (params[0],params[1],params[2],params[3],params[4],params[5],params[6],params[7],params[8],params[9]);
}

#ifdef DEBUG
int main(){
    server();
    return 0;
}
#endif









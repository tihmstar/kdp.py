#!/bin/bash

rm a.o*
xcrun -sdk iphoneos gcc -arch armv7 main.c -o a.o -c -fno-stack-protector 2>/dev/null
jtool -l a.o
jtool -e __TEXT.__text a.o >/dev/null 2>/dev/null
jtool -e __DATA.__data a.o >/dev/null 2>/dev/null
cat a.o.__TEXT.__text > raw.bin
if [ $1 ]; then
echo "filling $1 bytes"
for i in $(seq 1 $1); do
echo -e -n "\x00" >> raw.bin
done
fi
cat a.o.__DATA.__data >> raw.bin
xxd -i raw.bin 1>&2

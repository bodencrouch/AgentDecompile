"""Compatibility declarations shared by recovered-C compilation paths."""

PREAMBLE = """#ifndef NULL
#define NULL ((void*)0)
#endif
#define TRUE 1
#define FALSE 0
typedef unsigned char undefined;
typedef unsigned char byte;
typedef unsigned char uchar;
typedef int bool;
typedef unsigned short word;
typedef unsigned int dword;
typedef unsigned int size_t;
typedef long double float10;
"""

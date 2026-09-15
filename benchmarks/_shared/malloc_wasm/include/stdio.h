#ifndef MALLOC_GUEST_STDIO_H
#define MALLOC_GUEST_STDIO_H
#include <stddef.h>
typedef struct guest_FILE FILE;
extern FILE *stdin, *stdout, *stderr;
int printf(const char *, ...);
int fprintf(FILE *, const char *, ...);
int snprintf(char *, size_t, const char *, ...);
int puts(const char *);
#endif

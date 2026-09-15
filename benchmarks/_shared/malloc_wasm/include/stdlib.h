#ifndef MALLOC_GUEST_STDLIB_H
#define MALLOC_GUEST_STDLIB_H
#include <stddef.h>
_Noreturn void abort(void);
_Noreturn void exit(int);
void *malloc(size_t);
void free(void *);
void *calloc(size_t, size_t);
void *realloc(void *, size_t);
#endif

#include <stddef.h>

_Static_assert(sizeof(void *) == 8, "pointer width must be 64 bits");
_Static_assert(sizeof(size_t) == 8, "size_t width must be 64 bits");
_Static_assert(sizeof(long) == 8, "long width must be 64 bits");

void *memcpy(void *dst, const void *src, size_t n) {
    return __builtin_memcpy(dst, src, n);
}

void *memmove(void *dst, const void *src, size_t n) {
    return __builtin_memmove(dst, src, n);
}

void *memset(void *dst, int value, size_t n) {
    return __builtin_memset(dst, value, n);
}

int memcmp(const void *lhs, const void *rhs, size_t n) {
    const unsigned char *a = lhs, *b = rhs;
    for (size_t i = 0; i < n; ++i)
        if (a[i] != b[i])
            return (int)a[i] - (int)b[i];
    return 0;
}

size_t strlen(const char *text) {
    size_t n = 0;
    while (text[n])
        ++n;
    return n;
}

_Noreturn void abort(void) { __builtin_trap(); }
_Noreturn void exit(int status) {
    (void)status;
    __builtin_trap();
}

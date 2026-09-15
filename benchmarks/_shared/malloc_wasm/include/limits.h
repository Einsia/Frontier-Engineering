#ifndef MALLOC_GUEST_LIMITS_H
#define MALLOC_GUEST_LIMITS_H
#define CHAR_BIT 8
#define INT_MAX __INT_MAX__
#define INT_MIN (-INT_MAX - 1)
#define UINT_MAX (__INT_MAX__ * 2U + 1U)
#define LONG_MAX __LONG_MAX__
#define LONG_MIN (-LONG_MAX - 1L)
#define ULONG_MAX (__LONG_MAX__ * 2UL + 1UL)
#endif

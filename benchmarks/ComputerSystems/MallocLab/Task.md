# Malloc Lab Experiment Explanation

## Experiment Requirements

* Write a C program for dynamic memory allocation.

* Include three functions: `malloc`, `free`, and `realloc`.

* Complete the assignment independently.

## Experiment Method

The experiment package is located at `benchmarks/ComputerSystems/MallocLab/malloclab-handout`.

* Only the `mm.c` file needs to be modified.

* Evaluation will be performed using `mdriver` (file name: `mdriver.c`).

* **Running Method:**

```bash
make
./mdriver -V
```

## Implementation of the Dynamic Memory Allocator

The following four functions need to be implemented (declared in `mm.h`, defined in `mm.c`):

```c
int mm_init(void);
void *mm_malloc(size_t size);
void mm_free(void *ptr);
void *mm_realloc(void *ptr, size_t size);
```
* The `mm.c` file contains the simplest implementation of the dynamic memory allocator, which can pass some test cases. You will need to modify the implementation of related functions to utilize heap space more efficiently.

### mm_init

* **Interface:** `int mm_init(void);`

* Before calling `mm_malloc`, `mm_realloc`, or `mm_free`, the program calls `mm_init` to perform all necessary initializations.

* Returns -1 if a problem occurs during initialization, and 0 if it completes normally.

* `mdriver` calls this function to initialize before each new trace test.

* Do not call `mem_init` from `memlib` within this function.

### mm_malloc

* **Interface:** `void *mm_malloc(size_t size);`

* Returns a pointer to a contiguous block of memory at least `size` bytes.

* The allocated memory block should be entirely within the heap and should not overlap with any other allocated blocks.

* If allocation is not possible, a new heap region should be requested by calling `void *mem_sbrk(int incr)`.

* This experiment was conducted in a 64-bit environment; therefore, according to the C language standard, it should be aligned to 16 bytes.

### mm_free

* **Interface:** `void mm_free(void *ptr);`

* Frees the memory block pointed to by `ptr`, with no return value. If `ptr` is `NULL`, this call does nothing.

* Guaranteed that `ptr` is the pointer previously returned by `malloc` or `realloc` and has not been freed.

### mm_realloc

* **Interface:** `void *mm_realloc(void *ptr, size_t size);`

* Changes the size of the memory block pointed to by `ptr` to `size` and returns a pointer to the changed memory block.

* The returned pointer points to a contiguous memory block of at least `size` bytes. The following requirements apply:

* If `ptr` is `NULL`, it's equivalent to calling `mm_malloc(size)`.

* If `size` is 0, it's equivalent to calling `mm_free(ptr)`.

* If `ptr` is not `NULL`, it must be the pointer previously returned by `malloc` or `realloc`, and it hasn't been freed. This call changes the size of the memory block pointed to by `ptr` (the old block) to `size` bytes and returns the address of the new block. The address of the new block can be the same as or different from the old block.

* The new block needs to copy the contents of the old block. The size is determined by the smaller of the two blocks. For example:

* If the old block is 8 bytes and the new block is 12 bytes, then the first 8 bytes will be copied.

* If the old block is 8 bytes and the new block is 4 bytes, then the first 4 bytes will be copied.

## Supporting Functions

The `memlib.c` package simulates a memory system for the dynamic memory allocator. You can call the following functions:

* `void *mem_sbrk(int incr)`: Expands the heap by `incr` bytes, where `incr` is a positive integer. This function returns a generic pointer to the first byte of the newly allocated heap. The semantics are the same as Unix's `sbrk`, except that `mem_sbrk` only accepts positive arguments.

* `void *mem_heap_lo(void)`: Returns a generic pointer to the first byte of the heap.

* `void *mem_heap_hi(void)`: Returns a generic pointer to the last byte of the heap.

* `size_t mem_heapsize(void)`: Returns the current size of the heap in bytes.

* `size_t mem_pagesize(void)`: Returns the system's page size in bytes. Linux uses 4KB.

## driver

* Used to test the correctness, space utilization, and throughput of functions in `mm.c`.

* Test traces are located in the `traces` folder.

* Usage can be viewed using `./mdriver -h`. `-V` can be used to locate the file where errors occur, and `-f` can be used to specify the trace for testing.

## Programming Rules

* Interface functions in `mm.c` must not be modified.

* Official scoring provides no file, network, process, standard-input, or clock interfaces.

* System allocation functions (`malloc`, `free`, `realloc`, `sbrk`, `mmap`) must not be called; obtain heap space through `mem_sbrk`. The runtime supports `memcpy`, `memmove`, `memset`, `memcmp`, and `strlen`.

* Global or static composite data structures, such as arrays, structures, trees, or lists, must not be defined in the `mm.c` program. However, global scalar variables, such as integers, floating-point numbers, and pointers, can be declared in `mm.c`.

* Returned memory blocks should be 16-byte aligned.

## Scoring Criteria

Official scoring uses a Wasm64 allocator and a trusted host driver. The host owns the traces, heap high-water mark, and score, and checks allocation bounds, alignment, overlap, and preserved data. Each passing trace is independently executed and validated ten times; throughput uses the median allocator-call time measured by the host. Compilation, runtime initialization, and host payload checks are excluded from call time. Failed traces contribute no utilization or completed operations.

See the task README for the scoring command. Native `mdriver` remains a local debugging tool; its timings are not directly comparable to isolated-runtime scores.

* Space Utilization: The ratio between the maximum amount of memory used by the program and the maximum heap size used by the allocator; the optimal ratio is 1.

* Throughput: Kops (kilo operations per second)

* Scoring Formula: $$P = 100\left(wU + (1-w)\min(1,T/T_{ref})\right)m/N$$

* Here $w=0.6$, $N=11$, $m$ is the number of passing traces, and $U$ is mean utilization across all traces (zero for failed traces). $T$ is completed operations divided by the sum of median call times for passing traces. The fixed reference cap is $T_{ref}=10{,}000{,}000$ operations/second. It is a score normalization constant, not a fresh measurement of native libc performance.

## Some Suggestions

* Use `mdriver -f` to simplify debugging with small files, such as `traces/short{1,2}-bal.rep`.

* Use `-v` and `-V` to view detailed output.

* Study every line of code in the malloc implementation in the book. This example implements a simple allocator based on an implicit free list.

* Encapsulating pointer arithmetic within C preprocessor macros (`#define`) can significantly reduce code complexity.

* The first 9 traces only include `malloc` and `free`, while the last two include `malloc`, `free`, and `realloc`. It is recommended to debug `realloc` only after `malloc` and `free` work correctly on the first 9 traces.

* `realloc` can be built on top of `malloc` and `free`, but to achieve very good performance, it needs to be designed separately.

/* Trusted Malloc Lab driver. Candidate code executes only in Wasm memory. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/random.h>
#include <time.h>
#include <wasmtime.h>

#define HEAP_START (4ULL << 20)
#define MAX_HEAP (20ULL << 20)
#define MEMORY_SIZE (HEAP_START + MAX_HEAP)
#define REPEATS 10
#define THROUGHPUT_CAP 10000000.0
static const char *traces[] = {
    "amptjp-bal.rep",  "cccp-bal.rep",       "cp-decl-bal.rep",
    "expr-bal.rep",    "coalescing-bal.rep", "random-bal.rep",
    "random2-bal.rep", "binary-bal.rep",     "binary2-bal.rep",
    "realloc-bal.rep", "realloc2-bal.rep"};
static wasm_engine_t *engine;
static atomic_bool watchdog_done;
static char failure[1024];

typedef struct {
  char kind;
  unsigned id;
  uint64_t size;
} operation;
typedef struct {
  size_t nids, nops;
  operation *ops;
} trace;
typedef struct {
  uint64_t offset, size;
  uint8_t *expected;
  int live;
} block;
typedef struct {
  wasmtime_store_t *store;
  wasmtime_context_t *context;
  wasmtime_memory_t memory;
  wasmtime_func_t init, alloc, release, resize;
  uint64_t brk;
  int ready;
  double call_seconds;
} guest;

static void die(const char *message) {
  fprintf(stderr, "%s\n", message);
  exit(2);
}
static void *checked_calloc(size_t n, size_t s) {
  void *p = calloc(n, s);
  if (!p)
    die("host allocation failed");
  return p;
}
static double now(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t))
    die("clock failed");
  return t.tv_sec + t.tv_nsec * 1e-9;
}
static void *watchdog(void *unused) {
  (void)unused;
  struct timespec delay = {0, 10000000};
  while (!atomic_load(&watchdog_done)) {
    nanosleep(&delay, NULL);
    wasmtime_engine_increment_epoch(engine);
  }
  return NULL;
}
static void error_text(wasmtime_error_t *error, wasm_trap_t *trap) {
  wasm_name_t msg;
  if (error)
    wasmtime_error_message(error, &msg);
  else
    wasm_trap_message(trap, &msg);
  size_t n = msg.size < sizeof(failure) - 1 ? msg.size : sizeof(failure) - 1;
  memcpy(failure, msg.data, n);
  failure[n] = 0;
  wasm_name_delete(&msg);
  if (error)
    wasmtime_error_delete(error);
  if (trap)
    wasm_trap_delete(trap);
}
static void random_fill(uint8_t *p, size_t n) {
  while (n) {
    ssize_t count = getrandom(p, n, 0);
    if (count < 0 && errno == EINTR)
      continue;
    if (count <= 0)
      die("host entropy unavailable");
    p += count;
    n -= count;
  }
}
static wasm_trap_t *mem_call(void *env, wasmtime_caller_t *caller,
                             const wasmtime_val_t *args, size_t nargs,
                             wasmtime_val_t *results, size_t nresults) {
  (void)caller;
  (void)nargs;
  (void)nresults;
  uintptr_t packed = (uintptr_t)env;
  unsigned kind = (unsigned)(packed & 7);
  guest *g = (guest *)(packed & ~(uintptr_t)7);
  uint64_t value = 0;
  if (!g->ready)
    return wasmtime_trap_new(
        "memlib called during module initialization",
        strlen("memlib called during module initialization"));
  switch (kind) {
  case 0: {
    int32_t inc = args[0].of.i32;
    if (inc < 0 || (uint64_t)inc > HEAP_START + MAX_HEAP - g->brk)
      value = UINT64_MAX;
    else {
      value = g->brk;
      g->brk += (uint32_t)inc;
    }
    break;
  }
  case 1:
    value = HEAP_START;
    break;
  case 2:
    value = g->brk - 1;
    break;
  case 3:
    value = g->brk - HEAP_START;
    break;
  case 4:
    value = 4096;
    break;
  }
  results[0].kind = WASMTIME_I64;
  results[0].of.i64 = (int64_t)value;
  return NULL;
}
static int get_func(guest *g, wasmtime_instance_t *instance, const char *name,
                    unsigned n, int result64, wasmtime_func_t *out) {
  wasmtime_extern_t item;
  if (!wasmtime_instance_export_get(g->context, instance, name, strlen(name),
                                    &item) ||
      item.kind != WASMTIME_EXTERN_FUNC) {
    snprintf(failure, sizeof(failure), "missing function %s", name);
    return 0;
  }
  wasm_functype_t *t = wasmtime_func_type(g->context, &item.of.func);
  const wasm_valtype_vec_t *p = wasm_functype_params(t),
                           *r = wasm_functype_results(t);
  int ok = p->size == n && r->size == (result64 < 0 ? 0 : 1);
  for (size_t i = 0; i < p->size; i++)
    if (wasm_valtype_kind(p->data[i]) != WASM_I64)
      ok = 0;
  if (r->size &&
      wasm_valtype_kind(r->data[0]) != (result64 ? WASM_I64 : WASM_I32))
    ok = 0;
  wasm_functype_delete(t);
  if (!ok) {
    snprintf(failure, sizeof(failure), "incorrect signature for %s", name);
    return 0;
  }
  *out = item.of.func;
  return 1;
}
static int new_guest(guest *g, wasmtime_module_t *module) {
  memset(g, 0, sizeof(*g));
  g->brk = HEAP_START;
  g->store = wasmtime_store_new(engine, NULL, NULL);
  g->context = wasmtime_store_context(g->store);
  wasmtime_store_limiter(g->store, MEMORY_SIZE, 1000, 1, 1, 1);
  wasmtime_context_set_epoch_deadline(g->context, 100);
  wasmtime_linker_t *linker = wasmtime_linker_new(engine);
  const char *names[] = {"mem_sbrk", "mem_heap_lo", "mem_heap_hi",
                         "mem_heapsize", "mem_pagesize"};
  for (unsigned i = 0; i < 5; i++) {
    wasm_functype_t *type = i == 0
                                ? wasm_functype_new_1_1(wasm_valtype_new_i32(),
                                                        wasm_valtype_new_i64())
                                : wasm_functype_new_0_1(wasm_valtype_new_i64());
    wasmtime_error_t *e = wasmtime_linker_define_func(
        linker, "env", 3, names[i], strlen(names[i]), type, mem_call,
        (void *)((uintptr_t)g | i), NULL);
    wasm_functype_delete(type);
    if (e) {
      error_text(e, NULL);
      wasmtime_linker_delete(linker);
      return 0;
    }
  }
  wasmtime_instance_t instance;
  wasm_trap_t *trap = NULL;
  wasmtime_error_t *error =
      wasmtime_linker_instantiate(linker, g->context, module, &instance, &trap);
  wasmtime_linker_delete(linker);
  if (error || trap) {
    error_text(error, trap);
    die(failure);
  }
  wasmtime_extern_t item;
  if (!wasmtime_instance_export_get(g->context, &instance, "memory", 6,
                                    &item) ||
      item.kind != WASMTIME_EXTERN_MEMORY) {
    strcpy(failure, "missing memory");
    return 0;
  }
  g->memory = item.of.memory;
  wasm_memorytype_t *mt = wasmtime_memory_type(g->context, &g->memory);
  uint64_t maximum = 0;
  int fixed = wasmtime_memorytype_is64(mt) &&
              !wasmtime_memorytype_isshared(mt) &&
              wasmtime_memorytype_maximum(mt, &maximum) &&
              maximum == MEMORY_SIZE / 65536 &&
              wasmtime_memorytype_minimum(mt) == maximum;
  wasm_memorytype_delete(mt);
  if (!fixed ||
      wasmtime_memory_data_size(g->context, &g->memory) != MEMORY_SIZE) {
    strcpy(failure, "memory must be fixed 24 MiB, unshared, and 64-bit");
    return 0;
  }
  if (!wasmtime_instance_export_get(g->context, &instance, "__heap_base", 11,
                                    &item) ||
      item.kind != WASMTIME_EXTERN_GLOBAL) {
    strcpy(failure, "missing __heap_base");
    return 0;
  }
  wasmtime_val_t base;
  wasmtime_global_get(g->context, &item.of.global, &base);
  if (base.kind != WASMTIME_I64 || (uint64_t)base.of.i64 > HEAP_START) {
    strcpy(failure, "candidate static storage exceeds 4 MiB");
    return 0;
  }
  if (!get_func(g, &instance, "mm_init", 0, 0, &g->init) ||
      !get_func(g, &instance, "mm_malloc", 1, 1, &g->alloc) ||
      !get_func(g, &instance, "mm_free", 1, -1, &g->release) ||
      !get_func(g, &instance, "mm_realloc", 2, 1, &g->resize))
    return 0;
  g->ready = 1;
  return 1;
}
static int call(guest *g, const wasmtime_func_t *func, uint64_t a, uint64_t b,
                unsigned n, int result64, uint64_t *value) {
  wasmtime_val_raw_t args[2] = {{0}, {0}};
  args[0].i64 = a;
  args[1].i64 = b;
  wasm_trap_t *trap = NULL;
  wasmtime_context_set_epoch_deadline(g->context, 100);
  double start = now();
  /* Signatures were checked in get_func. The last length is the buffer
     capacity, including result space; mm_init needs one slot for its result. */
  wasmtime_error_t *error = wasmtime_func_call_unchecked(
      g->context, func, args, n ? n : (result64 < 0 ? 0 : 1), &trap);
  g->call_seconds += now() - start;
  if (error || trap) {
    error_text(error, trap);
    die(failure);
  }
  if (result64 >= 0)
    *value = result64 ? (uint64_t)args[0].i64
                      : (uint64_t)(int64_t)(int32_t)args[0].i32;
  return 1;
}
static int in_heap(guest *g, uint64_t ptr, uint64_t size) {
  return ptr >= HEAP_START && ptr <= g->brk && size <= g->brk - ptr &&
         !(ptr % 16) && size > 0;
}
static int run_trace(wasmtime_module_t *module, const trace *t, double *secs,
                     double *util) {
  guest *g = checked_calloc(1, sizeof(*g));
  block *blocks = checked_calloc(t->nids, sizeof(*blocks));
  int ok = 0;
  if (!new_guest(g, module))
    die(failure);
  uint64_t result = 0, live_bytes = 0, peak_bytes = 0;
  if (!call(g, &g->init, 0, 0, 0, 0, &result) || (int64_t)result < 0) {
    if (!failure[0])
      strcpy(failure, "mm_init failed");
    goto done;
  }
  uint8_t *memory = wasmtime_memory_data(g->context, &g->memory);
  for (size_t k = 0; k < t->nops; k++) {
    const operation *op = &t->ops[k];
    block *old = &blocks[op->id];
    if (op->kind != 'a' &&
        (!old->live ||
         memcmp(memory + old->offset, old->expected, old->size) != 0)) {
      snprintf(failure, sizeof(failure),
               "operation %zu: existing block contents damaged", k);
      goto done;
    }
    if (op->kind == 'f') {
      if (!call(g, &g->release, old->offset, 0, 1, -1, &result))
        goto done;
      live_bytes -= old->size;
      old->live = 0;
      free(old->expected);
      old->expected = NULL;
      continue;
    }
    if (op->kind == 'a' && old->live) {
      strcpy(failure, "trace allocates active ID");
      goto done;
    }
    if (op->kind == 'a') {
      if (!call(g, &g->alloc, op->size, 0, 1, 1, &result))
        goto done;
    } else {
      if (!call(g, &g->resize, old->offset, op->size, 2, 1, &result))
        goto done;
    }
    if (!in_heap(g, result, op->size)) {
      snprintf(failure, sizeof(failure),
               "operation %zu: returned address is null, unaligned, or outside "
               "requested heap",
               k);
      goto done;
    }
    for (size_t j = 0; j < t->nids; j++) {
      block *other = &blocks[j];
      if (other->live && j != op->id && result < other->offset + other->size &&
          other->offset < result + op->size) {
        snprintf(failure, sizeof(failure),
                 "operation %zu: overlapping allocation", k);
        goto done;
      }
    }
    if (op->kind == 'r') {
      uint64_t preserved = old->size < op->size ? old->size : op->size;
      if (memcmp(memory + result, old->expected, preserved) != 0) {
        snprintf(failure, sizeof(failure),
                 "operation %zu: realloc did not preserve data", k);
        goto done;
      }
      live_bytes -= old->size;
    }
    free(old->expected);
    old->expected = checked_calloc(op->size, 1);
    random_fill(old->expected, op->size);
    old->offset = result;
    old->size = op->size;
    old->live = 1;
    memcpy(memory + result, old->expected, op->size);
    live_bytes += op->size;
    if (live_bytes > peak_bytes)
      peak_bytes = live_bytes;
  }
  for (size_t j = 0; j < t->nids; j++)
    if (blocks[j].live && memcmp(memory + blocks[j].offset, blocks[j].expected,
                                 blocks[j].size) != 0) {
      strcpy(failure, "final live block contents damaged");
      goto done;
    }
  if (g->brk <= HEAP_START || peak_bytes > g->brk - HEAP_START) {
    strcpy(failure, "invalid heap utilization");
    goto done;
  }
  *secs = g->call_seconds;
  *util = (double)peak_bytes / (g->brk - HEAP_START);
  ok = 1;
done:
  if (g->store)
    wasmtime_store_delete(g->store);
  free(g);
  for (size_t j = 0; j < t->nids; j++)
    free(blocks[j].expected);
  free(blocks);
  return ok;
}
static trace load_trace(const char *directory, const char *name) {
  char path[8192];
  if (snprintf(path, sizeof(path), "%s/%s", directory, name) >=
      (int)sizeof(path))
    die("trace path too long");
  FILE *f = fopen(path, "r");
  if (!f)
    die("cannot open trusted trace");
  size_t heap, nids, nops, weight;
  if (fscanf(f, "%zu %zu %zu %zu", &heap, &nids, &nops, &weight) != 4 ||
      nids == 0 || nids > 1000000 || nops == 0 || nops > 10000000)
    die("invalid trace header");
  trace t = {nids, nops, checked_calloc(nops, sizeof(operation))};
  unsigned char *active = checked_calloc(nids, 1);
  for (size_t i = 0; i < nops; i++) {
    operation *o = &t.ops[i];
    if (fscanf(f, " %c %u", &o->kind, &o->id) != 2 || o->id >= nids)
      die("invalid trace ID");
    if (o->kind == 'a' || o->kind == 'r') {
      unsigned long long size;
      if (fscanf(f, "%llu", &size) != 1 || size == 0 || size > MAX_HEAP)
        die("invalid trace size");
      o->size = size;
    } else if (o->kind != 'f')
      die("invalid trace operation");
    if ((o->kind == 'a' && active[o->id]) || (o->kind != 'a' && !active[o->id]))
      die("invalid trace lifetime");
    active[o->id] = o->kind != 'f';
  }
  char extra;
  if (fscanf(f, " %c", &extra) == 1)
    die("extra trace operations");
  fclose(f);
  free(active);
  return t;
}
static void json_string(const char *s) {
  putchar('"');
  for (; *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\')
      putchar('\\');
    if (c >= 32 && c < 127)
      putchar(c);
    else
      printf("\\u%04x", c);
  }
  putchar('"');
}
int main(int argc, char **argv) {
  if (argc != 3)
    die("usage: malloc_host candidate.wasm trusted-trace-directory");
  FILE *f = fopen(argv[1], "rb");
  if (!f)
    die("cannot read candidate module");
  if (fseek(f, 0, SEEK_END))
    die("seek failed");
  long n = ftell(f);
  if (n <= 0 || n > 16 * 1024 * 1024)
    die("invalid module size");
  rewind(f);
  wasm_byte_vec_t bytes;
  wasm_byte_vec_new_uninitialized(&bytes, (size_t)n);
  if (fread(bytes.data, 1, n, f) != (size_t)n)
    die("read failed");
  fclose(f);
  wasm_config_t *config = wasm_config_new();
  wasmtime_config_wasm_memory64_set(config, true);
  wasmtime_config_wasm_threads_set(config, false);
  wasmtime_config_epoch_interruption_set(config, true);
  wasmtime_config_max_wasm_stack_set(config, 1024 * 1024);
  engine = wasm_engine_new_with_config(config);
  wasmtime_module_t *module;
  wasmtime_error_t *error =
      wasmtime_module_new(engine, (uint8_t *)bytes.data, bytes.size, &module);
  wasm_byte_vec_delete(&bytes);
  if (error) {
    error_text(error, NULL);
    die(failure);
  }
  pthread_t thread;
  if (pthread_create(&thread, NULL, watchdog, NULL))
    die("watchdog failed");
  const size_t count = sizeof(traces) / sizeof(traces[0]);
  size_t passed = 0;
  double sum_util = 0, sum_seconds = 0, completed_ops = 0;
  printf("{\"schema\":\"malloc_wasm64.v1\",\"traces\":[");
  for (size_t i = 0; i < count; i++) {
    trace t = load_trace(argv[2], traces[i]);
    double secs[REPEATS] = {0}, util[REPEATS] = {0};
    int valid = 1;
    for (unsigned r = 0; r < REPEATS; r++) {
      failure[0] = 0;
      if (!run_trace(module, &t, &secs[r], &util[r])) {
        valid = 0;
        break;
      }
    }
    double seconds = 0, utilization = 0;
    if (valid) {
      /* Every timing pass is independently instantiated and fully validated. */
      for (unsigned a = 0; a < REPEATS; a++)
        for (unsigned b = a + 1; b < REPEATS; b++)
          if (secs[b] < secs[a]) {
            double x = secs[a];
            secs[a] = secs[b];
            secs[b] = x;
          }
      seconds = (secs[REPEATS / 2 - 1] + secs[REPEATS / 2]) / 2;
      utilization = util[0];
      for (unsigned r = 1; r < REPEATS; r++)
        if (util[r] < utilization)
          utilization = util[r];
      if (!isfinite(seconds) || seconds <= 0)
        valid = 0;
    }
    if (valid) {
      passed++;
      sum_util += utilization;
      sum_seconds += seconds;
      completed_ops += t.nops;
    }
    if (i)
      putchar(',');
    printf("{\"name\":");
    json_string(traces[i]);
    printf(",\"valid\":%d,\"operations\":%zu,\"runtime_s\":%.12g,"
           "\"utilization\":%.12g,\"error\":",
           valid, t.nops, seconds, utilization);
    json_string(valid ? "" : failure);
    putchar('}');
    fflush(stdout);
    free(t.ops);
  }
  double throughput = sum_seconds > 0 ? completed_ops / sum_seconds : 0;
  double up = 60 * sum_util / count,
         tp = 40 * fmin(1, throughput / THROUGHPUT_CAP);
  double score = (up + tp) * passed / count;
  printf("],\"testcases_passed\":%zu,\"testcases_total\":%zu,\"util_points\":%."
         "12g,\"thru_points\":%.12g,\"throughput_ops_s\":%.12g,\"score_100\":%."
         "12g}\n",
         passed, count, up, tp, throughput, score);
  atomic_store(&watchdog_done, true);
  pthread_join(thread, NULL);
  wasmtime_module_delete(module);
  wasm_engine_delete(engine);
  return 0;
}

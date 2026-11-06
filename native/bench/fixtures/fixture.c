/* Deliberately small, deterministic native benchmark input. */
#include <stdint.h>

__attribute__((noinline)) int32_t native_bench_add(int32_t a, int32_t b) {
  return a + b;
}

__attribute__((noinline)) int32_t native_bench_mix(int32_t value) {
  return (native_bench_add(value, 7) * 3) ^ 0x55aa;
}

int main(void) {
  return native_bench_mix(11) & 0xff;
}

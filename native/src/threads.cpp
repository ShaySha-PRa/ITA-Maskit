#include "maskit/core/threads.hpp"

#include <algorithm>
#include <cstdlib>
#include <mutex>
#include <thread>

#ifdef MASKIT_USE_OPENMP
#include <omp.h>
#endif

namespace maskit::core {
namespace {

int g_override = -2;  // -2 = read env, -1 = hardware, 0 = serial, >0 = exact
std::once_flag g_once;

int from_env() {
    const char* raw = std::getenv("MASKIT_NATIVE_THREADS");
    if (raw == nullptr || raw[0] == '\0') {
        return -1;
    }
    char* end = nullptr;
    long n = std::strtol(raw, &end, 10);
    if (end == raw) {
        return -1;
    }
    if (n < 0) {
        return -1;
    }
    if (n > 256) {
        n = 256;
    }
    return static_cast<int>(n);
}

int resolved() {
    std::call_once(g_once, []() {
        if (g_override == -2) {
            g_override = from_env();
        }
    });
    if (g_override == -2) {
        return from_env();
    }
    return g_override;
}

int hardware() {
#ifdef MASKIT_USE_OPENMP
    int n = omp_get_max_threads();
    return n > 0 ? n : 1;
#else
    unsigned n = std::thread::hardware_concurrency();
    return n > 0 ? static_cast<int>(n) : 1;
#endif
}

}  // namespace

void set_native_threads(int n) {
    if (n < -1) {
        n = -1;
    }
    if (n > 256) {
        n = 256;
    }
    g_override = n;
}

int native_threads() {
    int n = resolved();
    return n < 0 ? hardware() : n;
}

int effective_threads(std::size_t batch_size, std::size_t min_parallel) {
    if (batch_size < min_parallel) {
        return 1;
    }
    int want = native_threads();
    if (want <= 1) {
        return 1;
    }
    return std::max(1, std::min(want, static_cast<int>(batch_size)));
}

}  // namespace maskit::core

#pragma once

#include <cstddef>

namespace maskit::core {

// MASKIT_NATIVE_THREADS: unset / <0 = hardware, 0 = serial, >0 = exact count.
void set_native_threads(int n);
int native_threads();
int effective_threads(std::size_t batch_size, std::size_t min_parallel = 256);

}  // namespace maskit::core

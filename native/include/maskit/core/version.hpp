#pragma once

#include <string>

namespace maskit::core {

inline constexpr const char* kNativeVersion = "0.1.1";
inline constexpr int kCoreAbiVersion = 1;
inline constexpr const char* kDetectorVersion = "python-reference";
inline constexpr const char* kNormalizerVersion = "1";

std::string native_version();
int core_abi_version();
std::string detector_version();
std::string build_compiler();
std::string build_type();

}  // namespace maskit::core

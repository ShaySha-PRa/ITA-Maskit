#include "maskit/core/version.hpp"

namespace maskit::core {

std::string native_version() { return kNativeVersion; }
int core_abi_version() { return kCoreAbiVersion; }
std::string detector_version() { return kDetectorVersion; }

std::string build_compiler() {
#if defined(_MSC_VER)
    return "msvc";
#elif defined(__clang__)
    return "clang";
#elif defined(__GNUC__)
    return "gcc";
#else
    return "unknown";
#endif
}

std::string build_type() {
#ifdef NDEBUG
    return "release";
#else
    return "debug";
#endif
}

}  // namespace maskit::core

#include "maskit/core/version.hpp"

#include <iostream>

int main() {
    std::cout << "native_version=" << maskit::core::native_version() << "\n";
    std::cout << "core_abi_version=" << maskit::core::core_abi_version() << "\n";
    std::cout << "build_compiler=" << maskit::core::build_compiler() << "\n";
    std::cout << "build_type=" << maskit::core::build_type() << "\n";
    return 0;
}

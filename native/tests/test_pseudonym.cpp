#include "maskit/core/errors.hpp"
#include "maskit/core/pseudonym.hpp"
#include "maskit/core/version.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

int g_failed = 0;

void expect(bool cond, const char* msg) {
    if (!cond) {
        std::cerr << "FAIL: " << msg << "\n";
        ++g_failed;
    }
}

}  // namespace

int main() {
    using namespace maskit::core;

    expect(native_version() == "0.1.1", "native_version");
    expect(core_abi_version() == 1, "abi");
    expect(!build_compiler().empty(), "compiler");

    const std::string pepper = "maskit-test-pepper-not-production";
    expect(hash_v1("13800138000", pepper, 8) == "4E231046", "v1 golden phone");
    expect(hash_v1("alice@corp.example", pepper, 8) == "8D3512B4", "v1 golden email");
    expect(hash_v1("张伟", pepper, 8) == "7334D813", "v1 golden name");
    expect(
        hash_v2("alice@corp.example", pepper, "email", 24, "1") == "AF266C7DF624E54BC10190A3",
        "v2 golden email"
    );
    auto a = hash_v1("13800138000", pepper, 8);
    auto b = hash_v1("13800138000", pepper, 8);
    expect(a == b, "v1 determinism");
    expect(a.size() == 8, "v1 length");
    expect(hash_v1("13800138000", "other", 8) != a, "v1 pepper separates");

    auto v2 = hash_v2("alice@corp.example", pepper, "email", 24, "1");
    expect(v2.size() == 24, "v2 length");
    expect(v2 == hash_v2("alice@corp.example", pepper, "email", 24, "1"), "v2 determinism");
    expect(v2 != hash_v2("alice@corp.example", pepper, "account", 24, "1"), "v2 entity separates");
    expect(v2 != hash_v2("alice@corp.example", pepper, "email", 24, "2"), "v2 nv separates");

    auto batch = hash_batch({"x", "y"}, pepper, PseudoScheme::V1, {}, 8, "1");
    expect(batch.size() == 2, "batch size");
    expect(batch[0] == hash_v1("x", pepper, 8), "batch[0]");
    expect(batch[1] == hash_v1("y", pepper, 8), "batch[1]");

    bool threw = false;
    try {
        parse_scheme("v9");
    } catch (const UnsupportedSchemeError&) {
        threw = true;
    }
    expect(threw, "unsupported scheme");

    auto digits = digits_from_hex("A1B2", 6);
    expect(digits.size() == 6, "digits len");
    expect(digits.substr(0, 4) == "0112", "digits map A=10->0 1=1 B=11->1 2=2");

    if (g_failed != 0) {
        std::cerr << g_failed << " failure(s)\n";
        return EXIT_FAILURE;
    }
    std::cout << "maskit_core_tests ok\n";
    return EXIT_SUCCESS;
}

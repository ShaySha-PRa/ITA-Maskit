#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace maskit::core {

enum class PseudoScheme { V1, V2 };

struct HashRequest {
    std::string_view value;
    std::string_view entity_type;
    int length = 8;
};

PseudoScheme parse_scheme(std::string_view scheme);

std::string hex_upper(const std::uint8_t* data, std::size_t n);

std::string hash_v1(std::string_view value, std::string_view pepper, int length);
std::string hash_v2(
    std::string_view value,
    std::string_view pepper,
    std::string_view entity_type,
    int length = 24,
    std::string_view normalizer_version = "1"
);

std::vector<std::string> hash_batch(
    const std::vector<std::string>& values,
    std::string_view pepper,
    PseudoScheme scheme,
    const std::vector<std::string>& entity_types,
    int length,
    std::string_view normalizer_version = "1"
);

// HMAC-derived digits, matching Python render_template {digits}.
std::string digits_from_hex(std::string_view hex, std::size_t n);

}  // namespace maskit::core

#pragma once

#include <cstddef>
#include <cstdint>
#include <span>

namespace maskit::core {

inline constexpr std::size_t kSha256Len = 32;

// Audited OS/library HMAC-SHA256. Never a hand-rolled hash.
void hmac_sha256(
    std::span<const std::uint8_t> key,
    std::span<const std::uint8_t> message,
    std::span<std::uint8_t, kSha256Len> out
);

void secure_wipe(std::span<std::uint8_t> buf);

}  // namespace maskit::core

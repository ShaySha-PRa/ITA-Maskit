#include "maskit/core/pseudonym.hpp"

#include "maskit/core/crypto.hpp"
#include "maskit/core/errors.hpp"
#include "maskit/core/threads.hpp"

#include <array>
#include <span>

namespace maskit::core {
namespace {

std::span<const std::uint8_t> as_bytes(std::string_view s) {
    return {reinterpret_cast<const std::uint8_t*>(s.data()), s.size()};
}

std::array<std::uint8_t, kSha256Len> hmac_sv(std::string_view key, std::string_view msg) {
    std::array<std::uint8_t, kSha256Len> out{};
    hmac_sha256(as_bytes(key), as_bytes(msg), std::span<std::uint8_t, kSha256Len>{out});
    return out;
}

std::array<std::uint8_t, kSha256Len> hmac_key_msg(
    std::span<const std::uint8_t> key,
    std::string_view msg
) {
    std::array<std::uint8_t, kSha256Len> out{};
    hmac_sha256(key, as_bytes(msg), std::span<std::uint8_t, kSha256Len>{out});
    return out;
}

}  // namespace

PseudoScheme parse_scheme(std::string_view scheme) {
    if (scheme == "v1") {
        return PseudoScheme::V1;
    }
    if (scheme == "v2") {
        return PseudoScheme::V2;
    }
    throw UnsupportedSchemeError(std::string(scheme));
}

std::string hex_upper(const std::uint8_t* data, std::size_t n) {
    static constexpr char kHex[] = "0123456789ABCDEF";
    std::string out;
    out.resize(n * 2);
    for (std::size_t i = 0; i < n; ++i) {
        out[2 * i] = kHex[(data[i] >> 4) & 0xF];
        out[2 * i + 1] = kHex[data[i] & 0xF];
    }
    return out;
}

std::string hash_v1(std::string_view value, std::string_view pepper, int length) {
    if (length <= 0 || length > 64) {
        throw NativeError("invalid digest length");
    }
    auto key = hmac_sv(pepper, "pseudonym");
    auto digest = hmac_key_msg(std::span<const std::uint8_t>{key.data(), key.size()}, value);
    std::string hex = hex_upper(digest.data(), digest.size());
    secure_wipe(std::span<std::uint8_t>{key.data(), key.size()});
    secure_wipe(std::span<std::uint8_t>{digest.data(), digest.size()});
    if (static_cast<std::size_t>(length) > hex.size()) {
        throw NativeError("invalid digest length");
    }
    hex.resize(static_cast<std::size_t>(length));
    return hex;
}

std::string hash_v2(
    std::string_view value,
    std::string_view pepper,
    std::string_view entity_type,
    int length,
    std::string_view normalizer_version
) {
    if (length <= 0 || length > 64) {
        throw NativeError("invalid digest length");
    }
    auto root = hmac_sv(pepper, "maskit:pseudonym:v2");
    auto key = hmac_key_msg(
        std::span<const std::uint8_t>{root.data(), root.size()}, entity_type
    );
    std::string msg;
    msg.reserve(3 + normalizer_version.size() + 1 + value.size());
    msg.append("v2|");
    msg.append(normalizer_version);
    msg.push_back('|');
    msg.append(value);
    auto digest = hmac_key_msg(std::span<const std::uint8_t>{key.data(), key.size()}, msg);
    std::string hex = hex_upper(digest.data(), digest.size());
    secure_wipe(std::span<std::uint8_t>{root.data(), root.size()});
    secure_wipe(std::span<std::uint8_t>{key.data(), key.size()});
    secure_wipe(std::span<std::uint8_t>{digest.data(), digest.size()});
    if (static_cast<std::size_t>(length) > hex.size()) {
        throw NativeError("invalid digest length");
    }
    hex.resize(static_cast<std::size_t>(length));
    return hex;
}

std::vector<std::string> hash_batch(
    const std::vector<std::string>& values,
    std::string_view pepper,
    PseudoScheme scheme,
    const std::vector<std::string>& entity_types,
    int length,
    std::string_view normalizer_version
) {
    if (scheme == PseudoScheme::V2 && entity_types.size() != values.size() &&
        entity_types.size() != 1 && !entity_types.empty()) {
        throw BatchSizeError();
    }
    if (length <= 0 || length > 64) {
        throw NativeError("invalid digest length");
    }
    std::vector<std::string> out(values.size());
    const int threads = effective_threads(values.size());
    if (scheme == PseudoScheme::V1) {
        auto key = hmac_sv(pepper, "pseudonym");
#ifdef MASKIT_USE_OPENMP
#pragma omp parallel for schedule(static) num_threads(threads)
        for (int i = 0; i < static_cast<int>(values.size()); ++i) {
            auto digest = hmac_key_msg(
                std::span<const std::uint8_t>{key.data(), key.size()},
                values[static_cast<std::size_t>(i)]
            );
            std::string hex = hex_upper(digest.data(), digest.size());
            hex.resize(static_cast<std::size_t>(length));
            out[static_cast<std::size_t>(i)] = std::move(hex);
            secure_wipe(std::span<std::uint8_t>{digest.data(), digest.size()});
        }
#else
        (void)threads;
        for (std::size_t i = 0; i < values.size(); ++i) {
            auto digest = hmac_key_msg(
                std::span<const std::uint8_t>{key.data(), key.size()}, values[i]
            );
            std::string hex = hex_upper(digest.data(), digest.size());
            hex.resize(static_cast<std::size_t>(length));
            out[i] = std::move(hex);
            secure_wipe(std::span<std::uint8_t>{digest.data(), digest.size()});
        }
#endif
        secure_wipe(std::span<std::uint8_t>{key.data(), key.size()});
        return out;
    }
    const bool shared_entity = entity_types.size() == 1 || entity_types.empty();
    std::array<std::uint8_t, kSha256Len> shared_key{};
    bool have_shared = false;
    if (shared_entity) {
        auto root = hmac_sv(pepper, "maskit:pseudonym:v2");
        std::string_view entity = entity_types.empty() ? "unknown" : entity_types[0];
        shared_key = hmac_key_msg(
            std::span<const std::uint8_t>{root.data(), root.size()}, entity
        );
        have_shared = true;
        secure_wipe(std::span<std::uint8_t>{root.data(), root.size()});
    }
#ifdef MASKIT_USE_OPENMP
#pragma omp parallel for schedule(static) num_threads(threads)
    for (int i = 0; i < static_cast<int>(values.size()); ++i) {
        const std::size_t idx = static_cast<std::size_t>(i);
#else
    for (std::size_t idx = 0; idx < values.size(); ++idx) {
#endif
        std::array<std::uint8_t, kSha256Len> key{};
        if (have_shared) {
            key = shared_key;
        } else {
            std::string_view entity = entity_types[idx];
            auto root = hmac_sv(pepper, "maskit:pseudonym:v2");
            key = hmac_key_msg(
                std::span<const std::uint8_t>{root.data(), root.size()}, entity
            );
            secure_wipe(std::span<std::uint8_t>{root.data(), root.size()});
        }
        std::string msg;
        msg.append("v2|");
        msg.append(normalizer_version);
        msg.push_back('|');
        msg.append(values[idx]);
        auto digest = hmac_key_msg(std::span<const std::uint8_t>{key.data(), key.size()}, msg);
        std::string hex = hex_upper(digest.data(), digest.size());
        hex.resize(static_cast<std::size_t>(length));
        out[idx] = std::move(hex);
        if (!have_shared) {
            secure_wipe(std::span<std::uint8_t>{key.data(), key.size()});
        }
        secure_wipe(std::span<std::uint8_t>{digest.data(), digest.size()});
    }
    if (have_shared) {
        secure_wipe(std::span<std::uint8_t>{shared_key.data(), shared_key.size()});
    }
    return out;
}

std::string digits_from_hex(std::string_view hex, std::size_t n) {
    std::string digits;
    digits.reserve(n);
    for (char c : hex) {
        unsigned v = 0;
        if (c >= '0' && c <= '9') {
            v = static_cast<unsigned>(c - '0');
        } else if (c >= 'A' && c <= 'F') {
            v = static_cast<unsigned>(c - 'A' + 10);
        } else if (c >= 'a' && c <= 'f') {
            v = static_cast<unsigned>(c - 'a' + 10);
        } else {
            continue;
        }
        digits.push_back(static_cast<char>('0' + (v % 10)));
        if (digits.size() == n) {
            break;
        }
    }
    while (digits.size() < n) {
        digits.push_back('0');
    }
    return digits;
}

}  // namespace maskit::core

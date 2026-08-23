#include "maskit/core/crypto.hpp"

#include "maskit/core/errors.hpp"

#include <cstring>

#if defined(MASKIT_USE_BCRYPT)
#include <windows.h>
#include <bcrypt.h>
#elif defined(MASKIT_USE_OPENSSL)
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#else
#error "No HMAC backend configured"
#endif

namespace maskit::core {

#if defined(MASKIT_USE_OPENSSL)

void hmac_sha256(
    std::span<const std::uint8_t> key,
    std::span<const std::uint8_t> message,
    std::span<std::uint8_t, kSha256Len> out
) {
    unsigned int out_len = 0;
    const auto* ok = HMAC(
        EVP_sha256(),
        key.data(),
        static_cast<int>(key.size()),
        message.data(),
        message.size(),
        out.data(),
        &out_len
    );
    if (ok == nullptr || out_len != kSha256Len) {
        throw NativeInternalError();
    }
}

void secure_wipe(std::span<std::uint8_t> buf) {
    if (!buf.empty()) {
        OPENSSL_cleanse(buf.data(), buf.size());
    }
}

#elif defined(MASKIT_USE_BCRYPT)

void hmac_sha256(
    std::span<const std::uint8_t> key,
    std::span<const std::uint8_t> message,
    std::span<std::uint8_t, kSha256Len> out
) {
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    NTSTATUS st = BCryptOpenAlgorithmProvider(
        &alg, BCRYPT_SHA256_ALGORITHM, nullptr, BCRYPT_ALG_HANDLE_HMAC_FLAG
    );
    if (st < 0) {
        throw NativeInternalError();
    }
    st = BCryptCreateHash(
        alg,
        &hash,
        nullptr,
        0,
        const_cast<PUCHAR>(reinterpret_cast<const UCHAR*>(key.data())),
        static_cast<ULONG>(key.size()),
        0
    );
    if (st < 0) {
        BCryptCloseAlgorithmProvider(alg, 0);
        throw NativeInternalError();
    }
    if (!message.empty()) {
        st = BCryptHashData(
            hash,
            const_cast<PUCHAR>(reinterpret_cast<const UCHAR*>(message.data())),
            static_cast<ULONG>(message.size()),
            0
        );
    }
    if (st >= 0) {
        st = BCryptFinishHash(hash, out.data(), static_cast<ULONG>(out.size()), 0);
    }
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(alg, 0);
    if (st < 0) {
        throw NativeInternalError();
    }
}

void secure_wipe(std::span<std::uint8_t> buf) {
    if (!buf.empty()) {
        SecureZeroMemory(buf.data(), buf.size());
    }
}

#endif

}  // namespace maskit::core

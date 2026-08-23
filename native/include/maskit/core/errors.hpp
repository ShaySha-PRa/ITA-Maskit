#pragma once

#include <stdexcept>
#include <string>

namespace maskit::core {

class NativeError : public std::runtime_error {
public:
    explicit NativeError(const std::string& what) : std::runtime_error(what) {}
};

class InvalidUtf8Error : public NativeError {
public:
    InvalidUtf8Error() : NativeError("invalid UTF-8 input") {}
};

class UnsupportedSchemeError : public NativeError {
public:
    explicit UnsupportedSchemeError(const std::string& scheme)
        : NativeError("unsupported pseudonym scheme") {
        (void)scheme;
    }
};

class BatchSizeError : public NativeError {
public:
    BatchSizeError() : NativeError("batch argument sizes do not match") {}
};

class NativeInternalError : public NativeError {
public:
    NativeInternalError() : NativeError("native internal error") {}
};

}  // namespace maskit::core

#include "maskit/core/normalize.hpp"

#include <cctype>

namespace maskit::core {
namespace {

bool is_ascii(std::string_view s) {
    for (unsigned char c : s) {
        if (c >= 0x80) {
            return false;
        }
    }
    return true;
}

char32_t halfwidth_cp(char32_t c) {
    if (c >= 0xFF01 && c <= 0xFF5E) {
        return static_cast<char32_t>(c - 0xFEE0);
    }
    if (c == 0x3000) {
        return U' ';
    }
    return c;
}

}  // namespace

std::size_t utf32_length(std::string_view utf8) {
    std::vector<char32_t> cps;
    if (!decode_utf32(utf8, cps)) {
        return utf8.size();
    }
    return cps.size();
}

bool decode_utf32(std::string_view utf8, std::vector<char32_t>& out) {
    out.clear();
    out.reserve(utf8.size());
    const auto* p = reinterpret_cast<const unsigned char*>(utf8.data());
    const auto* end = p + utf8.size();
    while (p < end) {
        unsigned char b = *p;
        char32_t cp = 0;
        std::size_t n = 0;
        if (b < 0x80) {
            cp = b;
            n = 1;
        } else if ((b & 0xE0) == 0xC0 && p + 1 < end) {
            cp = static_cast<char32_t>(((b & 0x1F) << 6) | (p[1] & 0x3F));
            n = 2;
        } else if ((b & 0xF0) == 0xE0 && p + 2 < end) {
            cp = static_cast<char32_t>(((b & 0x0F) << 12) | ((p[1] & 0x3F) << 6) | (p[2] & 0x3F));
            n = 3;
        } else if ((b & 0xF8) == 0xF0 && p + 3 < end) {
            cp = static_cast<char32_t>(
                ((b & 0x07) << 18) | ((p[1] & 0x3F) << 12) | ((p[2] & 0x3F) << 6) | (p[3] & 0x3F)
            );
            n = 4;
        } else {
            return false;
        }
        out.push_back(cp);
        p += n;
    }
    return true;
}

std::string encode_utf32(const std::vector<char32_t>& cps) {
    std::string out;
    out.reserve(cps.size() * 3);
    for (char32_t cp : cps) {
        if (cp < 0x80) {
            out.push_back(static_cast<char>(cp));
        } else if (cp < 0x800) {
            out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else if (cp < 0x10000) {
            out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else {
            out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        }
    }
    return out;
}

std::string_view slice_utf32(std::string_view utf8, std::size_t start, std::size_t end) {
    std::vector<char32_t> cps;
    if (!decode_utf32(utf8, cps)) {
        return {};
    }
    if (start > cps.size()) {
        start = cps.size();
    }
    if (end > cps.size()) {
        end = cps.size();
    }
    if (start >= end) {
        return {};
    }
    // Re-walk UTF-8 to find byte offsets.
    const auto* p = reinterpret_cast<const unsigned char*>(utf8.data());
    const auto* begin = p;
    const auto* last = p + utf8.size();
    std::size_t i = 0;
    const unsigned char* a = begin;
    const unsigned char* b = begin;
    while (p < last && i <= end) {
        if (i == start) {
            a = p;
        }
        if (i == end) {
            b = p;
            break;
        }
        unsigned char c = *p;
        if (c < 0x80) {
            p += 1;
        } else if ((c & 0xE0) == 0xC0) {
            p += 2;
        } else if ((c & 0xF0) == 0xE0) {
            p += 3;
        } else {
            p += 4;
        }
        ++i;
        if (i == end) {
            b = p;
        }
    }
    auto off = static_cast<std::size_t>(a - begin);
    auto n = static_cast<std::size_t>(b - a);
    if (off + n > utf8.size()) {
        return {};
    }
    return utf8.substr(off, n);
}

std::string to_halfwidth(std::string_view utf8) {
    if (is_ascii(utf8)) {
        return std::string(utf8);
    }
    std::vector<char32_t> cps;
    if (!decode_utf32(utf8, cps)) {
        return std::string(utf8);
    }
    for (char32_t& c : cps) {
        c = halfwidth_cp(c);
    }
    return encode_utf32(cps);
}

std::string nfkc_half(std::string_view utf8) {
    if (utf8.empty() || is_ascii(utf8)) {
        return std::string(utf8);
    }
    return to_halfwidth(utf8);
}

std::string strip_ascii_ws(std::string_view utf8) {
    std::size_t a = 0;
    std::size_t b = utf8.size();
    while (a < b && std::isspace(static_cast<unsigned char>(utf8[a]))) {
        ++a;
    }
    while (b > a && std::isspace(static_cast<unsigned char>(utf8[b - 1]))) {
        --b;
    }
    return std::string(utf8.substr(a, b - a));
}

std::string digits_only(std::string_view utf8) {
    std::string out;
    out.reserve(utf8.size());
    for (unsigned char c : utf8) {
        if (c >= '0' && c <= '9') {
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

std::string canonical_phone(std::string_view utf8) {
    std::string half = nfkc_half(utf8);
    std::string d;
    d.reserve(half.size());
    for (unsigned char c : half) {
        if ((c >= '0' && c <= '9') || c == '+') {
            d.push_back(static_cast<char>(c));
        }
    }
    if (d.rfind("+0086", 0) == 0) {
        d = "+86" + d.substr(5);
    } else if (d.rfind("0086", 0) == 0) {
        d = "+86" + d.substr(4);
    } else if (d.rfind("+86", 0) == 0) {
        // keep
    } else if (d.rfind("86", 0) == 0 && d.size() >= 13) {
        d = "+86" + d.substr(2);
    }
    return d;
}

std::string canonical_id_card(std::string_view utf8) {
    std::string out;
    out.reserve(utf8.size());
    for (unsigned char c : utf8) {
        if (!std::isspace(c)) {
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

std::string canonical_bank_card(std::string_view utf8) {
    std::string out;
    out.reserve(utf8.size());
    for (unsigned char c : utf8) {
        if (!std::isspace(c) && c != '-') {
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

std::string canonical_email(std::string_view utf8) {
    return to_halfwidth(utf8);
}

}  // namespace maskit::core

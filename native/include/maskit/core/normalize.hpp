#pragma once

#include <string>
#include <string_view>
#include <vector>

namespace maskit::core {

// Fullwidth ASCII FF01-FF5E and U+3000. 1:1 codepoint mapping, no ICU.
std::string to_halfwidth(std::string_view utf8);

// ASCII fast path; otherwise halfwidth. Matches Python nfkc_half for PII alphabet.
std::string nfkc_half(std::string_view utf8);

std::string strip_ascii_ws(std::string_view utf8);
std::string digits_only(std::string_view utf8);
std::string canonical_phone(std::string_view utf8);
std::string canonical_id_card(std::string_view utf8);
std::string canonical_bank_card(std::string_view utf8);
std::string canonical_email(std::string_view utf8);

std::size_t utf32_length(std::string_view utf8);
bool decode_utf32(std::string_view utf8, std::vector<char32_t>& out);
std::string encode_utf32(const std::vector<char32_t>& cps);
std::string_view slice_utf32(std::string_view utf8, std::size_t start, std::size_t end);

}  // namespace maskit::core

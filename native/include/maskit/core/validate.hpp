#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace maskit::core {

bool id_card_checksum_ok(std::string_view value);
bool luhn_ok(std::string_view digits);
bool is_date_like(std::string_view value);
bool is_phone_value(std::string_view value, bool column_mode);
bool is_app_version_value(std::string_view value, bool column_mode);
bool looks_like_employee_id(
    std::string_view value,
    const std::vector<std::string>& prefixes,
    bool column_mode
);

// subtype, canonical. Empty optional = not a phone.
std::optional<std::pair<std::string, std::string>> classify_phone(
    std::string_view value,
    bool column_mode
);

struct PhoneSpan {
    std::uint32_t start = 0;
    std::uint32_t end = 0;
    std::string original;
    std::string canonical;
    std::string subtype;
};

struct TokenSpan {
    std::uint32_t start = 0;
    std::uint32_t end = 0;
    std::string original;
};

std::vector<PhoneSpan> find_phones(std::string_view text);
std::vector<TokenSpan> find_app_versions(std::string_view text);
std::vector<TokenSpan> find_employee_ids(
    std::string_view text,
    const std::vector<std::string>& prefixes
);

}  // namespace maskit::core

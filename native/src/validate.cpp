#include "maskit/core/validate.hpp"

#include "maskit/core/normalize.hpp"

#include <algorithm>
#include <cctype>
#include <cstring>

namespace maskit::core {
namespace {

constexpr int kIdWeights[17] = {7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2};
constexpr const char* kIdCheck = "10X98765432";

std::string upper_ascii(std::string s) {
    for (char& c : s) {
        if (c >= 'a' && c <= 'z') {
            c = static_cast<char>(c - 'a' + 'A');
        }
    }
    return s;
}

bool is_digit(char32_t c) {
    return c >= U'0' && c <= U'9';
}

bool date_fullmatch(std::string_view s) {
    // ^(?:19|20)\d{2}[./\-]\d{1,2}(?:[./\-]\d{1,2})?$
    if (s.size() < 7 || s.size() > 10) {
        return false;
    }
    if (!((s[0] == '1' && s[1] == '9') || (s[0] == '2' && s[1] == '0'))) {
        return false;
    }
    if (!std::isdigit(static_cast<unsigned char>(s[2])) ||
        !std::isdigit(static_cast<unsigned char>(s[3]))) {
        return false;
    }
    if (s[4] != '.' && s[4] != '/' && s[4] != '-') {
        return false;
    }
    std::size_t i = 5;
    int n1 = 0;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i])) && n1 < 2) {
        ++n1;
        ++i;
    }
    if (n1 == 0) {
        return false;
    }
    if (i == s.size()) {
        return true;
    }
    if (s[i] != '.' && s[i] != '/' && s[i] != '-') {
        return false;
    }
    ++i;
    int n2 = 0;
    while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i])) && n2 < 2) {
        ++n2;
        ++i;
    }
    return n2 > 0 && i == s.size();
}

bool mobile_canon(std::string_view body) {
    if (body.size() != 11) {
        return false;
    }
    if (body[0] != '1' || body[1] < '3' || body[1] > '9') {
        return false;
    }
    for (char c : body) {
        if (c < '0' || c > '9') {
            return false;
        }
    }
    return true;
}

bool land_compact_ok(std::string_view compact) {
    if (compact.size() < 10 || compact.size() > 12) {
        return false;
    }
    if (compact[0] != '0') {
        return false;
    }
    for (char c : compact) {
        if (c < '0' || c > '9') {
            return false;
        }
    }
    return true;
}

bool has_sep(std::string_view s) {
    return s.find(' ') != std::string_view::npos || s.find('-') != std::string_view::npos;
}

bool landline_token_fullmatch(std::string_view s) {
    // (?:\+?86|0086)[\s\-]? optional, then 0\d{2,3}[\s\-]\d{7,8}(?:[\s\-]\d{1,6})?
    std::string_view t = s;
    if (t.size() >= 4 && t.substr(0, 4) == "0086") {
        t.remove_prefix(4);
        if (!t.empty() && (t[0] == ' ' || t[0] == '-')) {
            t.remove_prefix(1);
        }
    } else if (t.size() >= 3 && t.substr(0, 3) == "+86") {
        t.remove_prefix(3);
        if (!t.empty() && (t[0] == ' ' || t[0] == '-')) {
            t.remove_prefix(1);
        }
    } else if (t.size() >= 2 && t.substr(0, 2) == "86") {
        t.remove_prefix(2);
        if (!t.empty() && (t[0] == ' ' || t[0] == '-')) {
            t.remove_prefix(1);
        }
    }
    if (t.empty() || t[0] != '0') {
        return false;
    }
    std::size_t i = 1;
    int area = 0;
    while (i < t.size() && std::isdigit(static_cast<unsigned char>(t[i])) && area < 3) {
        ++area;
        ++i;
    }
    if (area < 2 || i >= t.size() || (t[i] != ' ' && t[i] != '-')) {
        return false;
    }
    ++i;
    int local = 0;
    while (i < t.size() && std::isdigit(static_cast<unsigned char>(t[i])) && local < 8) {
        ++local;
        ++i;
    }
    if (local < 7) {
        return false;
    }
    if (i == t.size()) {
        return true;
    }
    if (t[i] != ' ' && t[i] != '-') {
        return false;
    }
    ++i;
    int ext = 0;
    while (i < t.size() && std::isdigit(static_cast<unsigned char>(t[i])) && ext < 6) {
        ++ext;
        ++i;
    }
    return ext >= 1 && i == t.size();
}

bool is_ip_shaped(std::string_view value) {
    std::string body(value);
    if (!body.empty() && (body[0] == 'v' || body[0] == 'V')) {
        body.erase(0, 1);
    }
    int parts = 0;
    std::size_t i = 0;
    while (i < body.size()) {
        if (parts > 0) {
            if (body[i] != '.') {
                return false;
            }
            ++i;
        }
        if (i >= body.size() || !std::isdigit(static_cast<unsigned char>(body[i]))) {
            return false;
        }
        int n = 0;
        int digits = 0;
        while (i < body.size() && std::isdigit(static_cast<unsigned char>(body[i]))) {
            n = n * 10 + (body[i] - '0');
            ++digits;
            ++i;
            if (digits > 3) {
                return false;
            }
        }
        if (n > 255) {
            return false;
        }
        ++parts;
    }
    return parts == 4;
}

bool version_column_token(std::string_view s) {
    // ^[vV]?\d+(?:\.\d+){1,3}$
    std::string_view t = s;
    if (!t.empty() && (t[0] == 'v' || t[0] == 'V')) {
        t.remove_prefix(1);
    }
    int groups = 0;
    std::size_t i = 0;
    while (i < t.size()) {
        if (groups > 0) {
            if (t[i] != '.') {
                return false;
            }
            ++i;
        }
        int digits = 0;
        while (i < t.size() && std::isdigit(static_cast<unsigned char>(t[i]))) {
            ++digits;
            ++i;
        }
        if (digits == 0) {
            return false;
        }
        ++groups;
        if (groups > 4) {
            return false;
        }
    }
    return groups >= 2 && groups <= 4;
}

bool v_prefix_fullmatch(std::string_view s) {
    if (s.empty() || (s[0] != 'v' && s[0] != 'V')) {
        return false;
    }
    return version_column_token(s);
}

int match_cc(const std::vector<char32_t>& cps, std::size_t i) {
    // returns extra length consumed, 0 if none
    auto eq = [&](std::size_t j, const char* s) {
        std::size_t n = std::strlen(s);
        if (j + n > cps.size()) {
            return false;
        }
        for (std::size_t k = 0; k < n; ++k) {
            if (cps[j + k] != static_cast<char32_t>(s[k])) {
                return false;
            }
        }
        return true;
    };
    std::size_t n = 0;
    if (eq(i, "0086")) {
        n = 4;
    } else if (eq(i, "+86")) {
        n = 3;
    } else if (eq(i, "86")) {
        n = 2;
    } else if (i < cps.size() && cps[i] == U'+' && eq(i + 1, "86")) {
        n = 3;
    }
    if (n == 0) {
        return 0;
    }
    std::size_t j = i + n;
    if (j < cps.size() && (cps[j] == U' ' || cps[j] == U'-')) {
        ++j;
    }
    return static_cast<int>(j - i);
}

int match_mobile_body(const std::vector<char32_t>& cps, std::size_t i) {
    // 1[3-9]\d(?:[\s\-]?\d){8}
    if (i + 2 >= cps.size() || cps[i] != U'1' || cps[i + 1] < U'3' || cps[i + 1] > U'9' ||
        !is_digit(cps[i + 2])) {
        return 0;
    }
    std::size_t j = i + 3;
    for (int k = 0; k < 8; ++k) {
        if (j < cps.size() && (cps[j] == U' ' || cps[j] == U'-')) {
            ++j;
        }
        if (j >= cps.size() || !is_digit(cps[j])) {
            return 0;
        }
        ++j;
    }
    return static_cast<int>(j - i);
}

int match_landline_body(const std::vector<char32_t>& cps, std::size_t i) {
    // 0\d{2,3}[\s\-]\d{7,8}(?:[\s\-]\d{1,6})?
    if (i >= cps.size() || cps[i] != U'0') {
        return 0;
    }
    std::size_t j = i + 1;
    int area = 0;
    while (j < cps.size() && is_digit(cps[j]) && area < 3) {
        ++area;
        ++j;
    }
    if (area < 2 || j >= cps.size() || (cps[j] != U' ' && cps[j] != U'-')) {
        return 0;
    }
    ++j;
    int local = 0;
    while (j < cps.size() && is_digit(cps[j]) && local < 8) {
        ++local;
        ++j;
    }
    if (local < 7) {
        return 0;
    }
    if (j < cps.size() && (cps[j] == U' ' || cps[j] == U'-')) {
        std::size_t k = j + 1;
        int ext = 0;
        while (k < cps.size() && is_digit(cps[k]) && ext < 6) {
            ++ext;
            ++k;
        }
        if (ext >= 1) {
            j = k;
        }
    }
    return static_cast<int>(j - i);
}

bool prev_digit(const std::vector<char32_t>& cps, std::size_t i) {
    return i > 0 && is_digit(cps[i - 1]);
}

bool next_digit(const std::vector<char32_t>& cps, std::size_t i) {
    return i < cps.size() && is_digit(cps[i]);
}

bool prefix_token(std::string_view s, std::string& left, std::string& right) {
    // ([A-Za-z][A-Za-z0-9]*)-([A-Za-z0-9]{4,})
    auto dash = s.find('-');
    if (dash == std::string_view::npos || dash == 0) {
        return false;
    }
    if (!std::isalpha(static_cast<unsigned char>(s[0]))) {
        return false;
    }
    for (std::size_t i = 1; i < dash; ++i) {
        if (!std::isalnum(static_cast<unsigned char>(s[i]))) {
            return false;
        }
    }
    if (s.size() - dash - 1 < 4) {
        return false;
    }
    for (std::size_t i = dash + 1; i < s.size(); ++i) {
        if (!std::isalnum(static_cast<unsigned char>(s[i]))) {
            return false;
        }
    }
    left.assign(s.substr(0, dash));
    right.assign(s.substr(dash + 1));
    return true;
}

bool starts_any_prefix(std::string_view upper, const std::vector<std::string>& prefixes) {
    for (const auto& p : prefixes) {
        if (p.empty()) {
            continue;
        }
        std::string u = upper_ascii(p);
        if (upper.size() >= u.size() && upper.substr(0, u.size()) == u) {
            return true;
        }
    }
    return false;
}

bool context_at(const std::vector<char32_t>& cps, std::size_t i, std::size_t* consumed) {
    static const char32_t* kCn[] = {U"版本号", U"软件版本", U"版本"};
    static const char* kEn[] = {"version", "ver", "build", "release"};
    for (auto* w : kCn) {
        std::size_t n = 0;
        while (w[n] != 0) {
            ++n;
        }
        if (i + n <= cps.size()) {
            bool ok = true;
            for (std::size_t k = 0; k < n; ++k) {
                if (cps[i + k] != w[k]) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                *consumed = n;
                return true;
            }
        }
    }
    auto lower = [](char32_t c) -> char32_t {
        if (c >= U'A' && c <= U'Z') {
            return static_cast<char32_t>(c - U'A' + U'a');
        }
        return c;
    };
    for (auto* w : kEn) {
        std::size_t n = std::strlen(w);
        if (i + n > cps.size()) {
            continue;
        }
        bool ok = true;
        for (std::size_t k = 0; k < n; ++k) {
            if (lower(cps[i + k]) != static_cast<char32_t>(w[k])) {
                ok = false;
                break;
            }
        }
        if (!ok) {
            continue;
        }
        if (i > 0 && ((cps[i - 1] >= U'A' && cps[i - 1] <= U'Z') ||
                      (cps[i - 1] >= U'a' && cps[i - 1] <= U'z') ||
                      is_digit(cps[i - 1]))) {
            continue;
        }
        *consumed = n;
        return true;
    }
    return false;
}

bool eid_context_at(const std::vector<char32_t>& cps, std::size_t i, std::size_t* consumed) {
    static const char32_t* kCn[] = {U"员工编号", U"人员编号", U"员工号", U"员工id", U"工号"};
    static const char* kEn[] = {"employee id", "employee no", "staff id", "eid"};
    for (auto* w : kCn) {
        std::size_t n = 0;
        while (w[n] != 0) {
            ++n;
        }
        if (i + n <= cps.size()) {
            bool ok = true;
            for (std::size_t k = 0; k < n; ++k) {
                if (cps[i + k] != w[k] &&
                    !(w[k] == U'i' && (cps[i + k] == U'I' || cps[i + k] == U'i')) &&
                    !(w[k] == U'd' && (cps[i + k] == U'D' || cps[i + k] == U'd'))) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                *consumed = n;
                return true;
            }
        }
    }
    auto lower = [](char32_t c) -> char32_t {
        if (c >= U'A' && c <= U'Z') {
            return static_cast<char32_t>(c - U'A' + U'a');
        }
        return c;
    };
    for (auto* w : kEn) {
        std::size_t n = std::strlen(w);
        if (i + n > cps.size()) {
            continue;
        }
        bool ok = true;
        for (std::size_t k = 0; k < n; ++k) {
            char32_t want = static_cast<char32_t>(w[k]);
            if (want == U' ') {
                if (cps[i + k] != U' ' && cps[i + k] != U'\t') {
                    ok = false;
                    break;
                }
            } else if (lower(cps[i + k]) != want) {
                ok = false;
                break;
            }
        }
        if (ok) {
            *consumed = n;
            return true;
        }
    }
    return false;
}

void skip_sep(const std::vector<char32_t>& cps, std::size_t* i) {
    while (*i < cps.size() && (cps[*i] == U' ' || cps[*i] == U'\t')) {
        ++*i;
    }
    if (*i < cps.size() &&
        (cps[*i] == U':' || cps[*i] == U'：' || cps[*i] == U'=' || cps[*i] == U'＝')) {
        ++*i;
    }
    while (*i < cps.size() && (cps[*i] == U' ' || cps[*i] == U'\t')) {
        ++*i;
    }
}

int match_version_token(const std::vector<char32_t>& cps, std::size_t i, bool allow_v) {
    std::size_t j = i;
    if (allow_v && j < cps.size() && (cps[j] == U'v' || cps[j] == U'V')) {
        ++j;
    }
    auto start = j;
    std::string token;
    while (j < cps.size()) {
        if (is_digit(cps[j]) || cps[j] == U'.') {
            token.push_back(static_cast<char>(cps[j]));
            ++j;
        } else {
            break;
        }
    }
    if (start == j) {
        return 0;
    }
    std::string whole;
    if (allow_v && i < cps.size() && (cps[i] == U'v' || cps[i] == U'V')) {
        whole.push_back(static_cast<char>(cps[i]));
    }
    whole += token;
    if (!version_column_token(whole) && !version_column_token(token)) {
        return 0;
    }
    if (j < cps.size() && ((cps[j] >= U'A' && cps[j] <= U'Z') || (cps[j] >= U'a' && cps[j] <= U'z') ||
                           is_digit(cps[j]))) {
        return 0;
    }
    return static_cast<int>(j - i);
}

int match_eid_token(const std::vector<char32_t>& cps, std::size_t i) {
    // [A-Za-z][A-Za-z0-9]*-\d{4,}  or  [A-Za-z]\d{4,}
    if (i >= cps.size() ||
        !((cps[i] >= U'A' && cps[i] <= U'Z') || (cps[i] >= U'a' && cps[i] <= U'z'))) {
        return 0;
    }
    std::size_t j = i + 1;
    while (j < cps.size() &&
           ((cps[j] >= U'A' && cps[j] <= U'Z') || (cps[j] >= U'a' && cps[j] <= U'z') ||
            is_digit(cps[j]) || cps[j] == U'-')) {
        ++j;
    }
    std::string tok;
    tok.reserve(j - i);
    for (std::size_t k = i; k < j; ++k) {
        tok.push_back(static_cast<char>(cps[k]));
    }
    auto dash = tok.find('-');
    if (dash != std::string::npos) {
        int digits = 0;
        for (std::size_t k = dash + 1; k < tok.size(); ++k) {
            if (!std::isdigit(static_cast<unsigned char>(tok[k]))) {
                return 0;
            }
            ++digits;
        }
        if (digits < 4) {
            return 0;
        }
        return static_cast<int>(j - i);
    }
    if (tok.size() >= 5 && std::isalpha(static_cast<unsigned char>(tok[0]))) {
        bool rest_digit = true;
        for (std::size_t k = 1; k < tok.size(); ++k) {
            if (!std::isdigit(static_cast<unsigned char>(tok[k]))) {
                rest_digit = false;
                break;
            }
        }
        if (rest_digit && tok.size() >= 5) {
            return static_cast<int>(j - i);
        }
    }
    return 0;
}

}  // namespace

bool id_card_checksum_ok(std::string_view value) {
    std::string compact = upper_ascii(canonical_id_card(std::string(nfkc_half(value))));
    if (compact.size() != 18) {
        return false;
    }
    for (int i = 0; i < 17; ++i) {
        if (compact[static_cast<std::size_t>(i)] < '0' || compact[static_cast<std::size_t>(i)] > '9') {
            return false;
        }
    }
    char last = compact[17];
    if (!(last == 'X' || (last >= '0' && last <= '9'))) {
        return false;
    }
    int total = 0;
    for (int i = 0; i < 17; ++i) {
        total += (compact[static_cast<std::size_t>(i)] - '0') * kIdWeights[i];
    }
    return last == kIdCheck[total % 11];
}

bool luhn_ok(std::string_view digits) {
    if (digits.size() < 16 || digits.size() > 19) {
        return false;
    }
    for (char c : digits) {
        if (c < '0' || c > '9') {
            return false;
        }
    }
    int total = 0;
    int idx = 0;
    for (std::size_t p = digits.size(); p-- > 0;) {
        int n = digits[p] - '0';
        if (idx % 2 == 1) {
            n *= 2;
            if (n > 9) {
                n -= 9;
            }
        }
        total += n;
        ++idx;
    }
    return total % 10 == 0;
}

bool is_date_like(std::string_view value) {
    return date_fullmatch(strip_ascii_ws(nfkc_half(value)));
}

std::optional<std::pair<std::string, std::string>> classify_phone(
    std::string_view value,
    bool column_mode
) {
    std::string s = strip_ascii_ws(nfkc_half(value));
    if (s.empty() || is_date_like(s)) {
        return std::nullopt;
    }
    std::string canon = canonical_phone(s);
    std::string body = canon;
    if (body.rfind("+86", 0) == 0) {
        body = body.substr(3);
    }
    if (mobile_canon(body)) {
        return std::make_pair(std::string("mobile"), canon);
    }
    std::string compact = digits_only(body);
    if (land_compact_ok(compact) && compact[0] == '0' && (column_mode || has_sep(s))) {
        return std::make_pair(std::string("landline"), compact);
    }
    return std::nullopt;
}

bool is_phone_value(std::string_view value, bool column_mode) {
    std::string s = strip_ascii_ws(value);
    if (s.empty() || date_fullmatch(s)) {
        return false;
    }
    bool ascii = true;
    for (unsigned char c : s) {
        if (c >= 0x80) {
            ascii = false;
            break;
        }
    }
    if (column_mode && ascii) {
        if (mobile_canon(s)) {
            return true;
        }
        if (!s.empty() && s[0] == '0' && land_compact_ok(s)) {
            return true;
        }
        if (landline_token_fullmatch(s)) {
            return true;
        }
    }
    return classify_phone(s, column_mode).has_value();
}

bool is_app_version_value(std::string_view value, bool column_mode) {
    std::string s = strip_ascii_ws(value);
    if (s.empty() || is_date_like(s) || date_fullmatch(s)) {
        return false;
    }
    if (column_mode) {
        return version_column_token(s);
    }
    return v_prefix_fullmatch(s) ||
           ((!s.empty() && (s[0] == 'v' || s[0] == 'V')) && version_column_token(s));
}

bool looks_like_employee_id(
    std::string_view value,
    const std::vector<std::string>& prefixes,
    bool column_mode
) {
    std::string s = strip_ascii_ws(value);
    if (s.empty()) {
        return false;
    }
    if (!std::isalpha(static_cast<unsigned char>(s[0])) && classify_phone(s, true)) {
        return false;
    }
    std::string left;
    std::string right;
    if (!prefix_token(s, left, right)) {
        return false;
    }
    if (column_mode) {
        return true;
    }
    return starts_any_prefix(upper_ascii(left), prefixes);
}

std::vector<PhoneSpan> find_phones(std::string_view text) {
    std::string scan = nfkc_half(text);
    std::vector<char32_t> cps;
    if (!decode_utf32(scan, cps)) {
        return {};
    }
    std::vector<PhoneSpan> found;
    std::vector<char32_t> orig_cps;
    decode_utf32(text, orig_cps);
    auto take_orig = [&](std::size_t a, std::size_t b) {
        if (a < orig_cps.size() && b <= orig_cps.size()) {
            return encode_utf32(std::vector<char32_t>(orig_cps.begin() + static_cast<std::ptrdiff_t>(a),
                                                      orig_cps.begin() + static_cast<std::ptrdiff_t>(b)));
        }
        return encode_utf32(std::vector<char32_t>(cps.begin() + static_cast<std::ptrdiff_t>(a),
                                                  cps.begin() + static_cast<std::ptrdiff_t>(b)));
    };
    std::vector<std::pair<std::uint32_t, std::uint32_t>> seen;
    auto add = [&](std::size_t start, std::size_t end) {
        for (auto [s, e] : seen) {
            if (s == start && e == end) {
                return;
            }
        }
        std::string orig = take_orig(start, end);
        auto classified = classify_phone(orig, false);
        if (!classified) {
            return;
        }
        seen.emplace_back(static_cast<std::uint32_t>(start), static_cast<std::uint32_t>(end));
        PhoneSpan hit;
        hit.start = static_cast<std::uint32_t>(start);
        hit.end = static_cast<std::uint32_t>(end);
        hit.original = orig;
        hit.subtype = classified->first;
        hit.canonical = classified->second;
        found.push_back(std::move(hit));
    };
    for (std::size_t i = 0; i < cps.size(); ++i) {
        if (prev_digit(cps, i)) {
            continue;
        }
        int cc = match_cc(cps, i);
        std::size_t body_at = i + static_cast<std::size_t>(cc);
        int mob = match_mobile_body(cps, body_at);
        if (mob > 0 && !next_digit(cps, body_at + static_cast<std::size_t>(mob))) {
            add(i, body_at + static_cast<std::size_t>(mob));
        }
        int land = match_landline_body(cps, body_at);
        if (land > 0 && !next_digit(cps, body_at + static_cast<std::size_t>(land))) {
            add(i, body_at + static_cast<std::size_t>(land));
        }
    }
    std::sort(found.begin(), found.end(), [](const PhoneSpan& a, const PhoneSpan& b) {
        if (a.start != b.start) {
            return a.start < b.start;
        }
        return (a.end - a.start) > (b.end - b.start);
    });
    return found;
}

std::vector<TokenSpan> find_app_versions(std::string_view text) {
    std::vector<char32_t> cps;
    if (!decode_utf32(text, cps)) {
        return {};
    }
    std::vector<TokenSpan> hits;
    std::vector<std::pair<std::uint32_t, std::uint32_t>> seen;
    auto add = [&](std::size_t start, std::size_t end, const std::string& orig) {
        if (is_date_like(orig) || date_fullmatch(strip_ascii_ws(orig)) || is_ip_shaped(orig)) {
            return;
        }
        for (auto [s, e] : seen) {
            if (s == start && e == end) {
                return;
            }
        }
        seen.emplace_back(static_cast<std::uint32_t>(start), static_cast<std::uint32_t>(end));
        TokenSpan t;
        t.start = static_cast<std::uint32_t>(start);
        t.end = static_cast<std::uint32_t>(end);
        t.original = orig;
        hits.push_back(std::move(t));
    };
    for (std::size_t i = 0; i < cps.size(); ++i) {
        if ((cps[i] == U'v' || cps[i] == U'V')) {
            bool boundary = (i == 0) ||
                            !((cps[i - 1] >= U'A' && cps[i - 1] <= U'Z') ||
                              (cps[i - 1] >= U'a' && cps[i - 1] <= U'z') || is_digit(cps[i - 1]));
            int n = match_version_token(cps, i, true);
            if (boundary && n > 0) {
                add(i, i + static_cast<std::size_t>(n),
                    encode_utf32(std::vector<char32_t>(
                        cps.begin() + static_cast<std::ptrdiff_t>(i),
                        cps.begin() + static_cast<std::ptrdiff_t>(i + static_cast<std::size_t>(n))
                    )));
            }
        }
        std::size_t consumed = 0;
        if (context_at(cps, i, &consumed)) {
            std::size_t j = i + consumed;
            skip_sep(cps, &j);
            int n = match_version_token(cps, j, true);
            if (n > 0) {
                add(j, j + static_cast<std::size_t>(n),
                    encode_utf32(std::vector<char32_t>(
                        cps.begin() + static_cast<std::ptrdiff_t>(j),
                        cps.begin() + static_cast<std::ptrdiff_t>(j + static_cast<std::size_t>(n))
                    )));
            }
        }
    }
    return hits;
}

std::vector<TokenSpan> find_employee_ids(
    std::string_view text,
    const std::vector<std::string>& prefixes
) {
    std::vector<char32_t> cps;
    if (!decode_utf32(text, cps)) {
        return {};
    }
    std::vector<TokenSpan> hits;
    std::vector<std::string> seen;
    auto add = [&](std::size_t start, std::size_t end, const std::string& orig) {
        if (std::find(seen.begin(), seen.end(), orig) != seen.end()) {
            return;
        }
        if (classify_phone(orig, true)) {
            return;
        }
        seen.push_back(orig);
        TokenSpan t;
        t.start = static_cast<std::uint32_t>(start);
        t.end = static_cast<std::uint32_t>(end);
        t.original = orig;
        hits.push_back(std::move(t));
    };
    for (std::size_t i = 0; i < cps.size(); ++i) {
        if ((cps[i] >= U'A' && cps[i] <= U'Z') || (cps[i] >= U'a' && cps[i] <= U'z')) {
            std::size_t j = i + 1;
            while (j < cps.size() &&
                   ((cps[j] >= U'A' && cps[j] <= U'Z') || (cps[j] >= U'a' && cps[j] <= U'z') ||
                    is_digit(cps[j]) || cps[j] == U'-')) {
                ++j;
            }
            std::string tok = encode_utf32(std::vector<char32_t>(
                cps.begin() + static_cast<std::ptrdiff_t>(i),
                cps.begin() + static_cast<std::ptrdiff_t>(j)
            ));
            std::string left;
            std::string right;
            if (prefix_token(tok, left, right) && starts_any_prefix(upper_ascii(left), prefixes)) {
                add(i, j, tok);
            }
        }
        std::size_t consumed = 0;
        if (eid_context_at(cps, i, &consumed)) {
            std::size_t j = i + consumed;
            skip_sep(cps, &j);
            int n = match_eid_token(cps, j);
            if (n > 0) {
                std::string orig = encode_utf32(std::vector<char32_t>(
                    cps.begin() + static_cast<std::ptrdiff_t>(j),
                    cps.begin() + static_cast<std::ptrdiff_t>(j + static_cast<std::size_t>(n))
                ));
                add(j, j + static_cast<std::size_t>(n), orig);
            }
        }
    }
    return hits;
}

}  // namespace maskit::core

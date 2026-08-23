#include "maskit/core/normalize.hpp"
#include "maskit/core/resolve.hpp"
#include "maskit/core/validate.hpp"

#include <iostream>
#include <string>
#include <vector>

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

    expect(id_card_checksum_ok("110101199003077774"), "valid id");
    expect(!id_card_checksum_ok("110101199003077777"), "invalid id");
    expect(id_card_checksum_ok("110101 19900307 7774"), "spaced id");
    expect(luhn_ok("4111111111111111"), "luhn visa");
    expect(!luhn_ok("6222021234567890"), "luhn fail");
    expect(is_date_like("2019.06.22"), "date");
    expect(!is_date_like("13800138000"), "phone not date");
    expect(is_phone_value("13800138000", true), "mobile column");
    expect(!is_phone_value("2019.06.22", true), "date veto");
    auto mob = classify_phone("１３８００１３８０００", true);
    expect(mob && mob->first == "mobile", "fullwidth mobile");
    expect(to_halfwidth("ＡＢ") == "AB", "halfwidth");
    expect(is_app_version_value("v1.2.3", true), "version v");
    expect(!is_app_version_value("2024.1.1", true), "version date");
    std::vector<std::string> prefixes{"EID", "EMP", "STAFF"};
    expect(looks_like_employee_id("EID-10001", prefixes, false), "eid prefix");
    expect(!looks_like_employee_id("ISO-8601", prefixes, false), "iso not eid");

    RankedHit a;
    a.entity_type = "id_card";
    a.original_value = "110101 19900307 7774";
    a.confidence = 0.80;
    a.recognizer = "regex";
    a.reason = "variant";
    a.start = 0;
    a.end = 20;
    a.index = 0;
    RankedHit b = a;
    b.original_value = "110101199003077774";
    b.confidence = 1.0;
    b.recognizer = "checksum";
    b.reason = "compact";
    b.end = 18;
    b.index = 1;
    auto merged = merge_hits({a, b}, 20);
    expect(merged.kept_indices.size() == 1, "merge one");
    expect(merged.kept_indices[0] == 0, "longer wins");
    expect(merged.trace.size() == 1 && merged.trace[0].reason_code == std::string(kReasonOutranks),
           "outranks code");

    return g_failed == 0 ? 0 : 1;
}

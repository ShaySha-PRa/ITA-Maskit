#include "maskit/core/detect.hpp"

#include "maskit/core/normalize.hpp"
#include "maskit/core/resolve.hpp"
#include "maskit/core/threads.hpp"
#include "maskit/core/validate.hpp"

#ifdef MASKIT_USE_OPENMP
#include <omp.h>
#endif

namespace maskit::core {
namespace {

std::string upper_copy(std::string s) {
    for (char& c : s) {
        if (c >= 'a' && c <= 'z') {
            c = static_cast<char>(c - 'a' + 'A');
        }
    }
    return s;
}

NativeHit phone_hit(
    std::string orig,
    std::string canon,
    std::string subtype,
    bool column,
    std::optional<int> start,
    std::optional<int> end
) {
    NativeHit h;
    h.entity_type = "phone";
    h.original_value = std::move(orig);
    h.normalized_value = std::move(canon);
    h.confidence = column ? 0.95 : (subtype == "mobile" ? 0.93 : 0.91);
    h.recognizer = "phone";
    h.reason = column ? ("phone column " + subtype) : ("phone " + subtype);
    h.evidence = column ? "column+validator" : "validated";
    h.validation_status = "VALID";
    h.subtype = std::move(subtype);
    h.start = start;
    h.end = end;
    return h;
}

}  // namespace

std::optional<NativeHit> detect_column_value(
    std::string_view value,
    std::string_view entity_type,
    const std::vector<std::string>& prefixes
) {
    std::string raw(value);
    std::string s = strip_ascii_ws(raw);
    if (s.empty() || (!s.empty() && s[0] == '=')) {
        return std::nullopt;
    }
    if (entity_type == "phone") {
        auto c = classify_phone(s, true);
        if (!c) {
            return std::nullopt;
        }
        return phone_hit(s, c->second, c->first, true, std::nullopt, std::nullopt);
    }
    if (entity_type == "app_version") {
        if (!is_app_version_value(s, true)) {
            return std::nullopt;
        }
        NativeHit h;
        h.entity_type = "app_version";
        h.original_value = s;
        h.normalized_value = s;
        for (char& c : h.normalized_value) {
            if (c >= 'A' && c <= 'Z') {
                c = static_cast<char>(c - 'A' + 'a');
            }
        }
        h.confidence = 0.90;
        h.recognizer = "app_version";
        h.reason = "app_version column";
        h.evidence = "column+validator";
        h.validation_status = "VALID";
        return h;
    }
    if (entity_type == "employee_id") {
        if (!looks_like_employee_id(s, prefixes, true)) {
            return std::nullopt;
        }
        NativeHit h;
        h.entity_type = "employee_id";
        h.original_value = s;
        h.normalized_value = upper_copy(s);
        h.confidence = 0.92;
        h.recognizer = "employee_id";
        h.reason = "employee_id column+prefix";
        h.evidence = "column+prefix";
        h.validation_status = "VALID";
        return h;
    }
    if (entity_type == "id_card") {
        if (!id_card_checksum_ok(s) && canonical_id_card(s).size() != 18) {
            return std::nullopt;
        }
        bool ok = id_card_checksum_ok(s);
        NativeHit h;
        h.entity_type = "id_card";
        h.original_value = s;
        h.normalized_value = upper_copy(canonical_id_card(s));
        h.confidence = ok ? 1.0 : 0.45;
        h.recognizer = "checksum";
        h.reason = ok ? "GB 11643 checksum ok" : "GB 11643 checksum failed";
        h.evidence = "checksum";
        h.validation_status = ok ? "VALID" : "INVALID";
        return h;
    }
    if (entity_type == "bank_card") {
        std::string digits = canonical_bank_card(s);
        if (digits.size() < 16 || digits.size() > 19) {
            return std::nullopt;
        }
        bool ok = luhn_ok(digits);
        NativeHit h;
        h.entity_type = "bank_card";
        h.original_value = s;
        h.normalized_value = digits;
        h.confidence = ok ? 1.0 : 0.45;
        h.recognizer = "checksum";
        h.reason = ok ? "Luhn checksum ok" : "Luhn checksum failed";
        h.evidence = "checksum";
        h.validation_status = ok ? "VALID" : "INVALID";
        return h;
    }
    return std::nullopt;
}

std::vector<std::optional<NativeHit>> detect_column_batch(
    const std::vector<std::string>& values,
    std::string_view entity_type,
    const std::vector<std::string>& prefixes
) {
    std::vector<std::optional<NativeHit>> out(values.size());
    int threads = effective_threads(values.size());
    (void)threads;
#ifdef MASKIT_USE_OPENMP
#pragma omp parallel for schedule(static) num_threads(threads)
    for (int i = 0; i < static_cast<int>(values.size()); ++i) {
        out[static_cast<std::size_t>(i)] =
            detect_column_value(values[static_cast<std::size_t>(i)], entity_type, prefixes);
    }
#else
    for (std::size_t i = 0; i < values.size(); ++i) {
        out[i] = detect_column_value(values[i], entity_type, prefixes);
    }
#endif
    return out;
}

std::vector<NativeHit> detect_text_specialized(
    std::string_view text,
    const std::vector<std::string>& prefixes,
    const CompiledDictionary* names,
    bool scan_names
) {
    std::vector<NativeHit> raw;
    (void)names;
    (void)scan_names;
    if (text.empty()) {
        return raw;
    }
    for (const auto& p : find_phones(text)) {
        raw.push_back(phone_hit(
            p.original,
            p.canonical,
            p.subtype,
            false,
            static_cast<int>(p.start),
            static_cast<int>(p.end)
        ));
    }
    for (const auto& v : find_app_versions(text)) {
        NativeHit h;
        h.entity_type = "app_version";
        h.original_value = v.original;
        h.normalized_value = v.original;
        for (char& c : h.normalized_value) {
            if (c >= 'A' && c <= 'Z') {
                c = static_cast<char>(c - 'A' + 'a');
            }
        }
        h.confidence = 0.86;
        h.recognizer = "app_version";
        h.reason = "app_version context";
        h.evidence = "context";
        h.validation_status = "VALID";
        h.start = static_cast<int>(v.start);
        h.end = static_cast<int>(v.end);
        raw.push_back(std::move(h));
    }
    for (const auto& e : find_employee_ids(text, prefixes)) {
        NativeHit h;
        h.entity_type = "employee_id";
        h.original_value = e.original;
        h.normalized_value = upper_copy(e.original);
        h.confidence = 0.88;
        h.recognizer = "employee_id";
        h.reason = "employee_id prefix/context";
        bool pref = false;
        std::string u = h.normalized_value;
        for (const auto& p : prefixes) {
            std::string pu = upper_copy(p);
            if (!pu.empty() && u.rfind(pu, 0) == 0) {
                pref = true;
                break;
            }
        }
        h.evidence = pref ? "prefix" : "context";
        h.validation_status = "VALID";
        h.start = static_cast<int>(e.start);
        h.end = static_cast<int>(e.end);
        raw.push_back(std::move(h));
    }
    std::vector<RankedHit> ranked;
    ranked.reserve(raw.size());
    for (std::size_t i = 0; i < raw.size(); ++i) {
        RankedHit r;
        r.entity_type = raw[i].entity_type;
        r.original_value = raw[i].original_value;
        r.recognizer = raw[i].recognizer;
        r.reason = raw[i].reason;
        r.evidence = raw[i].evidence;
        r.validation_status = raw[i].validation_status;
        r.confidence = raw[i].confidence;
        r.start = raw[i].start;
        r.end = raw[i].end;
        r.index = static_cast<int>(i);
        ranked.push_back(std::move(r));
    }
    auto merged = merge_hits(ranked, static_cast<int>(utf32_length(text)));
    std::vector<NativeHit> kept;
    kept.reserve(merged.kept_indices.size());
    for (int idx : merged.kept_indices) {
        kept.push_back(raw[static_cast<std::size_t>(idx)]);
    }
    return kept;
}

std::vector<std::vector<NativeHit>> detect_text_batch(
    const std::vector<std::string>& texts,
    const std::vector<std::string>& prefixes,
    const CompiledDictionary* names,
    bool scan_names
) {
    std::vector<std::vector<NativeHit>> out(texts.size());
    int threads = effective_threads(texts.size());
    (void)threads;
#ifdef MASKIT_USE_OPENMP
#pragma omp parallel for schedule(static) num_threads(threads)
    for (int i = 0; i < static_cast<int>(texts.size()); ++i) {
        out[static_cast<std::size_t>(i)] =
            detect_text_specialized(texts[static_cast<std::size_t>(i)], prefixes, names, scan_names);
    }
#else
    for (std::size_t i = 0; i < texts.size(); ++i) {
        out[i] = detect_text_specialized(texts[i], prefixes, names, scan_names);
    }
#endif
    return out;
}

}  // namespace maskit::core

#include "maskit/core/resolve.hpp"

#include "maskit/core/normalize.hpp"

#include <algorithm>
#include <map>
#include <string_view>

namespace maskit::core {
namespace {

int evidence_rank(const RankedHit& r) {
    static const std::map<std::string, int> kEvid = {
        {"validated", 50},
        {"column+validator", 45},
        {"column+prefix", 44},
        {"context", 40},
        {"prefix", 38},
        {"column", 30},
        {"person-list span", 28},
        {"person-list exact", 28},
        {"name gazetteer", 26},
        {"semantic prefix name", 24},
        {"semantic prefix/gazetteer company", 24},
        {"surname heuristic (no list)", 18},
        {"regex search", 12},
        {"regex fullmatch", 12},
        {"checksum", 10},
    };
    auto it = kEvid.find(r.evidence);
    int evid = it == kEvid.end() ? 5 : it->second;
    if (it == kEvid.end() && !r.reason.empty()) {
        if (r.reason.rfind("regex", 0) == 0 || r.reason.find("regex") != std::string::npos) {
            evid = std::max(evid, 12);
        }
        if (r.reason.rfind("column", 0) == 0 || r.reason.find("column") != std::string::npos) {
            evid = std::max(evid, 30);
        }
        if (r.reason.rfind("GB 11643 checksum ok", 0) == 0 ||
            r.reason.find("GB 11643 checksum ok") != std::string::npos ||
            r.reason.rfind("Luhn checksum ok", 0) == 0 ||
            r.reason.find("Luhn checksum ok") != std::string::npos ||
            r.reason.find("checksum ok") != std::string::npos) {
            evid = std::max(evid, 55);
        }
    }
    return evid;
}

int valid_rank(std::string_view status) {
    if (status == "VALID") {
        return 2;
    }
    if (status == "INVALID") {
        return 0;
    }
    return 1;
}

int type_rank(std::string_view entity) {
    if (entity == "email") {
        return 80;
    }
    if (entity == "ip") {
        return 78;
    }
    if (entity == "id_card") {
        return 76;
    }
    if (entity == "bank_card") {
        return 74;
    }
    if (entity == "phone") {
        return 72;
    }
    if (entity == "name") {
        return 40;
    }
    if (entity == "company") {
        return 38;
    }
    if (entity == "employee_id") {
        return 20;
    }
    if (entity == "app_version") {
        return 15;
    }
    return 10;
}

struct Key {
    int length;
    int valid;
    int evid;
    double confidence;
    int type;
    int index;
};

Key make_key(const RankedHit& r) {
    return Key{
        static_cast<int>(utf32_length(r.original_value)),
        valid_rank(r.validation_status),
        evidence_rank(r),
        r.confidence,
        type_rank(r.entity_type),
        r.index,
    };
}

bool better(const Key& a, const Key& b) {
    if (a.length != b.length) {
        return a.length > b.length;
    }
    if (a.valid != b.valid) {
        return a.valid > b.valid;
    }
    if (a.evid != b.evid) {
        return a.evid > b.evid;
    }
    if (a.confidence != b.confidence) {
        return a.confidence > b.confidence;
    }
    if (a.type != b.type) {
        return a.type > b.type;
    }
    return a.index < b.index;
}

std::pair<int, int> span_of(const RankedHit& r, int text_len) {
    if (!r.start.has_value() || !r.end.has_value()) {
        return {0, text_len};
    }
    return {*r.start, *r.end};
}

}  // namespace

MergeResult merge_hits(const std::vector<RankedHit>& hits, int text_len) {
    MergeResult out;
    if (hits.empty()) {
        return out;
    }
    std::vector<int> whole;
    for (std::size_t i = 0; i < hits.size(); ++i) {
        if (!hits[i].start.has_value() || !hits[i].end.has_value()) {
            whole.push_back(static_cast<int>(i));
        }
    }
    if (!whole.empty()) {
        std::sort(whole.begin(), whole.end(), [&](int a, int b) {
            return better(make_key(hits[static_cast<std::size_t>(a)]), make_key(hits[static_cast<std::size_t>(b)]));
        });
        out.kept_indices.push_back(whole[0]);
        for (std::size_t i = 1; i < whole.size(); ++i) {
            out.trace.push_back(SuppressRecord{whole[0], whole[i], kReasonWholeCell});
        }
        return out;
    }
    int n = text_len;
    if (n <= 0) {
        for (const auto& h : hits) {
            n = std::max(n, h.end.value_or(0));
        }
    }
    std::vector<int> ranked(hits.size());
    for (std::size_t i = 0; i < hits.size(); ++i) {
        ranked[i] = static_cast<int>(i);
    }
    std::sort(ranked.begin(), ranked.end(), [&](int a, int b) {
        return better(make_key(hits[static_cast<std::size_t>(a)]), make_key(hits[static_cast<std::size_t>(b)]));
    });
    std::vector<std::pair<int, int>> occupied;
    for (int idx : ranked) {
        auto [a, b] = span_of(hits[static_cast<std::size_t>(idx)], n);
        int conflict = -1;
        for (std::size_t k = 0; k < occupied.size(); ++k) {
            int s = occupied[k].first;
            int e = occupied[k].second;
            if (a < e && s < b) {
                conflict = static_cast<int>(k);
                break;
            }
        }
        if (conflict >= 0) {
            out.trace.push_back(
                SuppressRecord{out.kept_indices[static_cast<std::size_t>(conflict)], idx, kReasonOutranks}
            );
            continue;
        }
        out.kept_indices.push_back(idx);
        occupied.emplace_back(a, b);
    }
    std::sort(out.kept_indices.begin(), out.kept_indices.end(), [&](int a, int b) {
        const auto& ha = hits[static_cast<std::size_t>(a)];
        const auto& hb = hits[static_cast<std::size_t>(b)];
        auto la = utf32_length(ha.original_value);
        auto lb = utf32_length(hb.original_value);
        if (la != lb) {
            return la > lb;
        }
        return ha.start.value_or(0) < hb.start.value_or(0);
    });
    return out;
}

}  // namespace maskit::core

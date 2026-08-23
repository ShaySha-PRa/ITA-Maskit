#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace maskit::core {

inline constexpr const char* kReasonWholeCell = "whole_cell_winner";
inline constexpr const char* kReasonOutranks = "outranks";

struct RankedHit {
    std::string entity_type;
    std::string original_value;
    std::string recognizer;
    std::string reason;
    std::string evidence;
    std::string validation_status;
    double confidence = 0.0;
    std::optional<int> start;
    std::optional<int> end;
    int index = 0;
};

struct SuppressRecord {
    int winner_index = -1;
    int suppressed_index = -1;
    std::string reason_code;
};

struct MergeResult {
    std::vector<int> kept_indices;
    std::vector<SuppressRecord> trace;
};

MergeResult merge_hits(const std::vector<RankedHit>& hits, int text_len);

}  // namespace maskit::core

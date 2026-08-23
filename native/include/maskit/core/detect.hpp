#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "maskit/core/dictionary.hpp"

namespace maskit::core {

struct NativeHit {
    std::string entity_type;
    std::string original_value;
    std::string normalized_value;
    double confidence = 0.0;
    std::string recognizer;
    std::string reason;
    std::string evidence;
    std::string validation_status = "UNKNOWN";
    std::string subtype;
    std::optional<int> start;
    std::optional<int> end;
};

// One mapped-column cell. Empty optional = no hit.
std::optional<NativeHit> detect_column_value(
    std::string_view value,
    std::string_view entity_type,
    const std::vector<std::string>& prefixes
);

std::vector<std::optional<NativeHit>> detect_column_batch(
    const std::vector<std::string>& values,
    std::string_view entity_type,
    const std::vector<std::string>& prefixes
);

std::vector<NativeHit> detect_text_specialized(
    std::string_view text,
    const std::vector<std::string>& prefixes,
    const CompiledDictionary* names,
    bool scan_names
);

std::vector<std::vector<NativeHit>> detect_text_batch(
    const std::vector<std::string>& texts,
    const std::vector<std::string>& prefixes,
    const CompiledDictionary* names,
    bool scan_names
);

}  // namespace maskit::core

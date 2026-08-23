#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace maskit::core {

struct PersonSpan {
    std::uint32_t char_start = 0;
    std::uint32_t char_end = 0;
    std::string name;
};

class CompiledDictionary {
public:
    static std::shared_ptr<CompiledDictionary> compile(const std::vector<std::string>& names);

    CompiledDictionary();
    ~CompiledDictionary();
    CompiledDictionary(const CompiledDictionary&) = delete;
    CompiledDictionary& operator=(const CompiledDictionary&) = delete;

    std::size_t size() const;
    std::vector<PersonSpan> match(std::string_view text_utf8) const;
    std::vector<std::vector<PersonSpan>> match_batch(
        const std::vector<std::string>& texts
    ) const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace maskit::core

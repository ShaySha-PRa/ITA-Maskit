#include "maskit/core/dictionary.hpp"

#include <cstdlib>
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
    using maskit::core::CompiledDictionary;

    auto empty = CompiledDictionary::compile({});
    expect(empty->size() == 0, "empty size");
    expect(empty->match("张伟").empty(), "empty dict");

    auto people = CompiledDictionary::compile({"张伟", "司马光", ""});
    expect(people->size() == 2, "size 2");

    auto spans = people->match("经办张伟复核");
    expect(spans.size() == 1, "经办张伟复核 count");
    if (!spans.empty()) {
        expect(spans[0].char_start == 2 && spans[0].char_end == 4, "经办张伟复核 span");
        expect(spans[0].name == "张伟", "经办张伟复核 name");
    }

    expect(people->match("张伟达").empty(), "张伟达 trap");
    expect(people->match("司马光华不是清单名").empty(), "司马光 alone vs 司马光华");

    auto longer = CompiledDictionary::compile({"司马光", "司马光华"});
    auto both = longer->match("司马光华不是清单名");
    expect(both.size() == 1, "both names count");
    if (!both.empty()) {
        expect(both[0].name == "司马光华", "leftmost-longest 司马光华");
        expect(both[0].char_start == 0 && both[0].char_end == 4, "司马光华 span");
    }

    auto dup = CompiledDictionary::compile({"张伟", "张伟"});
    expect(dup->size() == 1, "duplicate names");

    auto mixed = CompiledDictionary::compile({"张伟"});
    auto emo = mixed->match("😀张伟ok");
    expect(emo.size() == 1 && emo[0].char_start == 1 && emo[0].char_end == 3, "emoji offset");

    if (g_failed != 0) {
        std::cerr << g_failed << " failure(s)\n";
        return EXIT_FAILURE;
    }
    std::cout << "maskit_dict_tests ok\n";
    return EXIT_SUCCESS;
}

#include "maskit/core/dictionary.hpp"

#include "maskit/core/errors.hpp"

#include <algorithm>
#include <memory>
#include <unordered_map>
#include <utility>

namespace maskit::core {
namespace {

using U32 = std::u32string;
using U32View = std::u32string_view;

bool is_cjk(char32_t cp) {
    return cp >= 0x4E00 && cp <= 0x9FFF;
}

U32 decode_utf8(std::string_view s) {
    U32 out;
    out.reserve(s.size());
    std::size_t i = 0;
    while (i < s.size()) {
        const auto c = static_cast<unsigned char>(s[i]);
        char32_t cp = 0;
        std::size_t need = 0;
        if (c < 0x80) {
            cp = c;
            need = 1;
        } else if ((c & 0xE0) == 0xC0) {
            cp = c & 0x1F;
            need = 2;
        } else if ((c & 0xF0) == 0xE0) {
            cp = c & 0x0F;
            need = 3;
        } else if ((c & 0xF8) == 0xF0) {
            cp = c & 0x07;
            need = 4;
        } else {
            throw InvalidUtf8Error();
        }
        if (i + need > s.size()) {
            throw InvalidUtf8Error();
        }
        for (std::size_t k = 1; k < need; ++k) {
            const auto cc = static_cast<unsigned char>(s[i + k]);
            if ((cc & 0xC0) != 0x80) {
                throw InvalidUtf8Error();
            }
            cp = (cp << 6) | (cc & 0x3F);
        }
        if ((need == 2 && cp < 0x80) || (need == 3 && cp < 0x800) ||
            (need == 4 && cp < 0x10000) || cp > 0x10FFFF ||
            (cp >= 0xD800 && cp <= 0xDFFF)) {
            throw InvalidUtf8Error();
        }
        out.push_back(cp);
        i += need;
    }
    return out;
}

bool starts_with(U32View text, U32View prefix) {
    return text.size() >= prefix.size() && text.substr(0, prefix.size()) == prefix;
}

const std::vector<U32>& org_suffixes() {
    static const std::vector<U32> v = {
        decode_utf8("公司"), decode_utf8("集团"), decode_utf8("有限"),
        decode_utf8("工作室"), decode_utf8("事务所"), decode_utf8("医院"),
        decode_utf8("银行"), decode_utf8("大学"), decode_utf8("学院"),
        decode_utf8("厂"), decode_utf8("店"), decode_utf8("中心"),
    };
    return v;
}

const std::vector<U32>& contact_suffixes() {
    static const std::vector<U32> v = {
        decode_utf8("邮箱"), decode_utf8("邮件"), decode_utf8("电话"),
        decode_utf8("手机"), decode_utf8("联系"),
    };
    return v;
}

const std::vector<U32>& prose_particles() {
    static const std::vector<U32> v = {
        decode_utf8("均"), decode_utf8("和"), decode_utf8("与"), decode_utf8("及"),
        decode_utf8("等"), decode_utf8("的"), decode_utf8("在"), decode_utf8("于"),
        decode_utf8("已"), decode_utf8("还"), decode_utf8("也"), decode_utf8("称"),
        decode_utf8("说"), decode_utf8("表示"), decode_utf8("出席"),
        decode_utf8("负责"), decode_utf8("来函"), decode_utf8("同志"),
        decode_utf8("先生"), decode_utf8("女士"), decode_utf8("主任"),
        decode_utf8("经理"),
    };
    return v;
}

const std::vector<U32>& sentence_cont() {
    static const std::vector<U32> v = {
        decode_utf8("不"), decode_utf8("没"), decode_utf8("也"), decode_utf8("还"),
        decode_utf8("就"), decode_utf8("都"), decode_utf8("很"), decode_utf8("会"),
        decode_utf8("能"), decode_utf8("要"), decode_utf8("把"), decode_utf8("被"),
        decode_utf8("从"), decode_utf8("向"), decode_utf8("对"), decode_utf8("和"),
        decode_utf8("与"), decode_utf8("及"), decode_utf8("等"), decode_utf8("的"),
        decode_utf8("在"), decode_utf8("于"), decode_utf8("已"),
    };
    return v;
}

const std::vector<U32>& action_suffixes() {
    static const std::vector<U32> v = {
        decode_utf8("负责"), decode_utf8("复核"), decode_utf8("审批"),
        decode_utf8("经办"), decode_utf8("提交"), decode_utf8("确认"),
        decode_utf8("签字"), decode_utf8("录入"), decode_utf8("申请"),
        decode_utf8("离职"), decode_utf8("入职"), decode_utf8("完毕"),
        decode_utf8("出示"), decode_utf8("作证"), decode_utf8("到场"),
    };
    return v;
}

bool starts_with_any(U32View rest, const std::vector<U32>& prefixes) {
    for (const auto& p : prefixes) {
        if (starts_with(rest, p)) {
            return true;
        }
    }
    return false;
}

struct Node {
    std::unordered_map<char32_t, std::unique_ptr<Node>> next;
    bool terminal = false;
    std::string utf8;
    U32 u32;
};

bool name_set_contains(const Node* root, U32View s) {
    const Node* node = root;
    for (char32_t cp : s) {
        auto it = node->next.find(cp);
        if (it == node->next.end()) {
            return false;
        }
        node = it->second.get();
    }
    return node->terminal;
}

bool rest_has_name_prefix(const Node* root, U32View rest) {
    const Node* node = root;
    for (char32_t cp : rest) {
        auto it = node->next.find(cp);
        if (it == node->next.end()) {
            return false;
        }
        node = it->second.get();
        if (node->terminal) {
            return true;
        }
    }
    return false;
}

bool is_boundary_suffix(U32View tail) {
    return starts_with_any(tail, action_suffixes()) ||
           starts_with_any(tail, prose_particles()) ||
           starts_with_any(tail, contact_suffixes()) ||
           starts_with_any(tail, org_suffixes());
}

bool is_longer_name_trap(U32View name, U32View rest, const Node* root) {
    if (rest.empty() || name.empty()) {
        return false;
    }
    if (rest_has_name_prefix(root, rest)) {
        return false;
    }
    if (starts_with_any(rest, contact_suffixes()) ||
        starts_with_any(rest, prose_particles()) ||
        starts_with_any(rest, action_suffixes()) ||
        starts_with_any(rest, sentence_cont()) ||
        starts_with_any(rest, org_suffixes())) {
        return false;
    }
    if (!is_cjk(rest[0])) {
        return false;
    }
    std::size_t i = 0;
    while (i < rest.size() && is_cjk(rest[i])) {
        if (is_boundary_suffix(rest.substr(i))) {
            break;
        }
        ++i;
        if (i >= 4) {
            break;
        }
    }
    if (i == 0) {
        return false;
    }
    U32 combined;
    combined.reserve(name.size() + i);
    combined.append(name);
    combined.append(rest.substr(0, i));
    if (name_set_contains(root, combined)) {
        return false;
    }
    if (combined.size() < 2 || combined.size() > 8) {
        return false;
    }
    for (char32_t cp : combined) {
        if (!is_cjk(cp)) {
            return false;
        }
    }
    return true;
}

}  // namespace

struct CompiledDictionary::Impl {
    std::unique_ptr<Node> root = std::make_unique<Node>();
    std::size_t size = 0;
};

CompiledDictionary::CompiledDictionary() : impl_(std::make_unique<Impl>()) {}
CompiledDictionary::~CompiledDictionary() = default;

std::shared_ptr<CompiledDictionary> CompiledDictionary::compile(
    const std::vector<std::string>& names
) {
    auto dict = std::make_shared<CompiledDictionary>();
    for (const auto& name : names) {
        if (name.empty()) {
            continue;
        }
        U32 u32 = decode_utf8(name);
        Node* node = dict->impl_->root.get();
        for (char32_t cp : u32) {
            auto& slot = node->next[cp];
            if (!slot) {
                slot = std::make_unique<Node>();
            }
            node = slot.get();
        }
        if (!node->terminal) {
            ++dict->impl_->size;
        }
        node->terminal = true;
        node->utf8 = name;
        node->u32 = std::move(u32);
    }
    return dict;
}

std::size_t CompiledDictionary::size() const {
    return impl_->size;
}

std::vector<PersonSpan> CompiledDictionary::match(std::string_view text_utf8) const {
    if (text_utf8.empty() || impl_->size == 0) {
        return {};
    }
    const U32 text = decode_utf8(text_utf8);
    const Node* root = impl_->root.get();
    std::vector<PersonSpan> spans;
    std::size_t i = 0;
    while (i < text.size()) {
        struct Cand {
            std::size_t end;
            const Node* node;
        };
        std::vector<Cand> cands;
        const Node* node = root;
        for (std::size_t j = i; j < text.size(); ++j) {
            auto it = node->next.find(text[j]);
            if (it == node->next.end()) {
                break;
            }
            node = it->second.get();
            if (node->terminal) {
                cands.push_back(Cand{j + 1, node});
            }
        }
        std::sort(cands.begin(), cands.end(), [](const Cand& a, const Cand& b) {
            return a.end > b.end;
        });
        bool matched = false;
        for (const auto& c : cands) {
            const U32View rest(text.data() + c.end, text.size() - c.end);
            if (starts_with_any(rest, org_suffixes())) {
                continue;
            }
            if (is_longer_name_trap(c.node->u32, rest, root)) {
                continue;
            }
            spans.push_back(PersonSpan{
                static_cast<std::uint32_t>(i),
                static_cast<std::uint32_t>(c.end),
                c.node->utf8,
            });
            i = c.end;
            matched = true;
            break;
        }
        if (!matched) {
            ++i;
        }
    }
    return spans;
}

std::vector<std::vector<PersonSpan>> CompiledDictionary::match_batch(
    const std::vector<std::string>& texts
) const {
    std::vector<std::vector<PersonSpan>> out;
    out.reserve(texts.size());
    for (const auto& text : texts) {
        out.push_back(match(text));
    }
    return out;
}

}  // namespace maskit::core

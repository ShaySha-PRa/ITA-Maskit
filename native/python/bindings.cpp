#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <memory>
#include <tuple>

#include "maskit/core/detect.hpp"
#include "maskit/core/dictionary.hpp"
#include "maskit/core/errors.hpp"
#include "maskit/core/normalize.hpp"
#include "maskit/core/pseudonym.hpp"
#include "maskit/core/resolve.hpp"
#include "maskit/core/threads.hpp"
#include "maskit/core/validate.hpp"
#include "maskit/core/version.hpp"

namespace py = pybind11;

namespace {

void register_exceptions(const py::module_& m) {
    static py::exception<maskit::core::NativeError> native_err(m, "NativeError");
    static py::exception<maskit::core::InvalidUtf8Error> utf8_err(m, "InvalidUtf8Error", native_err);
    static py::exception<maskit::core::UnsupportedSchemeError> scheme_err(
        m, "UnsupportedSchemeError", native_err
    );
    static py::exception<maskit::core::BatchSizeError> batch_err(m, "BatchSizeError", native_err);
    static py::exception<maskit::core::NativeInternalError> internal_err(
        m, "NativeInternalError", native_err
    );
    (void)utf8_err;
    (void)scheme_err;
    (void)batch_err;
    (void)internal_err;
}

}  // namespace

PYBIND11_MODULE(_native, m) {
    m.doc() = "ITA-Maskit native core (HMAC, validators, resolve, batch detect)";

    auto hit_to_dict = [](const maskit::core::NativeHit& h) {
        py::dict d;
        d["entity_type"] = h.entity_type;
        d["original_value"] = h.original_value;
        d["normalized_value"] = h.normalized_value;
        d["confidence"] = h.confidence;
        d["recognizer"] = h.recognizer;
        d["reason"] = h.reason;
        d["evidence"] = h.evidence;
        d["validation_status"] = h.validation_status;
        d["subtype"] = h.subtype;
        if (h.start) {
            d["start"] = *h.start;
        } else {
            d["start"] = py::none();
        }
        if (h.end) {
            d["end"] = *h.end;
        } else {
            d["end"] = py::none();
        }
        return d;
    };

    py::class_<maskit::core::CompiledDictionary, std::shared_ptr<maskit::core::CompiledDictionary>>(
        m, "CompiledDictionary"
    )
        .def("size", &maskit::core::CompiledDictionary::size)
        .def(
            "match",
            [](const maskit::core::CompiledDictionary& self, const std::string& text) {
                py::gil_scoped_release release;
                auto spans = self.match(text);
                std::vector<std::tuple<std::uint32_t, std::uint32_t, std::string>> out;
                out.reserve(spans.size());
                for (auto& s : spans) {
                    out.emplace_back(s.char_start, s.char_end, std::move(s.name));
                }
                return out;
            },
            py::arg("text")
        )
        .def(
            "match_batch",
            [](const maskit::core::CompiledDictionary& self,
               const std::vector<std::string>& texts) {
                py::gil_scoped_release release;
                auto batches = self.match_batch(texts);
                std::vector<std::vector<std::tuple<std::uint32_t, std::uint32_t, std::string>>> out;
                out.reserve(batches.size());
                for (auto& spans : batches) {
                    std::vector<std::tuple<std::uint32_t, std::uint32_t, std::string>> row;
                    row.reserve(spans.size());
                    for (auto& s : spans) {
                        row.emplace_back(s.char_start, s.char_end, std::move(s.name));
                    }
                    out.push_back(std::move(row));
                }
                return out;
            },
            py::arg("texts")
        );

    m.def(
        "compile_person_list",
        &maskit::core::CompiledDictionary::compile,
        py::arg("names")
    );
    register_exceptions(m);

    m.def("native_version", &maskit::core::native_version);
    m.def("core_abi_version", &maskit::core::core_abi_version);
    m.def("detector_version", &maskit::core::detector_version);
    m.def("build_compiler", &maskit::core::build_compiler);
    m.def("build_type", &maskit::core::build_type);
    m.def(
        "pseudonym_scheme_versions",
        []() { return std::vector<std::string>{"v1", "v2"}; }
    );

    m.def(
        "hash_v1",
        [](const std::string& value, const std::string& pepper, int length) {
            py::gil_scoped_release release;
            return maskit::core::hash_v1(value, pepper, length);
        },
        py::arg("value"),
        py::arg("pepper"),
        py::arg("length") = 8
    );

    m.def(
        "hash_v2",
        [](const std::string& value,
           const std::string& pepper,
           const std::string& entity_type,
           int length,
           const std::string& normalizer_version) {
            py::gil_scoped_release release;
            return maskit::core::hash_v2(
                value, pepper, entity_type, length, normalizer_version
            );
        },
        py::arg("value"),
        py::arg("pepper"),
        py::arg("entity_type"),
        py::arg("length") = 24,
        py::arg("normalizer_version") = "1"
    );

    m.def(
        "hash_batch",
        [](const std::vector<std::string>& values,
           const std::string& pepper,
           const std::string& scheme,
           const std::vector<std::string>& entity_types,
           int length,
           const std::string& normalizer_version) {
            py::gil_scoped_release release;
            return maskit::core::hash_batch(
                values,
                pepper,
                maskit::core::parse_scheme(scheme),
                entity_types,
                length,
                normalizer_version
            );
        },
        py::arg("values"),
        py::arg("pepper"),
        py::arg("scheme") = "v1",
        py::arg("entity_types") = std::vector<std::string>{},
        py::arg("length") = 8,
        py::arg("normalizer_version") = "1"
    );

    m.def(
        "digits_from_hex",
        [](const std::string& hex, std::size_t n) {
            py::gil_scoped_release release;
            return maskit::core::digits_from_hex(hex, n);
        },
        py::arg("hex"),
        py::arg("n")
    );

    m.def(
        "batch_identity_size",
        [](const std::vector<std::string>& values) {
            py::gil_scoped_release release;
            return values.size();
        },
        py::arg("values")
    );
    m.def("set_native_threads", &maskit::core::set_native_threads, py::arg("n"));
    m.def("native_threads", &maskit::core::native_threads);
    m.def("to_halfwidth", &maskit::core::to_halfwidth, py::arg("text"));
    m.def("nfkc_half", &maskit::core::nfkc_half, py::arg("text"));
    m.def("canonical_phone", &maskit::core::canonical_phone, py::arg("text"));
    m.def("canonical_id_card", &maskit::core::canonical_id_card, py::arg("text"));
    m.def("canonical_bank_card", &maskit::core::canonical_bank_card, py::arg("text"));
    m.def("canonical_email", &maskit::core::canonical_email, py::arg("text"));
    m.def("id_card_checksum_ok", &maskit::core::id_card_checksum_ok, py::arg("value"));
    m.def("luhn_ok", &maskit::core::luhn_ok, py::arg("digits"));
    m.def("is_date_like", &maskit::core::is_date_like, py::arg("value"));
    m.def(
        "is_phone_value",
        [](const std::string& value, bool column_mode) {
            return maskit::core::is_phone_value(value, column_mode);
        },
        py::arg("value"),
        py::arg("column_mode") = false
    );
    m.def(
        "is_app_version_value",
        [](const std::string& value, bool column_mode) {
            return maskit::core::is_app_version_value(value, column_mode);
        },
        py::arg("value"),
        py::arg("column_mode") = false
    );
    m.def(
        "looks_like_employee_id",
        [](const std::string& value, const std::vector<std::string>& prefixes, bool column_mode) {
            return maskit::core::looks_like_employee_id(value, prefixes, column_mode);
        },
        py::arg("value"),
        py::arg("prefixes"),
        py::arg("column_mode") = false
    );
    m.def(
        "classify_phone",
        [](const std::string& value, bool column_mode) -> py::object {
            auto hit = maskit::core::classify_phone(value, column_mode);
            if (!hit) {
                return py::none();
            }
            return py::make_tuple(hit->first, hit->second);
        },
        py::arg("value"),
        py::arg("column_mode") = false
    );
    m.def(
        "merge_hits",
        [](const std::vector<py::dict>& rows, int text_len) {
            std::vector<maskit::core::RankedHit> hits;
            hits.reserve(rows.size());
            for (std::size_t i = 0; i < rows.size(); ++i) {
                const py::dict& d = rows[i];
                maskit::core::RankedHit h;
                h.entity_type = d["entity_type"].cast<std::string>();
                h.original_value = d["original_value"].cast<std::string>();
                h.recognizer = d.contains("recognizer") ? d["recognizer"].cast<std::string>() : "";
                h.reason = d.contains("reason") ? d["reason"].cast<std::string>() : "";
                h.evidence = d.contains("evidence") ? d["evidence"].cast<std::string>() : "";
                h.validation_status =
                    d.contains("validation_status") ? d["validation_status"].cast<std::string>()
                                                    : "UNKNOWN";
                h.confidence = d.contains("confidence") ? d["confidence"].cast<double>() : 0.0;
                if (d.contains("start") && !d["start"].is_none()) {
                    h.start = d["start"].cast<int>();
                }
                if (d.contains("end") && !d["end"].is_none()) {
                    h.end = d["end"].cast<int>();
                }
                h.index = static_cast<int>(i);
                hits.push_back(std::move(h));
            }
            maskit::core::MergeResult merged;
            {
                py::gil_scoped_release release;
                merged = maskit::core::merge_hits(hits, text_len);
            }
            py::list kept;
            for (int idx : merged.kept_indices) {
                kept.append(idx);
            }
            py::list trace;
            for (const auto& t : merged.trace) {
                py::dict row;
                row["winner_index"] = t.winner_index;
                row["suppressed_index"] = t.suppressed_index;
                row["reason_code"] = t.reason_code;
                trace.append(row);
            }
            py::dict out;
            out["kept"] = kept;
            out["trace"] = trace;
            return out;
        },
        py::arg("hits"),
        py::arg("text_len") = 0
    );
    m.def(
        "detect_column_batch",
        [hit_to_dict](
            const std::vector<std::string>& values,
            const std::string& entity_type,
            const std::vector<std::string>& prefixes
        ) {
            std::vector<std::optional<maskit::core::NativeHit>> rows;
            {
                py::gil_scoped_release release;
                rows = maskit::core::detect_column_batch(values, entity_type, prefixes);
            }
            py::list out;
            for (const auto& h : rows) {
                if (h) {
                    out.append(hit_to_dict(*h));
                } else {
                    out.append(py::none());
                }
            }
            return out;
        },
        py::arg("values"),
        py::arg("entity_type"),
        py::arg("prefixes") = std::vector<std::string>{}
    );
    m.def(
        "detect_text_batch",
        [hit_to_dict](
            const std::vector<std::string>& texts,
            const std::vector<std::string>& prefixes,
            std::shared_ptr<maskit::core::CompiledDictionary> names,
            bool scan_names
        ) {
            std::vector<std::vector<maskit::core::NativeHit>> rows;
            {
                py::gil_scoped_release release;
                rows = maskit::core::detect_text_batch(
                    texts, prefixes, names.get(), scan_names
                );
            }
            py::list out;
            for (const auto& row : rows) {
                py::list one;
                for (const auto& h : row) {
                    one.append(hit_to_dict(h));
                }
                out.append(one);
            }
            return out;
        },
        py::arg("texts"),
        py::arg("prefixes") = std::vector<std::string>{},
        py::arg("names") = py::none(),
        py::arg("scan_names") = false
    );
}

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "maskit/core/errors.hpp"
#include "maskit/core/pseudonym.hpp"
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
    m.doc() = "ITA-Maskit native core (HMAC batch + version metadata)";
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
}

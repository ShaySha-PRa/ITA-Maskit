cmake_minimum_required(VERSION 3.16)
project(maskit_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MASKIT_BUILD_PYTHON "Build pybind11 extension" ON)
option(MASKIT_BUILD_TESTS "Build C++ unit tests" ON)

add_library(maskit_core STATIC
    src/crypto.cpp
    src/pseudonym.cpp
    src/dictionary.cpp
    src/version.cpp
)
target_include_directories(maskit_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)
set_target_properties(maskit_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    target_compile_options(maskit_core PRIVATE /W4 /WX /utf-8)
    target_link_libraries(maskit_core PRIVATE bcrypt)
    target_compile_definitions(maskit_core PRIVATE MASKIT_USE_BCRYPT=1)
else()
    target_compile_options(maskit_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
    find_package(OpenSSL REQUIRED)
    target_link_libraries(maskit_core PRIVATE OpenSSL::Crypto)
    target_compile_definitions(maskit_core PRIVATE MASKIT_USE_OPENSSL=1)
endif()

if(MASKIT_BUILD_PYTHON)
    set(PYBIND11_FINDPYTHON ON)
    find_package(Python REQUIRED COMPONENTS Interpreter Development)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE _pybind11_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _pybind11_rc
    )
    if(NOT _pybind11_rc EQUAL 0)
        message(FATAL_ERROR "pybind11 is required: pip install pybind11")
    endif()
    list(APPEND CMAKE_PREFIX_PATH "${_pybind11_dir}")
    find_package(pybind11 CONFIG REQUIRED)

    pybind11_add_module(_native python/bindings.cpp)
    target_link_libraries(_native PRIVATE maskit_core)
    set_target_properties(_native PROPERTIES
        OUTPUT_NAME "_native"
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
        ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
    )
    foreach(cfg IN ITEMS Debug Release RelWithDebInfo MinSizeRel)
        set_target_properties(_native PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY_${cfg} "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
            RUNTIME_OUTPUT_DIRECTORY_${cfg} "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
            ARCHIVE_OUTPUT_DIRECTORY_${cfg} "${CMAKE_CURRENT_SOURCE_DIR}/../maskit"
        )
    endforeach()
    # MSVC multi-config still appends Release/; copy next to maskit/__init__.py.
    add_custom_command(TARGET _native POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "$<TARGET_FILE:_native>"
            "${CMAKE_CURRENT_SOURCE_DIR}/../maskit/$<TARGET_FILE_NAME:_native>"
    )
endif()

if(MASKIT_BUILD_TESTS)
    enable_testing()
    add_executable(maskit_core_tests tests/test_pseudonym.cpp)
    target_link_libraries(maskit_core_tests PRIVATE maskit_core)
    add_test(NAME maskit_core_tests COMMAND maskit_core_tests)

    add_executable(maskit_core_smoke tools/test.cpp)
    target_link_libraries(maskit_core_smoke PRIVATE maskit_core)
    add_test(NAME maskit_core_smoke COMMAND maskit_core_smoke)

    add_executable(maskit_dict_tests tests/test_dictionary.cpp)
    target_link_libraries(maskit_dict_tests PRIVATE maskit_core)
    add_test(NAME maskit_dict_tests COMMAND maskit_dict_tests)
endif()

# N7 Arrow / zero-copy evaluation

Date: 2026-08-23  
Native: 0.2.0 (OpenMP on, WSL Python 3.10.12)

Plan: implement Arrow only if Python list / string conversion ate most of the Native gain.

## Measurement

`batch_identity_size` copies 100k strings into `std::vector<std::string>` and returns the count (no HMAC). Compare that to `hash_batch` v1 on the same list.

| Step | median |
|------|--------|
| Python list retain | 0.0003 s |
| pybind11 conversion (`batch_identity_size`) | 0.0010 s |
| Native HMAC 100k | 0.074 s |
| Conversion / kernel | **1.3%** |

Threshold in the plan: conversion is a bottleneck only if it dominates. 1.3% does not.

## Decision

**Skip Arrow C Data / Stream bindings in V1.**

Reasons:

1. Conversion is ~1% of the HMAC kernel.
2. End-to-end 10k pseudo already improved 1.32× without Arrow.
3. Adding pyarrow would grow the Windows EXE and add a hard optional dep for little gain.
4. The plan forbids a complex first-pass Arrow binding.

Revisit if a later profile shows conversion > 30% of a target kernel (the bench writes `n7_arrow=consider` in that case).

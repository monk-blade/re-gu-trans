cmake_minimum_required(VERSION 3.20)
project(librime_gujarati_model LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(ONNXRUNTIME_ROOT "" CACHE PATH "ONNX Runtime release root")
find_path(ONNXRUNTIME_INCLUDE_DIR onnxruntime_cxx_api.h
  HINTS "${ONNXRUNTIME_ROOT}/include" "${ONNXRUNTIME_ROOT}/include/onnxruntime/core/session")
find_library(ONNXRUNTIME_LIBRARY onnxruntime HINTS "${ONNXRUNTIME_ROOT}/lib")
if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIBRARY)
  message(FATAL_ERROR "Set ONNXRUNTIME_ROOT to an ONNX Runtime C/C++ release")
endif()

add_library(librime-gujarati-model SHARED src/plugin.cc)
target_include_directories(librime-gujarati-model PRIVATE "${ONNXRUNTIME_INCLUDE_DIR}")
target_link_libraries(librime-gujarati-model PRIVATE "${ONNXRUNTIME_LIBRARY}")
set_target_properties(librime-gujarati-model PROPERTIES
  OUTPUT_NAME "rime-gujarati-model"
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN YES)

if(APPLE)
  set_target_properties(librime-gujarati-model PROPERTIES BUILD_RPATH "@loader_path" INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(librime-gujarati-model PROPERTIES BUILD_RPATH "$ORIGIN" INSTALL_RPATH "$ORIGIN")
endif()

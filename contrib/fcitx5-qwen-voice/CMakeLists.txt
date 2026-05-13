cmake_minimum_required(VERSION 3.16)
project(fcitx5-qwen-voice VERSION 0.1.0 LANGUAGES CXX)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FCITX5_CORE REQUIRED IMPORTED_TARGET Fcitx5Core)
pkg_check_modules(FCITX5_UTILS REQUIRED IMPORTED_TARGET Fcitx5Utils)
pkg_check_modules(FCITX5_MODULE REQUIRED IMPORTED_TARGET Fcitx5Module)

add_library(qwenvoicefcitx5 MODULE qwenvoicefcitx5.cpp)
target_compile_features(qwenvoicefcitx5 PRIVATE cxx_std_17)
target_link_libraries(
  qwenvoicefcitx5
  PRIVATE
    PkgConfig::FCITX5_CORE
    PkgConfig::FCITX5_UTILS
    PkgConfig::FCITX5_MODULE
)
set_target_properties(qwenvoicefcitx5 PROPERTIES PREFIX "lib")

install(TARGETS qwenvoicefcitx5 LIBRARY DESTINATION lib/fcitx5)
install(FILES qwenvoicefcitx5.conf DESTINATION share/fcitx5/addon)

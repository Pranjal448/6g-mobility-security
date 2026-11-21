# Out-of-tree driver for the ATK-05a full campaign.  Links against the libraries already
# built in /run/media/pranjal/hdd/mtp/build_env/srsran_full/build .  Touches no srsRAN file.
cmake_minimum_required(VERSION 3.16)
project(atk05a_campaign CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
# Flags copied verbatim from srsRAN's own build.
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=gnu++17 -fno-rtti -march=native -mtune=generic -fno-trapping-math -fno-math-errno -Wno-maybe-uninitialized")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")
add_definitions(-DASSERTS_ENABLED -DBUILD_TYPE_RELEASE)

set(SRS "/run/media/pranjal/hdd/mtp/build_env/srsran_full")
set(SRSB "${SRS}/build")

include_directories(${SRS}/include ${SRS}/lib ${SRS} ${SRS}/external ${SRS}/external/fmt/include)

add_executable(atk05a_campaign atk05a_campaign.cpp)

target_link_libraries(atk05a_campaign
  ${SRSB}/lib/phy/upper/channel_processors/libsrsran_prach_detector.a
  ${SRSB}/lib/phy/support/libsrsran_phy_support.a
  ${SRSB}/lib/phy/generic_functions/libsrsran_dft.a
  ${SRSB}/lib/ran/libsrsran_ran.a
  ${SRSB}/lib/support/libsrsran_support.a
  ${SRSB}/lib/instrumentation/libsrsran_instrumentation.a
  ${SRSB}/lib/srsvec/libsrsvec.a
  ${SRSB}/lib/srslog/libsrslog.a
  ${SRSB}/external/fmt/libfmt.a
  fftw3f pthread dl m)

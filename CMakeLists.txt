cmake_minimum_required(VERSION 3.10)
project(MissileDefense LANGUAGES CXX)

# Prefer an explicit variable, but fall back to the NDDSHOME environment variable
if(NOT DEFINED RTI_CONNEXTDDS_DIR)
  if(DEFINED ENV{NDDSHOME})
    set(RTI_CONNEXTDDS_DIR $ENV{NDDSHOME})
    message(STATUS "Using NDDSHOME for RTI Connext: ${RTI_CONNEXTDDS_DIR}")
  endif()
endif()

# Example usage in downstream targets:
# if(RTI_CONNEXTDDS_DIR)
#   include_directories(${RTI_CONNEXTDDS_DIR}/include)
#   link_directories(${RTI_CONNEXTDDS_DIR}/lib)
# endif()

# If RTI-generated IDL sources exist, build them into a static library usable by apps
if(DEFINED USE_CONNEXT AND USE_CONNEXT)
  file(GLOB RTI_GENERATED_SOURCES ${CMAKE_SOURCE_DIR}/idl/generated/*.cxx ${CMAKE_SOURCE_DIR}/idl/generated/*.cpp)
  if(RTI_GENERATED_SOURCES)
    add_library(ship_types STATIC ${RTI_GENERATED_SOURCES})
    target_include_directories(ship_types PRIVATE ${CMAKE_SOURCE_DIR}/idl ${CMAKE_SOURCE_DIR}/idl/generated)
    if(DEFINED RTI_CONNEXTDDS_DIR)
      target_include_directories(ship_types PRIVATE ${RTI_CONNEXTDDS_DIR}/include ${RTI_CONNEXTDDS_DIR}/include/ndds)
    endif()
    # Required for __declspec(dllimport) on data symbols when linking against dynamic RTI libs
    target_compile_definitions(ship_types PRIVATE
      RTI_WIN32
      RTI_dds_c_DLL_VARIABLE
      RTI_dds_cpp_DLL_VARIABLE
      RTI_osapi_DLL_VARIABLE
      RTI_cdr_DLL_VARIABLE
      RTI_log_DLL_VARIABLE
    )
    set_target_properties(ship_types PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED YES)
  endif()
endif()

# Add project subdirectories (apps, tests, examples)
if(EXISTS ${CMAKE_SOURCE_DIR}/apps/CMakeLists.txt)
  add_subdirectory(apps)
endif()

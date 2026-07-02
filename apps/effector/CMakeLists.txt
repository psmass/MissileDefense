cmake_minimum_required(VERSION 3.10)

add_executable(effector main.cpp)
set_target_properties(effector PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED YES)

target_include_directories(effector PRIVATE
    ${CMAKE_SOURCE_DIR}/idl/generated
    ${CMAKE_SOURCE_DIR}/idl
)

if(USE_CONNEXT)
    if(WIN32)
        set(RTI_LIB_DIR ${RTI_CONNEXTDDS_DIR}/lib/x64Win64VS2017)
    elseif(APPLE)
        set(RTI_LIB_DIR ${RTI_CONNEXTDDS_DIR}/lib/arm64Darwin23clang16.0)
    else()
        set(RTI_LIB_DIR ${RTI_CONNEXTDDS_DIR}/lib)
    endif()

    find_path(RTI_CONNEXTDDS_INCLUDE ndds/ndds_cpp.h PATHS ${RTI_CONNEXTDDS_DIR}/include)

    # Dynamic import libraries (nddscpp.dll, nddsc.dll, nddscore.dll)
    find_library(RTI_LIB_NDDSCPP  nddscpp  PATHS ${RTI_LIB_DIR} NO_DEFAULT_PATH)
    find_library(RTI_LIB_NDDSC    nddsc    PATHS ${RTI_LIB_DIR} NO_DEFAULT_PATH)
    find_library(RTI_LIB_NDDSCORE nddscore PATHS ${RTI_LIB_DIR} NO_DEFAULT_PATH)
    set(RTI_CONNEXTDDS_LIBS ${RTI_LIB_NDDSCPP} ${RTI_LIB_NDDSC} ${RTI_LIB_NDDSCORE})

    if(NOT RTI_CONNEXTDDS_INCLUDE OR NOT RTI_LIB_NDDSCPP OR NOT RTI_LIB_NDDSC OR NOT RTI_LIB_NDDSCORE)
        message(FATAL_ERROR "RTI Connext headers or dynamic libraries not found. Set RTI_CONNEXTDDS_DIR to the RTI install root.")
    endif()
    target_compile_definitions(effector PRIVATE USE_CONNEXT)
    if(WIN32)
        target_compile_definitions(effector PRIVATE
            RTI_WIN32
            RTI_dds_c_DLL_VARIABLE
            RTI_dds_cpp_DLL_VARIABLE
            RTI_osapi_DLL_VARIABLE
            RTI_cdr_DLL_VARIABLE
            RTI_log_DLL_VARIABLE
        )
    elseif(APPLE)
        target_compile_definitions(effector PRIVATE
            RTI_UNIX
            RTI_DARWIN
            RTI_64BIT
        )
    endif()
    target_include_directories(effector PRIVATE
        ${RTI_CONNEXTDDS_INCLUDE}
        ${RTI_CONNEXTDDS_DIR}/include/ndds
    )
    if(TARGET ship_types)
        target_link_libraries(effector PRIVATE ship_types ${RTI_CONNEXTDDS_LIBS})
    else()
        target_link_libraries(effector PRIVATE ${RTI_CONNEXTDDS_LIBS})
    endif()
endif()

cmake_minimum_required(VERSION 3.10)

# Prefer config package first; fall back to pkg-config on macOS/Linux.
find_package(SDL2 CONFIG QUIET)
if(NOT TARGET SDL2::SDL2)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)
endif()

# Prefer config package first; fall back to pkg-config on macOS/Linux.
find_package(SDL2_image CONFIG QUIET)
if(NOT TARGET SDL2_image::SDL2_image)
    pkg_check_modules(SDL2_IMAGE REQUIRED IMPORTED_TARGET SDL2_image)
endif()

add_executable(command_control main.cpp)
set_target_properties(command_control PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED YES)

target_include_directories(command_control PRIVATE
    ${CMAKE_SOURCE_DIR}/idl/generated
    ${CMAKE_SOURCE_DIR}/idl
)

if(TARGET SDL2::SDL2)
    target_link_libraries(command_control PRIVATE SDL2::SDL2)
else()
    target_link_libraries(command_control PRIVATE PkgConfig::SDL2)
endif()

if(TARGET SDL2::SDL2main)
    target_link_libraries(command_control PRIVATE SDL2::SDL2main)
endif()

if(TARGET SDL2_image::SDL2_image)
    target_link_libraries(command_control PRIVATE SDL2_image::SDL2_image)
else()
    target_link_libraries(command_control PRIVATE PkgConfig::SDL2_IMAGE)
endif()

# Copy ship photo and SDL2_image runtime DLLs next to the executable
add_custom_command(TARGET command_control POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/ArleighBurke-class.png"
        "$<TARGET_FILE_DIR:command_control>/ArleighBurke-class.png"
)

if(WIN32)
    set(_VCPKG_BIN "C:/RTI/vcpkg/installed/x64-windows/bin")
    add_custom_command(TARGET command_control POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${_VCPKG_BIN}/SDL2_image.dll"
            "$<TARGET_FILE_DIR:command_control>/SDL2_image.dll"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${_VCPKG_BIN}/libpng16.dll"
            "$<TARGET_FILE_DIR:command_control>/libpng16.dll"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${_VCPKG_BIN}/z.dll"
            "$<TARGET_FILE_DIR:command_control>/z.dll"
    )
endif()

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

    target_compile_definitions(command_control PRIVATE USE_CONNEXT)
    if(WIN32)
        target_compile_definitions(command_control PRIVATE
            RTI_WIN32
            RTI_dds_c_DLL_VARIABLE
            RTI_dds_cpp_DLL_VARIABLE
            RTI_osapi_DLL_VARIABLE
            RTI_cdr_DLL_VARIABLE
            RTI_log_DLL_VARIABLE
        )
    elseif(APPLE)
        target_compile_definitions(command_control PRIVATE
            RTI_UNIX
            RTI_DARWIN
            RTI_64BIT
        )
    endif()
    target_include_directories(command_control PRIVATE
        ${RTI_CONNEXTDDS_INCLUDE}
        ${RTI_CONNEXTDDS_DIR}/include/ndds
    )
    if(TARGET ship_types)
        target_link_libraries(command_control PRIVATE ship_types ${RTI_CONNEXTDDS_LIBS})
    else()
        target_link_libraries(command_control PRIVATE ${RTI_CONNEXTDDS_LIBS})
    endif()
endif()

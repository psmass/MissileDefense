# Top-level apps CMake

# Propagate RTI_CONNEXTDDS_DIR fallback so app-level CMakeLists can use it
if(NOT DEFINED RTI_CONNEXTDDS_DIR)
  if(DEFINED ENV{NDDSHOME})
    set(RTI_CONNEXTDDS_DIR $ENV{NDDSHOME} CACHE PATH "RTI Connext install (from NDDSHOME)")
    message(STATUS "Using NDDSHOME for RTI Connext: ${RTI_CONNEXTDDS_DIR}")
  endif()
endif()

# Add app subdirectories if they contain CMakeLists.txt
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/command_control/CMakeLists.txt)
  add_subdirectory(command_control)
endif()
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/sensor/CMakeLists.txt)
  add_subdirectory(sensor)
endif()
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/effector/CMakeLists.txt)
  add_subdirectory(effector)
endif()

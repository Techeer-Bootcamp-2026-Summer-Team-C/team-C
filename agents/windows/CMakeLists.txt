cmake_minimum_required(VERSION 3.24)
project(EDRWindowsAgent VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(SQLite3 REQUIRED)

add_library(edr_agent_core STATIC
    src/core.cpp
    src/packet_parser.cpp
)
target_include_directories(edr_agent_core PUBLIC include)
target_link_libraries(edr_agent_core PUBLIC SQLite::SQLite3)

if(WIN32)
    if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
        message(FATAL_ERROR "The Windows Agent supports x64 builds only")
    endif()
    add_executable(edr-windows-agent
        src/main.cpp
        src/windows_collectors.cpp
        src/windows_transport.cpp
    )
    target_compile_definitions(edr-windows-agent PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)
    target_link_libraries(edr-windows-agent PRIVATE
        edr_agent_core bcrypt crypt32 ncrypt iphlpapi rpcrt4 tdh wevtapi winhttp advapi32 ws2_32
    )
    if(DEFINED NPCAP_SDK_DIR)
        target_compile_definitions(edr-windows-agent PRIVATE EDR_HAS_NPCAP=1)
        target_include_directories(edr-windows-agent PRIVATE "${NPCAP_SDK_DIR}/Include")
        target_link_directories(edr-windows-agent PRIVATE "${NPCAP_SDK_DIR}/Lib/x64")
        target_link_libraries(edr-windows-agent PRIVATE wpcap Packet)
    endif()
endif()

enable_testing()
add_executable(edr-agent-core-tests tests/core_tests.cpp)
target_link_libraries(edr-agent-core-tests PRIVATE edr_agent_core)
add_test(NAME edr-agent-core-tests COMMAND edr-agent-core-tests)

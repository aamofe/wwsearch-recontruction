cmake_minimum_required(VERSION 2.8.12)
project(wwsearch)

option(WITH_ROCKSDB "build with rocksdb" ON)
option(WITH_SNAPPY "build with snappy" ON)
option(WITH_TESTS "build with ut" OFF)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/cmake/modules/")

# ✅ 修复1：移除 -lpthread/-lrt/-lz（不属于编译flags），修复 C_FLAGS 引用错误
set(CMAKE_COMMON_FLAGS 
    "-DROCKSDB_PLATFORM_POSIX -DROCKSDB_LIB_IO_POSIX -DOS_LINUX \
     -fno-builtin-memcmp -DZLIB -DROCKSDB_MALLOC_USABLE_SIZE \
     -DROCKSDB_PTHREAD_ADAPTIVE_MUTEX -DROCKSDB_BACKTRACE \
     -DROCKSDB_RANGESYNC_PRESENT -DROCKSDB_SCHED_GETCPU_PRESENT \
     -march=native -DHAVE_SSE42 -DHAVE_PCLMUL \
     -DROCKSDB_SUPPORT_THREAD_LOCAL"
)

add_definitions(-D_GLIBCXX_USE_CXX11_ABI=0)

# ✅ 修复2：C_FLAGS 用 CMAKE_C_FLAGS 而非 CMAKE_CXX_FLAGS
set(CMAKE_C_FLAGS   "${CMAKE_C_FLAGS}   ${CMAKE_COMMON_FLAGS} -g -Wno-narrowing")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${CMAKE_COMMON_FLAGS} -std=c++11 -g -Wno-narrowing")

# ✅ 修复3：链接选项单独设置
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -ldl -lrt")

set(WWSEARCH_DIR ${CMAKE_CURRENT_SOURCE_DIR})

set(CMAKE_INCLUDE_PATH "${WWSEARCH_DIR}/deps/snappy/include")
set(CMAKE_LIBRARY_PATH "${WWSEARCH_DIR}/deps/snappy/lib")

add_subdirectory(${WWSEARCH_DIR}/deps/rocksdb)
add_subdirectory(${WWSEARCH_DIR}/deps/tokenizer)

include_directories(
    ${WWSEARCH_DIR}
    ${WWSEARCH_DIR}/include
    ${WWSEARCH_DIR}/deps/rocksdb/
    ${WWSEARCH_DIR}/deps/rocksdb/include
    ${WWSEARCH_DIR}/deps/rocksdb/third-party/gtest-1.7.0/fused-src
    ${WWSEARCH_DIR}/deps/tokenizer/include
    ${WWSEARCH_DIR}/unittest
    ${WWSEARCH_DIR}/deps/protobuf/include
    ${WWSEARCH_DIR}/deps/snappy/include
)

# ✅ 修复4：FIND_LIBRARY 路径正确，链接写法修正
FIND_LIBRARY(PROTOBUF_LIB NAMES libprotobuf.a 
    HINTS ${WWSEARCH_DIR}/deps/protobuf/lib NO_DEFAULT_PATH)
FIND_LIBRARY(SNAPPY_LIB NAMES libsnappy.a 
    HINTS ${WWSEARCH_DIR}/deps/snappy/lib NO_DEFAULT_PATH)

file(GLOB WWSEARCH_SRC_DIR ./src/*.cpp ./include/*.cc)
ADD_LIBRARY(wwsearch ${WWSEARCH_SRC_DIR})

# ✅ 修复5：target_link_libraries 去掉错误的 -Lprotobuf/-Lsnappy
target_link_libraries(wwsearch 
    rocksdb 
    tokenizer 
    ${PROTOBUF_LIB} 
    ${SNAPPY_LIB} 
    z pthread rt
)

# --- Example ---
add_executable(wwsearch_example example/example.cpp)
target_link_libraries(wwsearch_example wwsearch)
set_target_properties(wwsearch_example PROPERTIES LINK_FLAGS "-no-pie")

# --- Benchmark ---
include_directories(${WWSEARCH_DIR}/benchmark)
file(GLOB WWSEARCH_BEN_DIR ./benchmark/*.cpp)
add_executable(wwsearch_ben ${WWSEARCH_BEN_DIR})
target_link_libraries(wwsearch_ben wwsearch)
set_target_properties(wwsearch_ben PROPERTIES LINK_FLAGS "-no-pie")

# --- Unit Test ---
# ✅ 修复6：WITH_TESTS option 真正生效
if(WITH_TESTS)
    file(GLOB WWSEARCH_UT_DIR ./unittest/*.cpp)
    add_executable(wwsearch_ut ${WWSEARCH_UT_DIR})
    target_link_libraries(wwsearch_ut wwsearch gtest z pthread)
    set_target_properties(wwsearch_ut PROPERTIES LINK_FLAGS "-no-pie")
endif()


# --- Test Helper（为集成测试提供 Update/Delete/Replace/AddOrUpdate CLI）---
add_executable(wwsearch_test_helper example/wwsearch_test_helper.cpp)
target_link_libraries(wwsearch_test_helper wwsearch)
set_target_properties(wwsearch_test_helper PROPERTIES LINK_FLAGS "-no-pie")
 
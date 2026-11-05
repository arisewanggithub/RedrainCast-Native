cmake_minimum_required(VERSION 3.22)
project(redrain_ffmpeg_consumer_smoke C)
find_package(redrain_ffmpeg CONFIG REQUIRED)
add_library(test SHARED ../smoke.c)
target_link_libraries(test PRIVATE redrain_ffmpeg::swresample redrain_ffmpeg::avutil)
target_link_options(test PRIVATE
    -Wl,--no-undefined -Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384)

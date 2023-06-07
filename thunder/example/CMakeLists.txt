MESSAGE(STATUS ${STATIC_FLAG})

add_executable(placer placer.cc)
target_link_libraries(placer thunder)

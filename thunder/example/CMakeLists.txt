add_executable(example1 example1.cc)
target_link_libraries(example1 thunder)

add_executable(example2 example2.cc)
target_link_libraries(example2 thunder)

add_executable(placer placer.cc)
target_link_libraries(placer thunder)
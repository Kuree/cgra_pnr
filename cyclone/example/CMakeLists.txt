add_executable(example1 example1.cc)
target_link_libraries(example1 cyclone)

add_executable(example2 example2.cc)
target_link_libraries(example2 cyclone)

add_executable(router router.cc)
target_link_libraries(router cyclone)
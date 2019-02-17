#ifndef THUNDER_IO_HH
#define THUNDER_IO_HH

#include <string>
#include <map>
#include <vector>
#include "layout.hh"

std::pair<std::map<std::string, std::vector<std::pair<std::string,
                                                      std::string>>>,
          std::map<std::string, uint32_t>>
load_netlist(const std::string &filename);

Layout load_layout(const std::string &filename);

void dump_layout(const Layout &layout, const std::string &filename);

void save_placement(const std::map<std::string, std::pair<int, int>> &placement,
                    const std::map<std::string, std::string> &id_to_name,
                    const std::string &filename);

std::map<std::string, std::string>
load_id_to_name(const std::string &filename);

#endif //THUNDER_IO_HH

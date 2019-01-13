#include "layout.hh"

using std::vector;
using std::runtime_error;

Layer::Layer(char blk_type, uint32_t width,
             uint32_t height) : blk_type(blk_type),
                                layout_(height, ::vector<bool>(width, false)) {}


bool Layer::operator[](const std::pair<uint32_t, uint32_t> &pos) const {
    auto [x, y] = pos;
    return layout_[y][x];
}

void Layout::add_layer(const Layer &layer) {
    const char blk_type = layer.blk_type;
    if (layers_.find(blk_type) != layers_.end())
        throw ::runtime_error(std::string(1, blk_type) + " already exists");
    layers_.insert({blk_type, layer});
}

bool Layout::is_legal(const std::string &blk_id, uint32_t x, uint32_t y) {
    const char blk_type = blk_id[0];
    auto const &layer = layers_.at(blk_type);
    return layer[{x, y}];
}
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

std::pair<uint64_t, uint64_t> Layer::get_size() const {
    return {layout_[0].size(), layout_.size()};
}

Layout::Layout(const std::map<char, std::vector<std::vector<bool>>> &layers) {
    for (auto &[blk_type, layer]: layers) {
        auto height = static_cast<uint32_t>(layer.size());
        auto width = static_cast<uint32_t>(layer[0].size());
        // add a layer one by one
        Layer l(blk_type, width, height);
        for (uint32_t y = 0; y < height; y++) {
            for (uint32_t x = 0; x < width; x++) {
                if (layer[y][x])
                    l.mark_available(x, y);
            }
        }
        add_layer(l);
    }
}

Layout::Layout(const std::vector<std::vector<char>> &layers) {
    auto height = static_cast<uint32_t>(layers.size());
    auto width = static_cast<uint32_t>(layers[0].size());
    // first pass to create the empty layers
    for (uint32_t y = 0; y < height; y++) {
        for (uint32_t x = 0; x < width; x++) {
            auto const blk_type = layers[y][x];
            if (layers_.find(blk_type) == layers_.end())
                add_layer(Layer(blk_type, width, height));
        }
    }
    // second pass to fill that layer in
    for (uint32_t y = 0; y < height; y++) {
        for (uint32_t x = 0; x < width; x++) {
            auto const blk_type = layers[y][x];
            auto &layer = layers_.at(blk_type);
            layer.mark_available(x, y);
        }
    }
}

void Layout::add_layer(const Layer &layer) {
    const char blk_type = layer.blk_type;
    if (layers_.find(blk_type) != layers_.end())
        throw ::runtime_error(std::string(1, blk_type) + " already exists");
    layers_.insert({blk_type, layer});

    // set width and height
    auto [width, height] = layer.get_size();
    if (width_ == 0) {
        width_ = width;
        height_ = height;
    } else {
        if (width_ != width || height_ != height)
            throw ::runtime_error("layer size doesn't match");
    }
}

bool Layout::is_legal(const std::string &blk_id, uint32_t x, uint32_t y) {
    const char blk_type = blk_id[0];
    auto const &layer = layers_.at(blk_type);
    return layer[{x, y}];
}

char Layout::get_blk_type(uint32_t x, uint32_t y) const {
    for (const auto &iter: layers_) {
        auto const &[blk_type, layer] = iter;
        if (layer[{x, y}])
            return blk_type;
    }
    return ' ';
}
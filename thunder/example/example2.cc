#include "../src/io.hh"

int main(int argc, char *argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " <cgra.layout>" << std::endl;
        return EXIT_FAILURE;
    }
    auto layout = load_layout(argv[1]);
    std::cout << std::endl << layout.layout_repr() << std::endl;

    return EXIT_SUCCESS;
}
CC = gcc
CPP = g++

FLAGS = -lm -pthread -O3 -march=native -Wall -funroll-loops -Wno-unused-result -Wno-maybe-uninitialized

all: metapath2vec

metapath2vec : metapath2vec.cpp
	$(CPP) metapath2vec.cpp -o metapath2vec $(FLAGS)

clean:
	rm -rf metapath2vec

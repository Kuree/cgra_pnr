CC = gcc

FLAGS = -lm -pthread -O3 -march=native -Wall -funroll-loops -Wno-unused-result

all: word2vec

word2vec : word2vec.c
	$(CC) word2vec.c -o word2vec $(FLAGS)

clean:
	rm -rf word2vec

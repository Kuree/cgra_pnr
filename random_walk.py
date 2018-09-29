from __future__ import print_function
import numpy as np
import tempfile
import random
import subprocess
import os
from tqdm import tqdm
from argparse import ArgumentParser
from arch.cgra_packer import load_packed_file
from arch.cgra import build_graph
from arch.fpga import load_packed_fpga_netlist


FILE_PATH = os.path.dirname(__file__)
NETLIST2VEC = os.path.join(FILE_PATH, "./word2vec")


# copied from node2vec
class Graph():
    def __init__(self, nx_G, is_directed, p, q):
        self.G = nx_G
        self.is_directed = is_directed
        self.p = p
        self.q = q

    def node2vec_walk(self, walk_length, start_node):
        '''
        Simulate a random walk starting from start node.
        '''
        G = self.G
        alias_nodes = self.alias_nodes
        alias_edges = self.alias_edges

        walk = [start_node]

        while len(walk) < walk_length:
                cur = walk[-1]
                cur_nbrs = sorted(G.neighbors(cur))
                if len(cur_nbrs) > 0:
                        if len(walk) == 1:
                                walk.append(cur_nbrs[alias_draw(alias_nodes[cur][0], alias_nodes[cur][1])])
                        else:
                                prev = walk[-2]
                                next = cur_nbrs[alias_draw(alias_edges[(prev, cur)][0],
                                        alias_edges[(prev, cur)][1])]
                                walk.append(next)
                else:
                        break

        return walk

    def simulate_walks(self, num_walks, walk_length):
        '''
        Repeatedly simulate random walks from each node.
        '''
        G = self.G
        walks = []
        nodes = list(G.nodes())
        print('Walk iteration:')
        for walk_iter in tqdm(range(num_walks)):
                random.shuffle(nodes)
                for node in nodes:
                    if node[0] != "x":
                            walks.append(self.node2vec_walk(walk_length=walk_length, start_node=node))

        return walks

    def get_alias_edge(self, src, dst):
        '''
        Get the alias edge setup lists for a given edge.
        '''
        G = self.G
        p = self.p
        q = self.q

        unnormalized_probs = []
        for dst_nbr in sorted(G.neighbors(dst)):
                if dst_nbr == src:
                        unnormalized_probs.append(G[dst][dst_nbr]['weight']/p)
                elif G.has_edge(dst_nbr, src):
                        unnormalized_probs.append(G[dst][dst_nbr]['weight'])
                else:
                        unnormalized_probs.append(G[dst][dst_nbr]['weight']/q)
        norm_const = sum(unnormalized_probs)
        normalized_probs =  [float(u_prob)/norm_const for u_prob in unnormalized_probs]

        return alias_setup(normalized_probs)

    def preprocess_transition_probs(self):
        '''
        Preprocessing of transition probabilities for guiding the random walks.
        '''
        G = self.G
        is_directed = self.is_directed

        alias_nodes = {}
        for node in G.nodes():
                unnormalized_probs = [G[node][nbr]['weight'] for nbr in sorted(G.neighbors(node))]
                norm_const = sum(unnormalized_probs)
                normalized_probs =  [float(u_prob)/norm_const for u_prob in unnormalized_probs]
                alias_nodes[node] = alias_setup(normalized_probs)

        alias_edges = {}
        triads = {}

        if is_directed:
                for edge in G.edges():
                        alias_edges[edge] = self.get_alias_edge(edge[0], edge[1])
        else:
                for edge in G.edges():
                        alias_edges[edge] = self.get_alias_edge(edge[0], edge[1])
                        alias_edges[(edge[1], edge[0])] = self.get_alias_edge(edge[1], edge[0])

        self.alias_nodes = alias_nodes
        self.alias_edges = alias_edges

        return


def alias_setup(probs):
    '''
    Compute utility lists for non-uniform sampling from discrete distributions.
    Refer to https://hips.seas.harvard.edu/blog/2013/03/03/the-alias-method-efficient-sampling-with-many-discrete-outcomes/
    for details
    '''
    K = len(probs)
    q = np.zeros(K)
    J = np.zeros(K, dtype=np.int)

    smaller = []
    larger = []
    for kk, prob in enumerate(probs):
        q[kk] = K*prob
        if q[kk] < 1.0:
            smaller.append(kk)
        else:
            larger.append(kk)

    while len(smaller) > 0 and len(larger) > 0:
        small = smaller.pop()
        large = larger.pop()

        J[small] = large
        q[large] = q[large] + q[small] - 1.0
        if q[large] < 1.0:
            smaller.append(large)
        else:
            larger.append(large)

    return J, q


def alias_draw(J, q):
    '''
    Draw sample from a non-uniform discrete distribution using alias sampling.
    '''
    K = len(J)

    kk = int(np.floor(np.random.rand()*K))
    if np.random.rand() < q[kk]:
        return kk
    else:
        return J[kk]


def build_walks(packed_filename, emb_name, is_fpga_packed):
    if is_fpga_packed:
        netlists, _ = load_packed_fpga_netlist(packed_filename)
        walk_length = 80
        num_walks = 10
    else:
        netlists, _, _, _ = load_packed_file(packed_filename)
        walk_length = 40
        num_walks = 15

    nx_g = build_graph(netlists, is_fpga_packed)
    p = 0.6
    q = 1
    num_dim = 12
    G = Graph(nx_g, False, p, q)
    G.preprocess_transition_probs()
    # generate random walks
    # because we use star expansion
    walks = G.simulate_walks(num_walks, walk_length * 2)
    basename = os.path.basename(packed_filename)
    design_name, _ = os.path.splitext(basename)

    with tempfile.NamedTemporaryFile(dir='/tmp', delete=False, mode="w+") as f:
        output_name = f.name
        for walk in walks:
            for node_id in walk:
                f.write("{} ".format(node_id))
            f.write("\n")
    print("Using", NETLIST2VEC)
    cmd = [NETLIST2VEC, "-train", output_name, "-output", emb_name, "-size",
           str(num_dim), "-threads", str(1)]
    subprocess.call(cmd)
    os.remove(output_name)


if __name__ == "__main__":
    parser = ArgumentParser("Netlist embedding tool (node2vec based)")
    parser.add_argument("-i", "--input", help="Packed netlist file, " +
                        "e.g. harris.packed",
                        required=True, action="store", dest="input")
    parser.add_argument("-o", "--output", help="Output embedding file, " +
                        "e.g. harris.emb",
                        required=True, action="store", dest="output")
    parser.add_argument("-s", "--seed", help="Seed for random walk. " +
                        "default is 0", type=int, default=0,
                        required=False, action="store", dest="seed")
    parser.add_argument("--fpga", action="store_true", dest="is_fpga",
                        default=False, help="Use this flag when working with"
                                            "ISPD packed netlist")
    args = parser.parse_args()
    seed = args.seed
    print("Using seed", seed, "for random walk")
    random.seed(seed)
    np.random.seed(seed)
    input_file = args.input
    output_file = args.output
    is_fpga = args.is_fpga
    build_walks(input_file, output_file, is_fpga)
    print()

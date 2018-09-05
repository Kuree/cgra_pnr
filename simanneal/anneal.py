"""
Original code from https://github.com/perrygeo/simanneal
Minor changes made by me (Keyi Zhang) to allow multi-processing and
deterministic annealing.
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import abc
import six
import math
import random
import time
from tqdm import tqdm


def round_figures(x, n):
    """Returns x rounded to n significant figures."""
    return round(x, int(n - math.ceil(math.log10(abs(x)))))


def time_string(seconds):
    """Returns time in seconds as a string formatted HHHH:MM:SS."""
    s = int(round(seconds))  # round to nearest second
    h, s = divmod(s, 3600)   # get hours and remainder
    m, s = divmod(s, 60)     # split remainder into minutes and seconds
    return '%4i:%02i:%02i' % (h, m, s)


class Annealer(object):

    """Performs simulated annealing by calling functions to calculate
    energy and make moves on a state.  The temperature schedule for
    annealing may be provided manually or estimated automatically.
    """

    __metaclass__ = abc.ABCMeta

    # defaults
    Tmax = 25000.0
    Tmin = 2.5
    steps = 50000
    updates = 100
    copy_strategy = 'deepcopy'
    user_exit = False

    # early termination
    num_nets = 0

    # fast HPWL calculation
    pre_state = None
    pre_energy = None

    # placeholders
    best_state = None
    best_energy = None
    start = None

    def __init__(self, initial_state=None, rand=None):
        if initial_state is not None:
            self.state = self.copy_state(initial_state)
        else:
            raise ValueError('No valid values supplied for neither \
            initial_state nor load_state')
        if rand is None:
            self.random = random.Random()
            self.random.seed(0)
        else:
            self.random = rand

        self.anneal_rand = random.Random()
        self.anneal_rand.seed(0)

    @staticmethod
    def __deepcopy(obj_to_copy):
        if isinstance(obj_to_copy, dict):
            d = obj_to_copy.copy()  # shallow dict copy
            for k, v in six.iteritems(d):
                d[k] = Annealer.__deepcopy(v)
        elif isinstance(obj_to_copy, list):
            d = obj_to_copy[:]  # shallow list/tuple copy
            i = len(d)
            while i:
                i -= 1
                d[i] = Annealer.__deepcopy(d[i])
        elif isinstance(obj_to_copy, set):
            d = obj_to_copy.copy()
        else:
            # tuple is fine since we're not modifying tuples
            d = obj_to_copy
        return d


    @abc.abstractmethod
    def move(self):
        """Create a state change"""
        pass

    @abc.abstractmethod
    def energy(self):
        """Calculate state's energy"""
        pass

    def set_schedule(self, schedule):
        """Takes the output from `auto` and sets the attributes
        """
        self.Tmax = schedule['tmax']
        self.Tmin = schedule['tmin']
        self.steps = int(schedule['steps'])
        self.updates = int(schedule['updates'])

    def copy_state(self, state):
        """Returns an exact copy of the provided state
        Implemented according to self.copy_strategy, one of

        * deepcopy : use copy.deepcopy (slow but reliable)
        * slice: use list slices (faster but only works if state is list-like)
        * method: use the state's copy() method
        """
        if self.copy_strategy == 'deepcopy':
            return Annealer.__deepcopy(state)
        elif self.copy_strategy == 'slice':
            return state[:]
        elif self.copy_strategy == 'method':
            return state.copy()
        else:
            raise RuntimeError('No implementation found for ' +
                               'the self.copy_strategy "%s"' %
                               self.copy_strategy)

    def anneal(self):
        """Minimizes the energy of a system by simulated annealing.

        Parameters
        state : an initial arrangement of the system

        Returns
        (state, energy): the best state and energy found.
        """
        step = 0
        self.start = time.time()

        # Precompute factor for exponential cooling from Tmax to Tmin
        if self.Tmin <= 0.0:
            raise Exception('Exponential cooling requires a minimum "\
                "temperature greater than zero.')
        Tfactor = -math.log(self.Tmax / self.Tmin)

        # Note initial state
        T = self.Tmax
        E = self.energy()
        self.pre_state = self.copy_state(self.state)
        self.pre_energy = E
        self.best_state = self.copy_state(self.state)
        self.best_energy = E
        trials, accepts, improves = 0, 0, 0

        # Attempt moves to new states
        for step in tqdm(range(self.steps)):
            step += 1
            T = self.Tmax * math.exp(Tfactor * step / self.steps)
            self.move()
            E = self.energy()
            dE = E - self.pre_energy
            trials += 1
            if dE > 0.0 and math.exp(-dE / T) < self.anneal_rand.random():
                # Restore previous state
                self.state = self.copy_state(self.pre_state)
            else:
                # Accept new state and compare to best state
                accepts += 1
                if dE < 0.0:
                    improves += 1
                self.pre_state = self.copy_state(self.state)
                self.pre_energy = E
                if E < self.best_energy:
                    self.best_state = self.copy_state(self.state)
                    self.best_energy = E

            # allow early termination
            if self.num_nets > 0 and T < 0.005 * E / self.num_nets:
                break

        self.state = self.copy_state(self.best_state)

        # Return best state and energy
        return self.best_state, self.best_energy

    def auto(self, minutes, steps=2000):
        """Explores the annealing landscape and
        estimates optimal temperature settings.

        Returns a dictionary suitable for the `set_schedule` method.
        """

        def run(T, steps):
            """Anneals a system at constant temperature and returns the state,
            energy, rate of acceptance, and rate of improvement."""
            E = self.energy()
            prevState = self.copy_state(self.state)
            prevEnergy = E
            accepts, improves = 0, 0
            for _ in range(steps):
                self.move()
                E = self.energy()
                dE = E - prevEnergy
                if dE > 0.0 and math.exp(-dE / T) < self.anneal_rand.random():
                    self.state = self.copy_state(prevState)
                    E = prevEnergy
                else:
                    accepts += 1
                    if dE < 0.0:
                        improves += 1
                    prevState = self.copy_state(self.state)
                    prevEnergy = E
            return E, float(accepts) / steps, float(improves) / steps

        step = 0
        self.start = time.time()

        # Attempting automatic simulated anneal...
        # Find an initial guess for temperature
        T = 0.0
        E = self.energy()
        while T == 0.0:
            step += 1
            self.move()
            T = abs(self.energy() - E)

        # Search for Tmax - a temperature that gives 98% acceptance
        E, acceptance, improvement = run(T, steps)

        step += steps
        while acceptance > 0.98:
            T = round_figures(T / 1.5, 2)
            E, acceptance, improvement = run(T, steps)
            step += steps
        while acceptance < 0.98:
            T = round_figures(T * 1.5, 2)
            E, acceptance, improvement = run(T, steps)
            step += steps
        Tmax = T

        # Search for Tmin - a temperature that gives 0% improvement
        while improvement > 0.0:
            T = round_figures(T / 1.5, 2)
            E, acceptance, improvement = run(T, steps)
            step += steps
        Tmin = T

        # Calculate anneal duration
        elapsed = time.time() - self.start
        duration = round_figures(int(60.0 * minutes * step / elapsed), 2)

        # Don't perform anneal, just return params
        return {'tmax': Tmax, 'tmin': Tmin, 'steps': duration, 'updates':
                 self.updates}

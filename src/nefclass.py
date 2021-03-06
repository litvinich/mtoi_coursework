import numpy as np

from .membership import *


EPSILON = 0.0000001


class NefClassModel:
    def __init__(
        self, num_input_units, num_fuzzy_sets, kmax, output_units, universe_max, universe_min, membership_type
    ):
        self.input = _input_layer(num_input_units, num_fuzzy_sets, universe_max, universe_min, membership_type)
        self.rule = _rule_layer(kmax, output_units)
        self.output = _output_layer(output_units)
        self.universe_max = universe_max
        self.universe_min = universe_min
        self.membership_type = membership_type

    def init_fuzzy_sets(self, abcs):
        self.input.init_abcs(abcs)

    def __call__(self, x, t):
        m, ante = self.input(x)
        o = self.rule(m)
        c = self.output(o)
        return c

    def learn_rule(self, x, t):

        m, ante = self.input(x)
        o = self.rule.learn(ante, t)
        # c = self.output(o)

    def update_fuzzy_sets(self, sigma, delta):
        # print(self.input.abcs)
        for n in self.rule.nodes:
            interm = n.update_fuzzy_set_node(delta)
            if interm is not None:
                self.input.update_fuzzy_sets(sigma, interm)
        # print(self.input.abcs)

    def get_num_rules(self):
        return len(self.rule.nodes)

    def get_antecedents(self, x):
        m = []
        for i in range(len(x)):
            m.append(
                [
                    determine_membership(x[i], v, self.universe_max[i], self.universe_min[i], self.membership_type)
                    for k, v in self.input.abcs[i].items()
                ]
            )

        ante = [mem.index(max(mem)) for mem in m]
        return m, ante

    def get_degree_of_fulfilment(self, m, a):
        activations = [m[i][a[i]] + EPSILON for i in range(len(a))]
        min_activation = min(activations)
        return min_activation

    def add_rules(self, antecedents, consequents):
        for a, c in zip(antecedents, consequents):
            self.rule._create_node(a, c)

    def predict(self, data: np.ndarray, targets: np.ndarray) -> np.ndarray:
        predicts = []
        for features, target in zip(data, targets):
            output = self.__call__(features, target)
            predicts.append(np.argmax(output))
        return np.array(predicts)


class _input_layer:
    def __init__(self, num_input_units, num_fuzzy_sets, universe_max, universe_min, membership_type):
        self.num_fuzzy_sets = num_fuzzy_sets
        self.num_input_units = num_input_units
        self.abcs = None
        self.last_m = None
        self.last_ante = None
        self.last_input = None
        self.universe_max = universe_max
        self.universe_min = universe_min
        self.membership_type = membership_type

    def init_abcs(self, abcs):
        self.abcs = abcs

    def __call__(self, x):
        self.last_input = x
        m = []
        for i in range(len(x)):
            m.append(
                [
                    determine_membership(x[i], v, self.universe_max[i], self.universe_min[i], self.membership_type)
                    for k, v in self.abcs[i].items()
                ]
            )
        ante = [mem.index(max(mem)) for mem in m]
        self.last_m = m
        self.last_ante = ante

        return m, ante

    def update_fuzzy_sets(self, sigma, interm):
        error_rule, (j1, j2), mu = interm
        key = list(self.abcs[j1].keys())[j2]
        abc = self.abcs[j1][key]
        # print(abc)
        delta_b = sigma * error_rule * (abc[2] - abc[0]) * np.sign(self.last_input[j1] - abc[1])
        delta_a = -sigma * error_rule * (abc[2] - abc[0]) + delta_b
        delta_c = sigma * error_rule * (abc[2] - abc[0]) + delta_b
        # print(delta_a, delta_b, delta_c)
        # update
        new_abc = [abc[0] + delta_a, abc[1] + delta_b, abc[2] + delta_c]

        # print(abc)
        if self.check_constraints(j1, key, new_abc):
            self.abcs[j1][key] = new_abc
        # else:
        # print('constraints failed')

    def check_constraints(self, input_node, key, new_abc):
        check1 = self.keep_relative_order(input_node, key, new_abc)
        check2 = self.always_overlap(input_node, key, new_abc)
        check3 = self.symmetrical(input_node, key, new_abc)

        return check1 and check2 and check3

    def keep_relative_order(self, input_node, key, new_abc):
        old_sets = self.abcs[input_node]
        old_sets[key] = new_abc

        bs = [b for a, b, c in list(old_sets.values())]
        bs_copy = bs[:]
        bs_copy.sort()
        check = bs == bs_copy
        return check

    def always_overlap(self, input_node, key, new_abc):
        old_sets = self.abcs[input_node]
        old_sets[key] = new_abc

        a_s = [a for a, b, c in list(old_sets.values())]
        bs = [b for a, b, c in list(old_sets.values())]
        cs = [c for a, b, c in list(old_sets.values())]

        for n, c in enumerate(cs):
            if c <= self.universe_min[n]:
                return False
            if n + 1 != self.num_fuzzy_sets:
                if c < a_s[n + 1]:
                    return False

        for n, a in enumerate(a_s):
            if a >= self.universe_max[n]:
                return False

        return True

    def symmetrical(self, input_node, key, new_abc):
        old_sets = self.abcs[input_node]
        old_sets[key] = new_abc

        for v in old_sets.values():
            a, b, c = v
            if not np.allclose(c - b, b - a):
                return False

        return True


class _rule_layer:
    def __init__(self, kmax, output_units):
        self.kmax = kmax
        self.output_units = output_units
        self.nodes = []
        self.antes = []

    def __call__(self, m):
        tally = [[] for i in range(self.output_units)]
        for n in self.nodes:
            tally = n(m, tally)
        return tally

    def learn(self, antecedent, consequent):
        if len(self.nodes) < self.kmax:
            if str(antecedent) not in self.antes:
                self._create_node(antecedent, consequent)
                self.antes.append(str(antecedent))
        # print(len(self.nodes), len(self.antes))

    def _create_node(self, antecedent, consequent):
        self.nodes.append(RuleNode(antecedent, consequent, self.output_units))


class RuleNode:
    def __init__(self, antecedent, consequent, output_units):
        self.antecedent = antecedent
        self.consequent = consequent
        self.output_units = output_units
        self.last_activation = None
        self.last_min_activation = None
        # each rule is connected to exactly 1 output (consequent)

    def __call__(self, m, tally):
        # min as tnorm
        activations = [m[i][self.antecedent[i]] + EPSILON for i in range(len(self.antecedent))]
        self.last_activation = activations
        min_activation = min(activations)
        self.last_min_activation = min_activation
        tally[self.consequent].append(min_activation)
        return tally

    def update_fuzzy_set_node(self, delta):
        if self.last_min_activation > EPSILON:
            error_rule = self.last_min_activation * (1 - self.last_min_activation) * (delta[self.consequent])
            j = np.argmin(self.last_activation)
            mu = self.last_activation[j]
            return error_rule, (j, self.antecedent[j]), mu
        else:
            return None


class _output_layer:
    def __init__(self, output_units):
        self.output_units = output_units

    def __call__(self, o):
        # o is tally
        # max as t-conorm
        output = [max(node) if len(node) != 0 else 0 for node in o]
        # print(output)
        total = sum(output)
        # print(total)
        output = [o / total for o in output]
        return output


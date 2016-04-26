#!/usr/bin/python3

import pdb
from module import *

def print_it(tp, tl, time, s):
    print("%s.%d: %s: %s" % (tp, tl, time, s))

loggers = []
loggers.append(trace.Logger("default", 1, print_it))
loggers.append(trace.Logger("debug", 1, print_it))
loggers.append(trace.Logger("trace", 9, print_it))
loggers.append(trace.Logger("ingress", 1, print_it))

x = otherstuff.Foo()
x.bar()

loggers.append(trace.Logger("egress", 1, print_it))

@trace.TracedFunction
def a():
    x.bar()

@trace.TracedFunction
def b():
    a()

@trace.TracedFunction
def c():
    b()

c()

#!/usr/bin/python3

import pdb
import sys
from module import *

def print_it(tp, tl, time, s):
    print("%s.%d: %s: %s" % (tp, tl, time, s))

def print_if_9(tp, tl, time, s):
    if tl >= 9:
        print("%s.%d: %s: %s" % (tp, tl, time, s))

tl = trace.Logger("debug", 9, print_if_9)

loggers = [
        {'trace_point':'debug', 'trace_level':9, 'logger':tl},
        {'trace_point':'default', 'trace_level':1, 'logger':None},
        {'trace_point':'debug', 'trace_level':1, 'logger':None},
        {'trace_point':'ingress', 'trace_level':1, 'logger':None},
        {'trace_point':'egress', 'trace_level':1, 'logger':None},
        ]

del tl

def makeloggers():
    for logger in loggers:
        if not logger['logger']:
            print("creating a logger for %(trace_point)s.%(trace_level)d" % logger)
            logger['logger'] = trace.Logger(logger['trace_point'],
                                            logger['trace_level'], print_it)
makeloggers()

print("instantiating otherstuff.Foo() as x")
x = otherstuff.Foo()
print("calling x.bar()")
x.bar()

sys.exit(0)

loggers += [
        {'trace_point':'ingress', 'trace_level':3, 'logger':None},
        {'trace_point':'egress', 'trace_level':3, 'logger':None},
        ]
makeloggers()

print("defining a, b, c")

@trace.TracedFunction
def a():
    x.bar()

@trace.TracedFunction
def b():
    a()

@trace.TracedFunction
def c():
    b()

print("calling c")
c()

loggers += [
        {'trace_point':'ingress', 'trace_level':5, 'logger':None},
        {'trace_point':'egress', 'trace_level':5, 'logger':None},
        ]
makeloggers()

print("calling c")
c()

loggers += [
        {'trace_point':'ingress', 'trace_level':7, 'logger':None},
        {'trace_point':'egress', 'trace_level':7, 'logger':None},
        ]
makeloggers()

print("calling c")
c()


loggers += [
        {'trace_point':'ingress', 'trace_level':9, 'logger':None},
        {'trace_point':'egress', 'trace_level':9, 'logger':None},
        ]
makeloggers()

print("calling c")
c()

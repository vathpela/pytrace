#!/usr/bin/python3

from .trace import *

@trace_point("debug")
@trace_level(1)
class Foo(TracedObject):
    @trace_point("default")
    def bar(self):
        print("bar")

    def baz(self):
        print("baz")

def baz():
    print("baz")

__all__ = ['Foo', 'baz']

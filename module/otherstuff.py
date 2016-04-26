#!/usr/bin/python3

from .trace import *

@tracepoint("debug")
@tracelevel(1)
class Foo(TracedObject):
    @tracepoint("default")
    def bar(self):
        print("bar")

    def baz(self):
        print("baz")

def baz():
    print("baz")

__all__ = ['Foo', 'baz']

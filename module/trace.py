#!/usr/bin/python3
#
# Copyright 2016 Red Hat, Inc.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#  Peter Jones <pjones@redhat.com>
#
import copy
import time
import types
import traceback
from contextlib import *
import contextlib
import inspect
import pdb
import sys
import threading
import collections
import pprint
from decimal import Decimal

# XXX FIXME: figure out a good default level
DEFAULT_TRACE_LEVEL = 100

class LogFunction(object):
    """ This class provides a callable to log some data """

    def __init__(self, trace_point):
        self.trace_point = trace_point

    # XXX this should use our real log formatter instead
    def __call__(self, trace_level, msg, *args):
        # somebody might want to turn some specific kind of thing on, but
        # silence some particular message.  They can do that with "squelch".
        #print("fake %s.%d: %s" % (self.trace_point,trace_level, msg))
        #print("traces: %s" % (Logger.traces,))
        if self.trace_point != "squelch":
            key = [self.trace_point, trace_level]
            if self.trace_point is None:
                key[0] = 'default'
            key = tuple(key)
            #print("key: %s" % (key,))
            if key in Logger.traces:
                trace = Logger.traces[key]
                trace(self.trace_point, trace_level, msg, *args)

    # This makes it so in TracedObject we can just add a "log" callable
    # that does whatever the function's default trace_point is, but
    # any caller can do "self.log.debug(level, msg)" and get "debug" as the
    # tracepoint, or anything else they put in that position, unless they try to
    # name their tracepoint __init__, __dict__, __getattr__, __call__, etc.,
    # which will fail.
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self.__dict__:
            return self.__dict__[name]
        else:
            lf = LogFunction(trace_point=name)
            self.__dict__[name] = lf
            return lf

def get_frame_info(frame):
    """ fish our code object and its name out of a stack frame """
    if '__name__' in frame.f_locals and \
       frame.f_locals['__name__'] == '__main__':
           pass
    funcname = frame.f_code.co_name
    if 'self' in frame.f_locals:
        obj = frame.f_locals['self']
    elif funcname in frame.f_locals:
        obj = frame.f_locals[funcname]
    elif funcname in frame.f_globals:
        obj = frame.f_globals[funcname]
    else:
        print("funcname: %s" % (funcname,))
        print("frame.f_globals:")
        for k,v in frame.f_globals.items():
            print("  '%s':%r" % (k,v))
        print("frame.f_locals:")
        for k,v in frame.f_locals.items():
            print("  '%s':%r" % (k,v))
        return {'funcname':funcname, 'obj':None}
    return {'obj':obj, 'funcname':funcname}

def get_trace_info(stack=None):
    ret = {'modname':None,
           'clsname':None,
           'funcname':None,
           'qualname':None,
           'obj':None,
           }
    # iterate our frames until we find the first function that's not part of the
    # trace infrastructure.  From there, keep descending until we've either a)
    # run out of frames, or b) gotten a _trace_point and _trace_level
    if stack is None:
        stack = [f[0] for f in inspect.stack()[1:]]
    for frame in stack:
        info = get_frame_info(frame)
        obj = info['obj']
        funcname = info['funcname']

        mod = obj.__module__
        modname = obj.__module__
        cls = obj.__class__
        clsname = obj.__class__.__name__

        if clsname == 'trace' or funcname == 'event_tracer':
            continue

        if not ret['clsname']:
            ret['funcname'] = funcname
            ret['modname'] = modname
            ret['clsname'] = clsname

        if funcname and hasattr(obj, funcname):
            func = getattr(obj, funcname)
        else:
            func = None
        for name in ['trace_point', 'trace_level']:
            if name in ret:
                continue
            undername = '_%s' % (name,)
            val = None
            if func and hasattr(func, undername):
                val = getattr(func, undername)
            elif obj and hasattr(obj, undername):
                val = getattr(obj, undername)
            elif cls and hasattr(cls, undername):
                val = getattr(cls, undername)
            elif mod and hasattr(mod, undername):
                val = getattr(mod, undername)
            if not val is None:
                ret[name] = val
        if 'trace_point' in ret and 'trace_level' in ret:
               break

    # if we didn't find either of these, set the default
    if not 'trace_point' in ret:
        ret['trace_point'] = 'default'
    if not 'trace_level' in ret:
        ret['trace_level'] = DEFAULT_TRACE_LEVEL

    # and build a qualified name string as a convenience
    if "modname" in ret and ret["modname"] and \
       "clsname" in ret and ret["clsname"] and \
       "funcname" in ret and ret["funcname"]:
           ret["qualname"] = "%(modname)s.%(clsname)s.%(funcname)s" % ret
    elif "modname" in ret and ret["modname"] and \
         "funcname" in ret and ret["funcname"]:
           ret["qualname"] = "%(modname)s.%(funcname)s" % ret
    else:
        ret["qualname"] = ret["funcname"]
    return ret

def get_trace_info_from_frame(frame):
    stack = [frame]
    while frame:
        frame = frame.f_back
        stack.append(frame)
    return get_trace_info(stack)


def nada(*args, **kwargs): pass

def traceback_logger(func, obj, *args, **kwargs):
    """ A simple logger to log a traceback on entry of an object. """

    info = get_trace_info()
    log = LogFunction("traceback")
    stack = inspect.stack()[1:]
    stack = filter(lambda x: x[3] != 'event_tracer' and \
                             x[3] != 'inner', stack)
    for line in stack:
        fmt = traceback.format_stack(line[0], limit=1)[0]
        for s in fmt.split('\n'):
            if s.strip():
                log(level, "%s:%s", info[qualname], s)

eventmap = {
    }

def trace_dispatcher(frame, event, arg):
    l = LogFunction("ingress")
    l(9, time.time(), "trace_dispatcher(frame=%r, event=%r, arg=%r)" %
            (frame, event, arg))
    if frame.f_code.co_name == '__exit__':
        return
    info = get_trace_info_from_frame(frame)
    obj = info['obj']
    fas = inspect.getargvalues(frame)
    args = inspect.formatargvalues(*fas)
    if hasattr(obj, 'log'):
        log = obj.log
    else:
        log = LogFunction("default")
    if event == "call":
        fmt = "".join(traceback.format_stack(frame))
        for s in fmt.split('\n'):
            if s.strip():
                log.trace(1, "%s:%s" % (frame.f_code.co_name, s))
        log.ingress(1, "%s%s" % (frame.f_code.co_name, args))
        return trace_dispatcher
    elif event == "return" and frame.f_code.co_name != '__exit__':
        log.egress(1, "%s(%s) = %r" % (frame.f_code.co_name, args, arg))
        sys.settrace(None)
    l(9, time.time(), "trace_dispatcher(frame=%r, event=%r, arg=%r) = None" %
            (frame, event, arg))

class tracecontext(ContextDecorator):
    deque=collections.deque()
    def __enter__(self):
        self.sys_tracer = sys.gettrace()
        threading.settrace(trace_dispatcher)
        sys.settrace(trace_dispatcher)
        return self

    def __exit__(self, *exc):
        sys.settrace(self.sys_tracer)
        threading.settrace(self.sys_tracer)
        return False

def event_tracer(func, obj, *args, **kwargs):
    trace_events = {}
    if hasattr(obj, '_trace_events'):
        trace_events.update(obj._trace_events)
    if hasattr(func, '_trace_events'):
        trace_events.update(func._trace_events)
    early = {}
    late = {}

    def before(k):
        v = eventmap[k]
        if 'before' in v:
            return v['before']
        if 'after' in v:
            return not v['after']
        return False

    def after(k):
        v = eventmap[k]
        if 'after' in v:
            return v['after']
        if 'before' in v:
            return not v['before']
        return False

    for k,v in trace_events.items():
        if before(k):
            early[k] = v
        if after(k):
            late[k] = v

    for k, v in early.items():
        eventmap[k]['ingress_logger'](func, obj, *args, **kwargs)
    ret = func(obj, *args, **kwargs)
    for k, v in late.items():
        eventmap[k]['egress_logger'](func, obj, ret, *args, **kwargs)
    return ret

def trace_point(name:str):
    """ Decorator to add a trace_point type to an object."""
    def run_func_with_trace_point_set(func, level=1):
        setattr(func, '_trace_point', name)
        return func
    return run_func_with_trace_point_set

def trace_level(level:int):
    """ Decorator to add a tracelevel type to an object."""
    level = int(level)
    def run_func_with_trace_level_set(func):
        setattr(func, '_trace_level', level)
        return func
    return run_func_with_trace_level_set

def trace_event(name:str, trace_point="debug", trace_level=1):
    """ Decorator to add a trace event to an object."""
    def run_func_with_event_list(func):
        if hasattr(func, '_trace_events'):
            events = func._trace_events
        else:
            events = {}
        if not name in events:
            events[name] = {'trace_point':trace_point,
                            'trace_level':trace_level
                            }
        setattr(func, '_trace_events', events)
        return func
    return run_func_with_event_list

def redecorate(obj):
    for k in dir(obj):
        v = getattr(obj, k)
        if isinstance(v, types.FunctionType):
            # yo dog, I hear you like manually making decorators, so
            # here's a manually made decorator.
            def decorate(func):
                return tracecontext()(func)
            v = decorate(v)
            setattr(obj, k, v)

class TracedObjectMeta(type):
    """ This class object provides you with a metaclass you can use in your
    classes to get logging set up with easy defaults
    """
    _default_trace_events = {
        }
    _traced_things = set([])

    def __new__(cls, name, bases, nmspc):
        if not name in ["TracedFunction", "TracedObject"]:
            for k, v in nmspc.items():
                # XXX actually find the right things to decorate
                if isinstance(v, types.FunctionType):
                    # yo dog, I hear you like manually making decorators, so
                    # here's a manually made decorator.
                    def decorate(func):
                        return tracecontext()(func)
                    v = decorate(v)
                    redecorate(v)
                    nmspc[k] = v

            # We use "None" rather than "default" here so that if somebody /sets/
            # something to default, we won't override it with something with lower
            # precedence.
            trace_point = nmspc.setdefault("_trace_point", None)
            nmspc['log'] = LogFunction(trace_point)
        print("cls: %s name: %s" % (cls, name))
        print("bases: %s" % (bases,))
        return type.__new__(cls, name, bases, nmspc)

class TracedObject(metaclass=TracedObjectMeta):
    """ This provides an object which automatically logs some things """

    def __init__(self, *args, **kwargs):
        pass

class TracedFunction(metaclass=TracedObjectMeta):
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        pass

class Logger(object):
    """ This is our logger """
    class __Logger(object):
        def __init__(self, trace_point, trace_level, callback):
            self.callbacks = [callback]
            self.trace_point = trace_point
            self.trace_event = trace_event

        def __call__(self, trace_point, trace_level, fmt, *args):
            if not isinstance(trace_level, int):
                raise TypeError("log level must be an integer")

            t = time.time()
            if isinstance(fmt, dict):
                if args:
                    fmt['args'] = args
                s = fmt
            else:
                try:
                    s = (str(fmt) % args).replace("\n", "\\n")
                except TypeError:
                    print("fmt: '%r' args: %r" % (fmt, args))
                    pdb.set_trace()
                    raise
            for callback in self.callbacks:
                return callback(trace_point, trace_level, t, s)
    traces = {}

    def __init__(self, trace_point, trace_level, callback):
        trace_level = int(trace_level)
        key =(trace_point,trace_level)
        if key in Logger.traces:
            instance = Logger.traces[key]
            instance.callbacks.append(callback)
            redecorate(trace_point, trace_level)
        else:
            instance = Logger.__Logger(trace_point, trace_level, callback)
            Logger.traces[key] = instance

    def __call__(self, trace_point, trace_level, *args):
        trace_level = int(trace_level)
        for k,v in Logger.traces.items():
            if k['trace_point'] != trace_point:
                continue
            if k['trace_level'] < trace_level:
                continue
            instance(trace_point, trace_level, *args)


#log = LogFunction()
#
#@trace_point("zoom")
#class Foo(metaclass=TracedObject):
#    def __init__(self):
#        self.log(1, "this should be log level type zoom")
#        print('1')
#
#    @trace_point("baz")
#    def foo(self):
#        self.log(3, "this should be log type baz")
#        print('2')
#
#    def zonk(self):
#        self.log.debug(3, "this should be log type debug")
#        print('3')
#        return 0
#
#class Bar(metaclass=TracedObject):
#    def __init__(self):
#        self.log(9, "this should be log type default")
#
#@trace_point("incorrect")
#class Baz(metaclass=TracedObject):
#    @trace_point("default")
#    def __init__(self):
#        self.log(4, "this should be log type default")
#
#    def zonk(self):
#        self.log(5,"this should be log type incorrect")
#
#@trace_point("maybe")
#def bullshit():
#    log(4, "does this even work?  maybe...")
#
#x = Foo()
#x.foo()
#x.zonk()
#
#y = Bar()
#
#z = Baz()
#z.zonk()

__all__ = [ "TracedObject", "TracedFunction", "LogFunction",
            "trace_point", "trace_level", "trace_event",
            'eventmap', "get_trace_info"]

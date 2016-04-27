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
import inspect
import sys
import threading
import collections
from decimal import Decimal
import pdb

# XXX FIXME: figure out a good default level
DEFAULT_TRACE_LEVEL = 100

def get_frame_info(frame):
    """ fish our code object and its name out of a stack frame """
    if frame.f_code.co_name == 'bar' :
        pass
    funcname = frame.f_code.co_name
    if 'self' in frame.f_locals:
        obj = frame.f_locals['self']
    elif funcname in frame.f_locals:
        obj = frame.f_locals[funcname]
    elif funcname in frame.f_globals:
        obj = frame.f_globals[funcname]
    else:
        return {'funcname':funcname, 'obj':None}
    return {'obj':obj, 'funcname':funcname}

def stack_frames(frame=None):
    if frame:
        yield frame
        while frame:
            frame = frame.f_back
            if frame:
                yield frame
    else:
        # iterate our frames until we find the first function that's not part of
        # the trace infrastructure.  From there, keep descending until we've
        # either a) run out of frames, or b) gotten a _trace_point and
        # _trace_level
        for f in inspect.stack()[1:]:
            if f and f[0]:
                yield f[0]

def get_trace_info(start_frame=None):
    ret = {'modname':None,
           'clsname':None,
           'funcname':None,
           'qualname':None,
           'obj':None,
           }
    for frame in stack_frames(start_frame):
        info = get_frame_info(frame)
        obj = info['obj']
        if not obj:
            continue
        # basically: never choose this module or the python startup module
        # names, because those are definitely not what we're trying to trace.
        if obj.__module__ in [get_trace_info.__module__,
                             '_frozen_importlib']:
            continue

        funcname = info['funcname']
        if funcname == '__main__':
            break

        ret['obj'] = obj
        ret['funcname'] = funcname

        mod = obj.__module__
        modname = obj.__module__
        cls = obj.__class__
        clsname = obj.__class__.__name__

        if not ret['clsname']:
            ret['clsname'] = clsname
        if not ret['funcname']:
            ret['funcname'] = funcname
        if not ret['modname']:
            ret['modname'] = modname
        if not ret['obj']:
            ret['obj'] = obj

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

class Logger(object):
    """ This is our logger """
    class __Logger(object):
        def __init__(self, trace_point, trace_level, callback):
            self.callbacks = [callback]
            self.trace_point = trace_point
            self.trace_level = trace_level

        def __call__(self, trace_point, trace_level, fmt, *args):
            if not isinstance(trace_level, int):
                raise TypeError("log level must be an integer")
            if trace_level > self.trace_level:
                return

            t = Decimal(time.time()).normalize().quantize(Decimal('0.00001'))
            if isinstance(fmt, dict):
                if args:
                    fmt['args'] = args
                s = fmt
            else:
                try:
                    s = (str(fmt) % args).replace("\n", "\\n")
                except TypeError:
                    print("fmt: '%r' args: %r" % (fmt, args))
                    raise
            tp = trace_point or "default"
            for callback in self.callbacks:
                return callback(tp, trace_level, t, s)
    traces = {}

    def __init__(self, trace_point, trace_level, callback):
        if trace_point is None:
            raise ValueError("trace_point cannot be None")
        if not isinstance(trace_level, int):
            raise TypeError("trace_level must be an integer")
        key = (trace_point, trace_level)
        if not key in Logger.traces:
            Logger.traces[key] = Logger.__Logger(trace_point, trace_level, callback)
        instance = Logger.traces[key]
        if not callback in instance.callbacks:
            instance.callbacks.append(instance)

        # redecorate(trace_point, trace_level)
        # print("Logger.traces: %s" % (Logger.traces,))

    def __call__(self, trace_point, trace_level, *args):
        if trace_point is None:
            raise ValueError("trace_point cannot be None")
        if not isinstance(trace_level, int):
            raise TypeError("trace_level must be an integer")
        for logger in find_loggers(trace_point, trace_level):
            logger(trace_point, trace_level, *args)

def find_loggers(trace_point:str, trace_level:int, regexp=False):
    """ This generator provides all the valid loggers registered for a given
        trace_point string and trace_level."""
    if trace_point is None:
        raise ValueError("trace_point cannot be None")
    if not isinstance(trace_level, int):
        raise TypeError("trace_level must be an integer")

    # somebody might want to turn some specific kind of thing on, but
    # silence some particular message level.  They can do that with
    # "squelch".
    if trace_point == 'squelch' or trace_point.endswith('.squelch') or \
            '.squelch.' in trace_point:
        raise StopIteration

    for k,v in Logger.traces.items():
        tp = k[0]
        dottpdot = ".%s." % (tp,)
        dottp = ".%s" % (tp,)

        # XXX make globbing work
        # XXX make regexps work
        # print("trace_point: %s tp: %s" % (trace_point, tp))
        if trace_point != tp and not trace_point.endswith(dottp) and \
                not dottpdot in trace_point:
            continue
        if k[1] < trace_level:
            continue
        yield v

class LogFunction(object):
    """ This class provides a callable to log some data """

    def __init__(self, trace_point=None, qualname=None, base=False):
        self._qualname = ""
        self.__tracepoint = ""
        self._base = base
        self._name = ""

        if qualname == "default":
            qualname = None
        elif qualname and qualname.endswith(".default"):
            qualname = qualname[:-8]
        if trace_point and trace_point.endswith(".default"):
            trace_point = trace_point[:-8]
        if qualname and trace_point and trace_point.startswith(qualname):
            trace_point = trace_point[:-len(qualname)]
        if not qualname and trace_point and "." in trace_point:
            qualname = trace_point
            trace_point = "default"
        #print("qn: %s tp: %s base: %s" % (qualname, trace_point, base))
        if qualname:
            if qualname.endswith(".default"):
                qualname = qualname[:-8]
            elif trace_point and "." in trace_point:
                qualname = trace_point
            self._qualname = qualname
            self._name = trace_point or "default"

        if self._qualname:
            qn = "%s." % (self._qualname,)
        else:
            qn = ""
        tp = "%s%s" % (qn, trace_point or "default")
        self.__tracepoint = tp
        #print("s.qn: %s s.tp: %s s.n: %s" % (self._qualname, self.__tracepoint,
        #    self._name))

    def __call__(self, trace_level, fmt, *args):
        trace_point = self.__tracepoint or "default"
        for logger in find_loggers(trace_point, trace_level):
            logger(trace_point, trace_level, fmt, *args)

    # This makes it so in TracedObject we can just add a "log" callable
    # that does whatever the function's default trace_point is, but
    # any caller can do "self.log.debug(level, msg)" and get "debug" as the
    # tracepoint, or anything else they put in that position, unless they try to
    # name their tracepoint __init__, __dict__, __getattr__, __call__, etc.,
    # which will fail.
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name.startswith('_'):
            raise AttributeError(name)
        else:
            lf = LogFunction(qualname=self.__tracepoint, trace_point=name)
            self.__dict__[name] = lf
            return lf

# just a convenient default logger we can use
log = LogFunction(qualname=LogFunction.__module__)

def trace_dispatcher(frame, event, arg):
    global log
    log.trace_dispatcher.ingress(1,
            "trace_dispatcher(frame=%r, event=%r, arg=%r)" %
            (frame, event, arg))
    if frame.f_code.co_name in ['TracedObject', 'TracedFunction']:
        return
    info = get_trace_info(frame)
    # dlog.trace_dispatcher.debug(9, "info: %s" % (info,))
    qualname = info['qualname']
    obj = info['obj']
    fas = inspect.getargvalues(frame)
    args = inspect.formatargvalues(*fas)
    # print("qualname: %s" % (qualname,))
    # print("obj: %s" % (obj,))
    frame = frame.f_back
    if event == "call":
        lines = inspect.getsource(frame).split("\n")
        for line in lines:
            if line.strip():
                obj.log.ingress(7, "%s" % (line))

        fmt = "".join(traceback.format_stack(frame))
        for s in fmt.split('\n'):
            if s.strip():
                obj.log.ingress(5, "%s" % (s))

        obj.log.ingress(3, "%s line %s" % (inspect.getsourcefile(frame),
                                           inspect.getlineno(frame)))
        obj.log.ingress(1, "%s%s" % (qualname, args))
        return trace_dispatcher
    elif event == "return" and frame.f_code.co_name != '__exit__':
        obj.log.egress(3, "%s line %s" % (inspect.getsourcefile(frame),
                                          inspect.getlineno(frame)))
        obj.log.egress(1, "%s%s = %r" % (qualname, args, arg))
        sys.settrace(None)
    log.trace_dispatcher.egress(1,
            "trace_dispatcher(frame=%r, event=%r, arg=%r) = None" %
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

def tracepoint(name:str):
    """ Decorator to add a trace_point type to an object."""
    def run_func_with_trace_point_set(func, level=1):
        setattr(func, '_trace_point', name)
        return func
    return run_func_with_trace_point_set

def get_caller_module():
    return None

def tracelevel(level:int):
    """ Decorator to add a tracelevel type to an object."""
    level = int(level)
    mod = get_caller_module()
    def run_func_with_trace_level_set(func):
        setattr(func, '_trace_level', level)
        if mod:
            func.__module__ = mod
        return func

    return run_func_with_trace_level_set

class TracedObjectMeta(type):
    """ This class object provides you with a metaclass you can use in your
    classes to get logging set up with easy defaults
    """

    def __new__(cls, name, bases, nmspc):
        new_nmspc = {}
        for k, v in nmspc.items():
            if k in ["TracedFunction", "TracedObject"]:
                new_nmspc[k] = v
            else:
                # XXX actually find the right things to decorate
                if isinstance(v, types.FunctionType) or hasattr(v, '__call__'):
                    # yo dog, I hear you like manually making decorators, so
                    # here's a manually made decorator.
                    def decorate(func):
                        return tracecontext()(func)
                    new_nmspc[k] = decorate(v)

            # We use "None" rather than "default" here so that if somebody /sets/
            # something to default, we won't override it with something with lower
            # precedence.
            trace_point = nmspc.get('_trace_point') or None
            new_nmspc["_trace_point"] = trace_point

        x = type.__new__(cls, name, bases, new_nmspc)

        # XXX seriously this is the worst damned hack.  If we don't do this,
        # everything uselessly says it's from /this/ module.
        def guess_modname_from_nmspc(nmspc):
            modnames = {}
            for v in nmspc.values():
                if hasattr(v, '__module__'):
                    if v.__module__.startswith('_frozen_'):
                        continue
                    modnames.setdefault(v.__module__, 0)
                    modnames[v.__module__] += 1
            n = 0
            name = None
            for k,v in modnames.items():
                if v > n:
                    name = k
            return name or cls.__module__
        modname = guess_modname_from_nmspc(nmspc)
        setattr(x, '__module__', modname)
        qualname = "%s.%s" % (x.__module__, x.__name__)
        log = LogFunction(qualname=qualname, trace_point="default")
        setattr(x, 'log', log)
        return x

class TracedObject(object, metaclass=TracedObjectMeta):
    """ This provides an object which automatically logs some things """

@contextmanager
def logcontext(func):
    if hasattr(func, 'log'):
        yield func.log
    else:
        qn = "%s.%s" % (func.__module__, func.__name__)
        log = LogFunction(qualname=qn, trace_point="default")
        yield log

class TracedFunction(object):
    def __new__(cls, self):
        with logcontext(self) as log:
            def decorate(func):
                f = tracecontext()(func)
                setattr(func, 'log', log)
                setattr(f, 'log', log)
                return f
            self.__callee__ = decorate(self)

            # we don't want the module import to instantiate these, because
            # get_trace_info() will wind up trying to find info about
            # TracedObjectMeta instead of our real object.  def
            # defer_this_call(): return LogFunction("default")
            #self.log = defer_this_call
            setattr(self, 'log', log)
            return self

    def __call__(self, *args, **kwargs):
        callee = self.__callee__(*args, **kwargs)
        return callee

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
            "tracepoint", "tracelevel", "get_trace_info"]

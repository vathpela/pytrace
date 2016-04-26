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
        #print("lalalalaa")
        #print("dir(frame): %s" % (dir(frame)))
        #print("dir(frame.f_code): %s" % (dir(frame.f_code)))
        #print("locals: %s" % (frame.f_locals))
        pass
    funcname = frame.f_code.co_name
    if 'self' in frame.f_locals:
        obj = frame.f_locals['self']
    elif funcname in frame.f_locals:
        obj = frame.f_locals[funcname]
    elif funcname in frame.f_globals:
        obj = frame.f_globals[funcname]
    else:
        f = {'funcname':funcname, 'obj':None}
        #print("f: %s" % (f,))
        return f
    g = {'obj':obj, 'funcname':funcname}
    #print("g: %s" % (g,))
    return g

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

def get_trace_info(start_frame=None, extracrud=True):
    first_found = {
            'modname':None,
            'clsname':None,
            'funcname':None,
            }
    for frame in stack_frames(start_frame):
        ret = {'modname':None,
               'clsname':None,
               'funcname':None,
               'qualname':None,
               'obj':None,
               }

        info = get_frame_info(frame)
        obj = info['obj']
        if not obj:
            continue
        if extracrud:
            # print("info: %s" % (info,))
            # print("obj.__module__: %s" % (obj.__module__,))
            pass
        if obj.__module__ == get_trace_info.__module__:
            continue
        funcname = info['funcname']
        if funcname == '__main__':
            break

        if obj:
            mod = obj.__module__
            modname = obj.__module__
            cls = obj.__class__
            clsname = obj.__class__.__name__
        else:
            pdb.set_trace()
            pass

        if clsname == 'trace' or funcname == 'event_tracer':
            #continue
            pass

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

class LogFunction(object):
    """ This class provides a callable to log some data """

    def __init__(self, trace_point=None, base=True):
        info = get_trace_info()
        if info['funcname'] == '__init__':
            self._qualname = "%(modname).%(clsname)" % info
            self._name = trace_point
        elif info['qualname']:
            self._qualname = info["qualname"]
            self._name = trace_point
        else:
            self._qualname = LogFunction.__module__
            self._name = None
            #print("holy zonkballs batman: %s" % (info,))
            #pdb.set_trace()
        self._trace_point = trace_point
        self._base = base

    def __call__(self, trace_level, fmt, *args):
        trace_point = self._trace_point or "default"
        for logger in find_loggers(trace_point, trace_level):
            logger(trace_point, trace_level, fmt, *args)

    # This makes it so in TracedObject we can just add a "log" callable
    # that does whatever the function's default trace_point is, but
    # any caller can do "self.log.debug(level, msg)" and get "debug" as the
    # tracepoint, or anything else they put in that position, unless they try to
    # name their tracepoint __init__, __dict__, __getattr__, __call__, etc.,
    # which will fail.
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        elif name in self.__dict__:
            return self.__dict__[name]
        elif name.startswith('_'):
            raise AttributeError(name)
        else:
            qn = self.__dict__.setdefault('_qualname', '')
            if qn:
                qn = "%s.%s" % (qn, name)
            else:
                qn = "%s" % (name,)
            lf = LogFunction(trace_point=qn, base=False)
            self.__dict__[name] = lf
            return lf

# just a convenient default logger we can use
dlog = LogFunction(None)

def trace_dispatcher(frame, event, arg):
    global log
    dlog.ingress(9,
            "%s: trace_dispatcher(frame=%r, event=%r, arg=%r)" %
            (trace_dispatcher.__module__, frame, event, arg))
    if frame.f_code.co_name in ['TracedObject', 'TracedFunction']:
        return
    info = get_trace_info(frame, extracrud=True)
    # dlog.trace_dispatcher.debug(9, "info: %s" % (info,))
    qualname = info['qualname']
    obj = info['obj']
    fas = inspect.getargvalues(frame)
    args = inspect.formatargvalues(*fas)
    if hasattr(obj, 'log'):
        log = obj.log
    else:
        log = dlog
    frame = frame.f_back
    if event == "call":
        lines = inspect.getsource(frame).split("\n")
        for line in lines:
            if line.strip():
                log.ingress(7, "%s %s" % (qualname, line))

        fmt = "".join(traceback.format_stack(frame))
        for s in fmt.split('\n'):
            if s.strip():
                log.ingress(5, "%s:%s" % (qualname, s))

        log.ingress(3, "%s %s line %s" % (qualname,
                                          inspect.getsourcefile(frame),
                                          inspect.getlineno(frame)))
        log.ingress(1, "%s%s" % (qualname, args))
        return trace_dispatcher
    elif event == "return" and frame.f_code.co_name != '__exit__':
        log.egress(3, "%s %s line %s" % (qualname,
                                          inspect.getsourcefile(frame),
                                          inspect.getlineno(frame)))
        log.egress(1, "%s(%s) = %r" % (qualname, args, arg))
        sys.settrace(None)
    dlog.egress(9,
            "%s: trace_dispatcher(frame=%r, event=%r, arg=%r) = None" %
            (trace_dispatcher.__module__, frame, event, arg))

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
        return True

eventmap = {
    }

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

def traceevent(name:str, trace_point="debug", trace_level=1):
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
                x = tracecontext()(func)
                return x
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

        frames = [f[0] for f in inspect.stack()[1:]]
        info = get_trace_info()
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
                        x = tracecontext()(func)
                        #print("dir(x): %s" % (dir(x)))
                        #print("dir(func): %s" % (dir(func)))
                        #print("x.__qualname__: %s" % (x.__qualname__))
                        #print("func.__qualname__: %s" % (func.__qualname__))
                        #print("x.__module__: %s" % (x.__module__))
                        #print("func.__module__: %s" % (func.__module__))
                        return x
                    v = decorate(v)
                    # print("redecorating %s.%s" % (name, k))
                    # redecorate(v)
                    new_nmspc[k] = v

            # We use "None" rather than "default" here so that if somebody /sets/
            # something to default, we won't override it with something with lower
            # precedence.
            trace_point = nmspc.get('_trace_point') or None
            new_nmspc["_trace_point"] = trace_point

            # we don't want the module import to instantiate these, because
            # get_trace_info() will wind up trying to find info about
            # TracedObjectMeta instead of our real object.
            def defer_this_call():
                return LogFunction("default")
            new_nmspc['log'] = defer_this_call

        x = type.__new__(cls, name, bases, new_nmspc)

        # XXX seriously this is the worst damned hack.  If we don't do this,
        # everything uselessly says it's from /this/ module.
        def guess_modname_from_nmspc(nmspc):
            modnames = {}
            for v in nmspc.values():
                if hasattr(v, '__module__'):
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
        return x

class TracedObject(object, metaclass=TracedObjectMeta):
    """ This provides an object which automatically logs some things """

@contextmanager
def logcontext(func):
    yield func.log

class TracedFunction(object):
    def __new__(cls, self):
        def decorate(func):
            return tracecontext()(func)
        self.__callee__ = decorate(self)

        # we don't want the module import to instantiate these, because
        # get_trace_info() will wind up trying to find info about
        # TracedObjectMeta instead of our real object.
        def defer_this_call():
            return LogFunction("default")
        self.log = defer_this_call

        return self

    def __call__(self, *args, **kwargs):
        with logcontext(self) as log:
            callee = self.__callee__(*args, **kwargs)

class Logger(object):
    """ This is our logger """
    class __Logger(object):
        def __init__(self, trace_point, trace_level, callback):
            self.callbacks = [callback]
            self.trace_point = trace_point
            #self.trace_event = trace_event

        def __call__(self, trace_point, trace_level, fmt, *args):
            if not isinstance(trace_level, int):
                raise TypeError("log level must be an integer")

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
                    #pdb.set_trace()
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
            "tracepoint", "tracelevel", "traceevent",
            'eventmap', "get_trace_info"]

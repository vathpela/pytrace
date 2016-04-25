#!/usr/bin/python3

# this is just a simple logger, so I can have a logger to show you
class Logger(object):
    def __init__(self):
        self.loglevel = 0

    def __call__(self, level, msg):
        import time
        if self.loglevel >= level:
            print("%s %s" % (time.asctime(), msg))

logger = Logger()

# this is the thing having log points added to it
class ExampleClass(object):
    _trace_points = {"foo":"show_state"}
    def __init__(self):
        self._state = 1

    @property
    def state(self):
        return self._state

    def show_state(self):
        print("self.state: %d" % (self.state,))
        return 4

# here is the magic you don't need to see
class LogEditor(object):
    def __init__(self, parent, child, level, logtypes):
        self.parent = parent
        self.child = child
        self.method = getattr(parent, child)
        self.level = level
        self.logtypes = logtypes

    def __call__(self, *args, **kwds):
        if "ingress" in self.logtypes:
            logger(3, "ingress %s(args=%s, kwds=%s)" % (self.method.__name__, args, kwds))
        if "traceback" in self.logtypes:
            import traceback
            stack = "\n" + "".join(traceback.format_stack()).rstrip()
            logger(3, stack)
        ret = self.method(self=self.__real_object__, *args[1:], **kwds)
        if "egress" in self.logtypes:
            logger(3, "egress %s() = %s" % (self.method.__name__, ret))
        return ret

    def __real_init__(self, *args, **kwds):
        self.__real_object__ = self.parent.__new__(self.parent, *args, **kwds)
        self.__fake_init__(self=self.__real_object__, *args, **kwds)
        return None

def add_logging(parent, child, level, logtypes=["ingress", "egress"]):
    if hasattr(parent, "_trace_points") and child in parent._trace_points:
        child = parent._trace_points[child]
    old = getattr(parent, child)
    if isinstance(old, LogEditor):
        for logtype in logtypes:
            if not logtype in old.logtypes:
                old.logtypes.append(logtype)
    else:
        newlogger = LogEditor(parent, child, level, logtypes)
        setattr(parent, child, newlogger)
        setattr(newlogger, '__fake_init__', parent.__init__)
        setattr(parent, '__init__', newlogger.__real_init__)

# make kickstart drive these lines via something more or less something like:
#
# %logging
# method ExampleClass.foo --level 3
# method ExampleClass.foo --level 3 --traceback
#
add_logging(ExampleClass, "foo", 3)
add_logging(ExampleClass, "foo", 3, logtypes=["traceback"])

# and then here's the normal usage code:
x = ExampleClass()
print("run with loglevel=0:")
x.show_state()
print("run with loglevel=3:")
logger.loglevel = 3
x.show_state()

from __future__ import with_statement
import random
import re
import socket

import mock
from nose.tools import eq_

from statsd import StatsClient


ADDR = (socket.gethostbyname('localhost'), 8125)


def _client(prefix=None, batch_len=1):
    sc = StatsClient(host=ADDR[0], port=ADDR[1], prefix=prefix, batch_len=batch_len)
    sc._sock = mock.Mock()
    return sc


def _sock_check(cl, count, val):
    eq_(cl._sock.sendto.call_count, count)
    if val:
        val = val.encode('ascii')
        eq_(cl._sock.sendto.call_args, ((val, ADDR), {}))
    else:
        eq_(cl._sock.sendto.call_args, None)


class assert_raises(object):
    """A context manager that asserts a given exception was raised.

    >>> with assert_raises(TypeError):
    ...     raise TypeError

    >>> with assert_raises(TypeError):
    ...     raise ValueError
    AssertionError: ValueError not in ['TypeError']

    >>> with assert_raises(TypeError):
    ...     pass
    AssertionError: No exception raised.

    Or you can specify any of a number of exceptions:

    >>> with assert_raises(TypeError, ValueError):
    ...     raise ValueError

    >>> with assert_raises(TypeError, ValueError):
    ...     raise KeyError
    AssertionError: KeyError not in ['TypeError', 'ValueError']

    You can also get the exception back later:

    >>> with assert_raises(TypeError) as cm:
    ...     raise TypeError('bad type!')
    >>> cm.exception
    TypeError('bad type!')
    >>> cm.exc_type
    TypeError
    >>> cm.traceback
    <traceback @ 0x3323ef0>

    Lowercase name because that it's a class is an implementation detail.

    """

    def __init__(self, *exc_cls):
        self.exc_cls = exc_cls

    def __enter__(self):
        # For access to the exception later.
        return self

    def __exit__(self, typ, value, tb):
        assert typ, 'No exception raised.'
        assert typ in self.exc_cls, '%s not in %s' % (
            typ.__name__, [e.__name__ for e in self.exc_cls])
        self.exc_type = typ
        self.exception = value
        self.traceback = tb

        # Swallow expected exceptions.
        return True


@mock.patch.object(random, 'random', lambda: -1)
def test_incr():
    sc = _client()

    sc.incr('foo')
    _sock_check(sc, 1, 'foo:1|c')

    sc.incr('foo', 10)
    _sock_check(sc, 2, 'foo:10|c')

    sc.incr('foo', 1.2)
    _sock_check(sc, 3, 'foo:1.2|c')

    sc.incr('foo', 10, rate=0.5)
    _sock_check(sc, 4, 'foo:10|c|@0.5')


@mock.patch.object(random, 'random', lambda: -1)
def test_decr():
    sc = _client()

    sc.decr('foo')
    _sock_check(sc, 1, 'foo:-1|c')

    sc.decr('foo', 10)
    _sock_check(sc, 2, 'foo:-10|c')

    sc.decr('foo', 1.2)
    _sock_check(sc, 3, 'foo:-1.2|c')

    sc.decr('foo', 1, rate=0.5)
    _sock_check(sc, 4, 'foo:-1|c|@0.5')


@mock.patch.object(random, 'random', lambda: -1)
def test_gauge():
    sc = _client()
    sc.gauge('foo', 30)
    _sock_check(sc, 1, 'foo:30|g')

    sc.gauge('foo', 1.2)
    _sock_check(sc, 2, 'foo:1.2|g')

    sc.gauge('foo', 70, rate=0.5)
    _sock_check(sc, 3, 'foo:70|g|@0.5')


@mock.patch.object(random, 'random', lambda: -1)
def test_timing():
    sc = _client()

    sc.timing('foo', 100)
    _sock_check(sc, 1, 'foo:100|ms')

    sc.timing('foo', 350)
    _sock_check(sc, 2, 'foo:350|ms')

    sc.timing('foo', 100, rate=0.5)
    _sock_check(sc, 3, 'foo:100|ms|@0.5')


@mock.patch.object(random, 'random', lambda: -1)
def test_batch():
    sc = _client(None, 2)

    sc.incr('foo')
    _sock_check(sc, 0, '')

    sc.incr('bar')
    _sock_check(sc, 1, 'foo:1|c\nbar:1|c')

@mock.patch.object(random, 'random', lambda: -1)
def test_batch_flush():
    sc = _client(None, 10)

    sc.incr('foo')
    _sock_check(sc, 0, '')

    sc.incr('bar')
    _sock_check(sc, 0, '')

    sc.flush()
    _sock_check(sc, 1, 'foo:1|c\nbar:1|c')

def test_prefix():
    sc = _client('foo')

    sc.incr('bar')
    _sock_check(sc, 1, 'foo.bar:1|c')


def _timer_check(cl, count, start, end):
    eq_(cl._sock.sendto.call_count, count)
    value = cl._sock.sendto.call_args[0][0].decode('ascii')
    exp = re.compile('^%s:\d+|%s$' % (start, end))
    assert exp.match(value)


def test_timer_manager():
    """StatsClient.timer is a context manager."""
    sc = _client()

    with sc.timer('foo'):
        pass

    _timer_check(sc, 1, 'foo', 'ms')


def test_timer_manager():
    """StatsClient.timer is a decorator."""
    sc = _client()

    @sc.timer('bar')
    def bar():
        pass

    bar()

    _timer_check(sc, 1, 'bar', 'ms')


def test_timer_capture():
    """You can capture the output of StatsClient.timer."""
    sc = _client()
    with sc.timer('woo') as result:
        eq_(result.ms, None)
    assert isinstance(result.ms, int)


@mock.patch.object(random, 'random', lambda: -1)
def test_timer_context_rate():
    sc = _client()

    with sc.timer('foo', rate=0.5):
        pass

    _timer_check(sc, 1, 'foo', 'ms|@0.5')


@mock.patch.object(random, 'random', lambda: -1)
def test_timer_decorator_rate():
    sc = _client()

    @sc.timer('bar', rate=0.1)
    def bar():
        pass

    bar()

    _timer_check(sc, 1, 'bar', 'ms|@0.1')


def test_timer_context_exceptions():
    """Exceptions within a managed block should get logged and propagate."""
    sc = _client()

    with assert_raises(socket.timeout):
        with sc.timer('foo'):
            raise socket.timeout()

    _timer_check(sc, 1, 'foo', 'ms')


def test_timer_decorator_exceptions():
    """Exceptions from wrapped methods should get logged and propagate."""
    sc = _client()

    @sc.timer('foo')
    def foo():
        raise ValueError()

    with assert_raises(ValueError):
        foo()

    _timer_check(sc, 1, 'foo', 'ms')

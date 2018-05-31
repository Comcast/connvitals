# Copyright 2018 Comcast Cable Communications Management, LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module contains utility functions used by the main utility to do things
lke printing errors and warnings to stderr, or get a single, valid IP address
for a host.
"""

import typing
import socket

# I don't know why, but pylint seems to think that socket.AddressFamily isn't real, but it is.
# Nobody else has this issue as far as I could find.
#pylint: disable=E1101
Host = typing.NamedTuple("Host", [('addr', str), ('family', socket.AddressFamily)])
#pylint: enable=E1101

PingResult = typing.NamedTuple("PingResult", [
                                  ('minimum', float),
                                  ('avg',     float),
                                  ('maximum', float),
                                  ('std',     float),
                                  ('loss',    float)])

def pingResultToStr(self: PingResult) -> str:
	"""
	Returns the string representation of a ping result in plaintext
	"""
	fmt = "%.3f\t%.3f\t%.3f\t%.3f\t%.3f"
	return fmt % (self.minimum, self.avg, self.maximum, self.std, self.loss)

def pingResultRepr(self: PingResult) -> str:
	"""
	Returns the JSON representation of a ping result
	"""
	fmt = '{"min":%f,"avg":%f,"max":%f,"std":%f,"loss":%f}'
	return fmt % (self.minimum, self.avg, self.maximum, self.std, self.loss)

PingResult.__str__ = pingResultToStr
PingResult.__repr__ = pingResultRepr


TraceStep = typing.NamedTuple("TraceStep", [("host", str), ("rtt", float)])
Trace = typing.NewType("Trace", typing.List[TraceStep])

def traceStepToStr(self: TraceStep) -> str:
	"""
	Returns the string representation of a step of a route trace in plaintext

	>>> traceStepToStr(TraceStep("1.2.3.4", 3.059267))
	'1.2.3.4\\t3.059'
	>>> traceStepToStr(TraceStep("*", -1))
	'*'
	"""
	if self.rtt < 0 or self.host == "*":
		return "*"
	return "%s\t%.3f" % (self.host, self.rtt)

def traceStepRepr(self: TraceStep) -> str:
	"""
	Returns the JSON representation of a single step in a route trace

	>>> traceStepRepr(TraceStep("1.2.3.4", 3.059267))
	'["1.2.3.4", 3.059267]'
	>>> traceStepRepr(TraceStep("*", -1))
	'["*"]'
	"""
	if self.rtt < 0 or self.host == "*":
		return '["*"]'
	return '["%s", %f]' % (self.host, self.rtt)

def compareTraceSteps(self: TraceStep, other: TraceStep) -> bool:
	"""
	Implements `self == other`

	Two trace steps are considered equal iff their hosts are the same - rtt is not considered.

	>>> compareTraceSteps(TraceStep("localhost", -800), TraceStep("localhost", 900))
	True
	>>> compareTraceSteps(TraceStep("localhost", 7), TraceStep("127.0.0.1", 7))
	False
	"""
	return self.host == other.host

def traceStepIsValid(self: TraceStep) -> bool:
	"""
	Implements `bool(self)`

	Returns True if the step reports that the packet reached the host within the timeout,
	False otherwise.

	>>> traceStepIsValid(TraceStep('*', -1))
	False
	>>> traceStepIsValid(TraceStep("someaddr", 0))
	True
	>>> traceStepIsValid(TraceStep("someotheraddr", 27.0))
	True
	"""
	return self.rtt >= 0 and self.host != "*"

TraceStep.__str__ = traceStepToStr
TraceStep.__repr__ = traceStepRepr
TraceStep.__eq__ = compareTraceSteps
TraceStep.__bool__ = traceStepIsValid

def compareTraces(self: Trace, other: Trace) -> bool:
	"""
	Implements `self == other`

	Checks that traces are of the same length and contain the same hosts in the same order
	i.e. does *not* check the rtts of any or all trace steps.

	Note: ignores steps that are invalid ('*').

	>>> a = Trace([TraceStep('0.0.0.1', 0), TraceStep('0.0.0.2', 0)])
	>>> b=Trace([TraceStep('0.0.0.1',0), TraceStep('*',-1), TraceStep('*',-1), TraceStep('0.0.0.2',0)])
	>>> compareTraces(a, b)
	True
	"""
	this, that = [step for step in self if step], [step for step in other if step]
	return len(this) == len(that) and all(this[i] == that[i] for i in range(len(this)))

def traceToStr(self: Trace) -> str:
	"""
	Implements `str(self)`

	Returns the plaintext representation of a route trace.
	"""
	return '\n'.join(str(step) for step in self)

def traceRepr(self: Trace) -> str:
	"""
	Implements `repr(self)`

	Returns the JSON representation of a route trace.
	"""
	return "[%s]" % ','.join(repr(step) for step in self)

Trace.__str__ = traceToStr
Trace.__repr__ = traceRepr
Trace.__eq__ = compareTraces


ScanResult = typing.NamedTuple("ScanResult", [("httpresult", typing.Tuple[float, str, str]),
                                              ("httpsresult", typing.Tuple[float, str, str]),
                                              ("mysqlresult", typing.Tuple[float, str])])

def scanResultToStr(self: ScanResult) -> str:
	"""
	Returns the string representation of a portscan result in plaintext
	"""
	return "%s\t%s\t%s" % ("%.3f, %s, %s" % self.httpresult if self.httpresult else 'None',
	                       "%.3f, %s, %s" % self.httpsresult if self.httpsresult else 'None',
	                       "%.3f, %s" % self.mysqlresult if self.mysqlresult else 'None')

def scanResultRepr(self: ScanResult) -> str:
	"""
	Returns the JSON representation of a portscan result
	"""
	httpFmt = '{"rtt":%f,"response code":"%s","server":"%s"}'
	http = httpFmt % self.httpresult if self.httpresult else '"None"'
	https = httpFmt % self.httpsresult if self.httpsresult else '"None"'
	mySQL = '{"rtt":%f,"version":"%s"}' % self.mysqlresult if self.mysqlresult else '"None"'
	return '{"http":%s,"https":%s,"mysql":%s}' % (http, https, mySQL)

ScanResult.__str__ = scanResultToStr
ScanResult.__repr__ = scanResultRepr


def error(err: Exception, fatal: int=False):
	"""
	Logs an error to stderr, then exits if fatal is a non-falsy value, using it as an exit code
	"""
	from sys import stderr
	from time import ctime
	if stderr.isatty():
		fmt = "\033[38;2;255;0;0mEE: %s:"
		print(fmt % type(err).__name__, "%s" % err, "-\t", ctime(), "\033[m", file=stderr)
	else:
		print("EE: %s:" % type(err).__name__, "%s" % err, "-\t", ctime(), file=stderr)
	if fatal:
		exit(int(fatal))

def warn(warning: str):
	"""
	Logs a warning to stderr.
	"""
	from sys import stderr
	from time import ctime
	if stderr.isatty():
		print("\033[38;2;238;216;78mWW:", warning, "-\t", ctime(), "\033[m", file=stderr)
	else:
		print("WW:", warning, '-\t', ctime(), file=stderr)

def getaddr(host: str) -> typing.Optional[Host]:
	"""
	Returns a tuple of Address Family, IP Address for the host passed in `host`.
	"""

	try:
		addrinfo = socket.getaddrinfo(host, 1).pop()
		return Host(addrinfo[4][0], addrinfo[0])
	except socket.gaierror:
		return None

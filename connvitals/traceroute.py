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
This module defines a single function which implements route tracing.
"""
import socket
import struct
from struct import unpack
import time
from . import utils

class Tracer():
	"""
	A context-manage-able route tracer.
	"""

	def __init__(self, host:utils.Host, ID:int, maxHops:int):
		"""
		Constructs a route tracer, including the sockets used to send/recieve
		route tracer packets.

		Not that - unlike the functional implementation - this takes a direct
		integer instead of a whole `Config` object to determine `maxHops`.
		"""
		self.host = host
		self.ID = ID
		self.maxHops = maxHops

		# A bunch of stuff needs to be tweaked if we're using IPv6
		if host.family is socket.AF_INET6:
			# BTW, this doesn't actually work. The RFCs for IPv6 don't define
			# the behaviour of raw sockets - which are heavily utilized by
			# `connvitals`. One of these days, I'll have to implement it using
			# raw ethernet frames ...

			self.receiver = socket.socket(family=host.family,
			                              type=socket.SOCK_RAW,
			                              proto=socket.IPPROTO_ICMPV6)
			self.setTTL = self.setIPv6TTL
			self.isMyTraceResponse = self.isMyIPv6TraceResponse

		else:
			self.receiver = socket.socket(family=host.family,
			                              type=socket.SOCK_RAW,
			                              proto=socket.IPPROTO_ICMP)

		# We need a sender because a UDP socket can't receive ICMP 'TTL
		# Exceeded In Transit' packets, and having a raw sender introduces
		# a slew of new issues.
		self.sender = socket.socket(family=host.family,
		                            type=socket.SOCK_DGRAM)
		self.receiver.settimeout(0.05)

	def __enter__(self) -> 'Tracer':
		"""
		Context-managed instantiation.
		"""
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		"""
		Context-managed cleanup.
		"""
		self.sender.shutdown(socket.SHUT_RDWR)
		self.sender.close()
		self.receiver.shutdown(socket.SHUT_RDWR)
		self.receiver.close()

		# Print exception information if possible
		if exc_type and exc_value:
			utils.error(exc_type("Unknown error occurred in route trace"))
			utils.error(exc_type(exc_value))
			if traceback:
				utils.warn("Stack Trace for route trace error: %s" % traceback)

	def __del__(self):
		"""
		Non-context-managed cleanup.
		"""
		try:
			self.sender.close()
			self.receiver.close()
		except AttributeError:
			# At least one of the socket references was already deleted
			pass

	def trace(self) -> utils.Trace:
		"""
		Runs the route trace, returning a list of visited hops
		"""
		from time import time
		ret = []

		for ttl in range(1, self.maxHops+1):
			self.setTTL(ttl)

			rtt = time()

			try:
				self.sender.sendto(b'', (self.host.addr, self.ID))
			except OSError:
				ret.append(utils.TraceStep("*", -1))

			try:
				while True:
					pkt, addr = self.receiver.recvfrom(1024)
					rtt = time() - rtt

					if self.isMyTraceResponse(pkt):
						break

			except socket.timeout:
				ret.append(utils.TraceStep("*", -1))
			else:
				ret.append(utils.TraceStep(addr[0], rtt*1000))
				if addr[0] == self.host.addr:
					break

		return utils.Trace(ret)

	def setIPv4TTL(self, ttl:int):
		"""
		Sets the TTL assuming `sender` is an IPV4 socket.
		"""
		self.sender.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)

	def setIPv6TTL(self, ttl:int):
		"""
		Sets the TTL assuming `sender` is an IPV6 socket.
		"""
		# Actually, hop limits should be set at the packet level, so this'll
		# change when I move to ethernet frames.
		self.sender.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, ttl)

	def isMyIPv4TraceResponse(self, pkt:bytes) -> bool:
		"""
		Returns `True` if `pkt` is an IPv4 Traceroute Response AND it came
		from this particular Tracer - otherwise `False`.
		"""
		return pkt[20] in {11,3} and unpack("!H", pkt[50:52])[0] == self.ID

	def isMyIPv6TraceResponse(self, pkt:bytes) -> bool:
		"""
		Returns `True` if `pkt` is an IPv6 Traceroute Response AND it came
		from this particular Tracer - otherwise `False`
		"""
		return x[0] in {1,3} # ID fetch not implemented, since this isn't actually supported yet.

	# IPv4 is default
	setTTL = setIPv4TTL
	isMyTraceResponse = isMyIPv4TraceResponse


# Functional implementation still exists for convenience/legacy compatibility.

def trace(host: utils.Host, myID: int, config: 'config.Config') -> utils.Trace:
	"""
	Traces a route from the localhost to a given destination.
	Returns a tabular list of network hops up to the maximum specfied by 'hops'
	"""

	ret = []

	ipv6 = host[1] == socket.AF_INET6

	receiver = socket.socket(family=host.family, type=socket.SOCK_RAW, proto=58 if ipv6 else 1)
	receiver.settimeout(0.05)
	sender = socket.socket(family=host.family, type=socket.SOCK_DGRAM, proto=17)

	# Sets up functions used in the main loop, so it can transparently
	# handle ipv4 and ipv6 without needing to check which one we're
	# using on every iteration.
	setTTL, isTraceResponse, getIntendedDestination = None, None, None
	getID = lambda x: (x[50] << 8) + x[51]
	if ipv6:
		setTTL = lambda x: sender.setsockopt(41, 4, x)
		isTraceResponse = lambda x: x[0] in {1, 3}
		getIntendedDestination = lambda x: socket.inet_ntop(socket.AF_INET6, x[32:48])
	else:
		setTTL = lambda x: sender.setsockopt(socket.SOL_IP, socket.IP_TTL, x)
		isTraceResponse = lambda x: x[20] in {11, 3}
		getIntendedDestination = lambda x: ".".join(str(byte) for byte in x[44:48])

	for ttl in range(config.HOPS):
		setTTL(ttl+1)
		timestamp = time.time()

		try:
			sender.sendto(b'', (host[0], myID))
		except OSError as e:
			ret.append(utils.TraceStep("*", -1))
			continue

		try:
			#Wait for packets sent by this trace
			while True:
				pkt, addr = receiver.recvfrom(1024)
				rtt = time.time() - timestamp

				# If this is a response from a tracer and the tracer sent
				# it to the same place we're sending things, then this
				# packet must belong to us.
				if isTraceResponse(pkt):
					destination = getIntendedDestination(pkt)
					if destination == host.addr and getID(pkt) == myID:
						break

		except socket.timeout:
			ret.append(utils.TraceStep("*", -1)),
			done = False
		else:
			ret.append(utils.TraceStep(addr[0], rtt*1000))
			done = addr[0] == host[0]

		if done:
			break
	receiver.close()
	sender.close()
	return utils.Trace(ret)

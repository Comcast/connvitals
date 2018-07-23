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
import time
from . import utils

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
			# print("timeout")
			done = False
		else:
			ret.append(utils.TraceStep(addr[0], rtt*1000))
			done = addr[0] == host[0]

		if done:
			break
	receiver.close()
	sender.close()
	return utils.Trace(ret)

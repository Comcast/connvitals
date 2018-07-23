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

"""This module defines a single worker to collect stats from a single host"""

import multiprocessing
import math
from . import utils, config, ping, traceroute, ports

class Collector(multiprocessing.Process):
	"""
	A threaded worker that collects stats for a single host.
	"""
	trace = None
	result = [utils.PingResult(-1, -1, -1, -1, 100.),
	          utils.Trace([utils.TraceStep('*', -1)] * 10),
	          utils.ScanResult(None, None, None)]

	def __init__(self, host:str, ID:int, conf:config.Config = config.CONFIG):
		"""
		Initializes the Collector, and its worker pool
		"""
		super(Collector, self).__init__()

		self.hostname = host
		self.conf = conf
		self.host = conf.HOSTS[host]
		self.name = host
		self.ID = ID

		self.pipe = multiprocessing.Pipe()

	def run(self):
		"""
		Called when the thread is run
		"""
		with multiprocessing.pool.ThreadPool() as pool:
			pscan_result, trace_result, ping_result = None, None, None
			if self.conf.PORTSCAN:
				pscan_result = pool.apply_async(ports.portScan,
													 (self.host, pool),
													 error_callback=utils.error)
			if self.conf.TRACE:
				trace_result = pool.apply_async(traceroute.trace,
													 (self.host, self.ID, self.conf),
													 error_callback=utils.error)
			if not self.conf.NOPING:
				try:
					self.ping(pool)
				except (multiprocessing.TimeoutError, ValueError):
					self.result[0] = type(self).result[0]
			else:
				self.result[0] = None

			if self.conf.TRACE:
				try:
					self.result[1] = trace_result.get(self.conf.HOPS)
				except multiprocessing.TimeoutError:
					self.result[1] = type(self).result[1]
			else:
				self.result[1] = None

			if self.conf.PORTSCAN:
				try:
					self.result[2] = pscan_result.get(0.5)
				except multiprocessing.TimeoutError:
					self.result[2] = type(self).result[2]
			else:
				self.result[2] = None

			self.pipe[1].send(self.result)

	def ping(self, pool: multiprocessing.pool.ThreadPool):
		"""
		Pings the host
		"""
		pinger = ping.Pinger(self.host, bytes(self.conf.PAYLOAD))

		# Aggregates round-trip time for each packet in the sequence
		rtt, lost = [], 0

		# Sends, receives and parses all icmp packets asynchronously
		results = pool.map_async(pinger.ping,
		                              range(self.conf.NUMPINGS),
		                              error_callback=utils.error)
		pkts = results.get(8)
		pinger.sock.close()
		del pinger

		for pkt in pkts:
			if pkt != None and pkt > 0:
				rtt.append(pkt*1000)
			else:
				lost += 1

		try:
			avg = sum(rtt) / len(rtt)
			std = 0.
			for item in rtt:
				std += (avg - item)**2
			std /= len(rtt) - 1
			std = math.sqrt(std)
		except ZeroDivisionError:
			std = 0.

		self.result[0] = utils.PingResult(min(rtt), avg, max(rtt), std, lost/self.conf.NUMPINGS *100.0)

	def __str__(self) -> str:
		"""
		Implements 'str(self)'

		Returns a plaintext output result
		"""
		ret = []
		if self.host[0] == self.hostname:
			ret.append(self.hostname)
		else:
			ret.append("%s (%s)" % (self.hostname, self.host[0]))

		pings, trace, scans = self.result

		if pings:
			ret.append(str(pings))
		if trace and trace != self.trace:
			self.trace = trace
			# Dirty hack because I can't inherit with strong typing in Python 3.4
			ret.append(utils.traceToStr(trace))
		if scans:
			ret.append(str(scans))

		return "\n".join(ret)

	def __repr__(self) -> repr:
		"""
		Implements `repr(self)`

		Returns a JSON output result
		"""
		ret = [r'{"addr":"%s"' % self.host[0]]
		ret.append(r'"name":"%s"' % self.hostname)

		if not self.conf.NOPING:
			ret.append(r'"ping":%s' % repr(self.result[0]))

		if self.conf.TRACE and self.trace != self.result[1]:
			self.trace = self.result[1]
			# Dirty hack because I can't inherit with strong typing in Python 3.4
			ret.append(r'"trace":%s' % utils.traceRepr(self.result[1]))

		if self.conf.PORTSCAN:
			ret.append(r'"scan":%s' % repr(self.result[2]))

		return ','.join(ret) + '}'

	def recv(self):
		"""
		Returns a message from the Collector's Pipe
		"""
		return self.pipe[0].recv()

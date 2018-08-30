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
This module defines a class and utilities to manage icmp/icmpv6 echo requests
and replies to remote hosts.
"""

import socket
import struct
import time
import sys
import math
from . import utils
from . import icmp

def icmpParse(pkt: bytes, ipv6: bool) -> int:
	"""
	Parses an icmp packet, returning its sequence number.

	If the packet is found to be not an echo reply, this will
		immediately return -1, indicating that this packet
		should be disregarded.
	"""
	try:
		if ipv6:
			if pkt[0] == 129:
				return struct.unpack("!H", pkt[6:8])[0]
			return -1
		if pkt[20] == 0:
			return struct.unpack("!H", pkt[26:28])[0]
		return -1
	except (IndexError, struct.error):
		return -1

class Pinger():
	"""
	A data structure that handles icmp pings to a remote machine.
	"""
	def __init__(self, host: utils.Host, payload: bytes):
		"""
		Inializes a socket connection to the host on port 22, and returns a Pinger object
		referencing it.
		"""

		self.sock, self.icmpParse, self.mkPkt = None, None, None

		if host.family == socket.AF_INET6:
			self.sock = socket.socket(host.family, socket.SOCK_RAW, proto=socket.IPPROTO_ICMPV6)
			self.icmpParse = self._icmpv6Parse
			self.mkPkt = self._mkPkt6
		else:
			self.sock = socket.socket(host.family, socket.SOCK_RAW, proto=socket.IPPROTO_ICMP)
			self.icmpParse = self._icmpv4Parse
			self.mkPkt = self._mkPkt4

		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

		self.sock.settimeout(1)
		self.payload = payload

		#Build a socket object
		self.host = host

		self.timestamps = {}

	def sendAll(self, num:int) -> utils.PingResult:
		"""
		Sends all pings sequentially in one thread
		"""
		for i in range(num):
			pkt = icmp.ICMPPkt(self.host, payload=struct.pack("!HH", 2, i))
			self.timestamps[i] = time.time()

			try:
				self.sock.sendto(bytes(pkt), (self.host.addr, 0))
			except Exception as e:
				utils.err("Network is unreachable... (%s)" % e)

		return self.recvAll(num)

	def recvAll(self, num:int) -> utils.PingResult:
		"""
		Recieves and parses all packets
		"""
		maxPacketLen, found = 100 + len(self.payload), 0
		pkts = [-1,]*num

		while found < num:

			try:
				pkt, addr = self.sock.recvfrom(maxPacketLen)
			except (socket.timeout, TimeoutError):
				# If we hit a socket timeout, we'll consider the packet dropped
				found += 1
				continue

			if addr[0] == self.host[0]:
				seqno = self.icmpParse(pkt)
				if seqno in range(len(pkts)):
					pkts[seqno] = time.time() - self.timestamps[seqno]
					found += 1

		# All packets collected; parse and return the results
		rtt, lost = [], 0
		for pkt in pkts:
			if pkt > 0:
				rtt.append(pkt*1000)
			else:
				lost += 1

		if lost == num:
			return utils.PingResult(-1, -1, -1, -1, 100.)

		try:
			avg = sum(rtt) / len(rtt)
			std = 0.
			for item in rtt:
				std += (avg - item) ** 2
			std /= len(rtt) - 1
			std = math.sqrt(std)
		except ZeroDivisionError:
			std = 0.

		return utils.PingResult(min(rtt), avg, max(rtt), std, lost/num * 100.0)

	def ping(self, seqno: int) -> float:
		"""
		Sends a single icmp packet to the remote host.
		Returns the round-trip time (in ms) between packet send and receipt
		or 0 if packet was not received.
		"""
		pkt = icmp.ICMPPkt(self.host, payload=struct.pack("!HH", 2, seqno))

		# I set time here so that rtt includes the device latency
		self.timestamps[seqno] = time.time()

		try:
			# ICMP has no notion of port numbers
			self.sock.sendto(bytes(pkt), (self.host.addr, 0))
		except Exception as e:
			#Sometimes, when the network is unreachable this will erroneously report that there's an
			#'invalid argument', which is impossible since the hostnames are coming straight from
			#`socket` itself
			raise Exception("Network is unreachable... (%s)" % e)
		return self.recv()

	@staticmethod
	def _icmpv4Parse(pkt: bytes) -> int:
		"""
		Attemtps to parse an icmpv4 packet, returning the sequence number if parsing succeds,
		or -1 otherwise.
		"""
		try:
			if pkt[20] == 0:
				return struct.unpack("!H", pkt[26:28])[0]
		except (IndexError, struct.error):
			pass
		return -1

	@staticmethod
	def _icmpv6Parse(pkt: bytes) -> int:
		"""
		Attemtps to parse an icmpv6 packet, returning the sequence number if parsing succeds,
		or -1 otherwise.
		"""
		try:
			if pkt[0] == 0x81:
				return struct.unpack("!H", pkt[6:8])[0]
		except (IndexError, struct.error):
			pass
		return -1

	def _mkPkt4(self, seqno: int) -> bytes:
		"""
		Contsructs and returns an ICMPv4 packet
		"""
		header = struct.pack("!BBHHH", 8, 0, 0, 2, seqno)
		checksum = self._checksum4(header + self.payload)
		return struct.pack("!BBHHH", 8, 0, checksum, 2, seqno) + self.payload

	def _mkPkt6(self, seqno: int) -> bytes:
		"""
		Contsructs and returns an ICMPv6 packet
		"""
		header = struct.pack("!BBHHH", 0x80, 0, 0, 2, seqno)
		checksum = self._checksum6(header)
		return struct.pack("!BBHHH", 0x80, 0, checksum, 2, seqno) + self.payload

	@staticmethod
	def _checksum4(pkt: bytes) -> int:
		"""
		calculates and returns the icmpv4 checksum of 'pkt'
		"""

		countTo = len(pkt) // 2 * 2
		total, count = 0, 0

		# Handle bytes in pairs (decoding as short ints)
		loByte, hiByte = 0, 0
		while count < countTo:
			if sys.byteorder == "little":
				loByte = pkt[count]
				hiByte = pkt[count + 1]
			else:
				loByte = pkt[count + 1]
				hiByte = pkt[count]
			total += hiByte * 256 + loByte
			count += 2

		# Handle last byte if applicable (odd-number of bytes)
		# Endianness should be irrelevant in this case
		if countTo < len(pkt): # Check for odd length
			total += pkt[len(pkt) - 1]

		total &= 0xffffffff # Truncate sum to 32 bits (a variance from ping.c, which
		                    # uses signed ints, but overflow is unlikely in ping)

		total = (total >> 16) + (total & 0xffff)    # Add high 16 bits to low 16 bits
		total += (total >> 16)                      # Add carry from above (if any)

		return socket.htons((~total) & 0xffff)

	def _checksum6(self, pkt: bytes) -> int:
		"""
		calculates and returns the icmpv6 checksum of pkt
		"""
		laddr = socket.inet_pton(self.host[1], self.sock.getsockname()[0])
		raddr = socket.inet_pton(*reversed(self.host))
		# IPv6 Pseudo-Header used for checksum calculation as specified by
		# RFC 2460 (https://tools.ieft.org/html/rfc2460)
		psh = laddr + raddr + struct.pack("!I", len(pkt)) + b'\x00\x00\x00:'
		# This last bit is the 4-byte-packed icmp6 protocol number (58 or 0xa3)


		total, packet = 0, psh+pkt

		# Sum all 2-byte words
		num_words = len(packet) // 2
		for chunk in struct.unpack("!%sH" % num_words, packet[0:num_words*2]):
			total += chunk

		# Add any left-over byte (for odd-length packets)
		if len(packet) % 2:
			total += ord(packet[-1]) << 8

		# Fold 32-bits into 16-bits
		total = (total >> 16) + (total & 0xffff)
		total += total >> 16
		return ~total + 0x10000 & 0xffff

	def recv(self) -> float:
		"""
		Recieves each ping sent.
		"""
		# If a packet is not an echo reply, icmpParse will give its seqno as -1
		# This lets us disregard packets from traceroutes immediately
		maxlen = 100+len(self.payload) #this should be enough to cover headers and whatnot

		while True:

			try:
				pkt, addr = self.sock.recvfrom(maxlen)
			except (socket.timeout, TimeoutError):
				return -1

			# The packet must have actually come from the host we pinged
			if addr[0] == self.host[0]:
				seqno = self.icmpParse(pkt)
				if seqno >= 0:
					return time.time() - self.timestamps[seqno]


	def __enter__(self) -> "Pinger":
		"""
		Context-managed instantiation
		"""
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		"""
		Context-managed cleanup
		"""
		self.sock.close()

		if exc_type and exc_value:
			utils.error(exc_type("Unknown error occurred while pinging"))
			utils.error(exc_type(exc_value))
			if traceback:
				utils.warn(traceback)

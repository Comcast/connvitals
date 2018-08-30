"""
This module contains convenience functions for dealing with the ICMP protocol.
Most notably, it contains the `ICMPPkt` class, which can construct an ICMP packet object either
from a simple payload and destination (which will make an 'Echo Request' of the appropriate version)
or from a raw bytestring that is presumably an ICMP packet recived from an external host.
"""

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

import socket
import struct
import enum
from . import utils



# Gets our local IP address, for calculating ICMPv6 checksums
with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
	s.connect(("2001:4998:c:1023::4", 1)) #yahoo.com public IPv6 address
	LADDR = socket.inet_pton(s.family, s.getsockname()[0])

LADDR = LADDR # 'LADDR' is now a global value

# Note that these type code mappings only enumerate the types used by connvitals
class ICMPType(enum.IntEnum):
	"""
	Mapping of ICMP type codes to their names.

	Meant only to be inherited for it's `str` type coercion behaviour, IPv4 and IPv6 have their own,
	more specific Type enumerations.
	"""
	def __str__(self) -> str:
		"""
		Gives the name of the ICMP Type.
		"""
		return self.name.replace('_', ' ')

class ICMPv4Type(ICMPType):
	"""
	Mapping of ICMPv4 type codes to their names.
	"""
	Echo_Reply = 0
	Destination_Unreachable = 3
	Echo_Request = 8
	Time_Exceeded = 11

class ICMPv6Type(ICMPType):
	"""
	Mapping of ICMPv6 type codes to their names.
	"""
	Destination_Unreachable = 1
	Time_Exceeded = 3
	Echo_Request = 128
	Echo_Reply = 129

def ICMPv4_checksum(pkt: bytes) -> int:
	"""
	Implementation of the "Internet Checksum" specified in
	RFC 1071 (https://tools.ieft.org/html/rfc1071)

	Ideally this would act on the string as a series of half-words in host byte order,
	but this works.

	Network data is big-endian, hosts are typically little-endian,
	which makes this much more tedious than it needs to be.
	"""

	from sys import byteorder

	countTo = len(pkt) // 2 * 2
	total, count = 0, 0

	# Handle bytes in pairs (decoding as short ints)
	loByte, hiByte = 0, 0
	while count < countTo:
		if byteorder == "little":
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

def ICMPv6_checksum(pkt: bytes, laddr: bytes, raddr: bytes) -> int:
	"""
	Implementation of the ICMPv6 "Internet Checksum" as specified in
	RFC 1701 (https://tools.ieft.org/html/rfc1701).

	This takes the Payload Length from the IPv6 layer to be 32 (0x20), since we
	don't expect any extension headers and ICMP doesn't carry any length
	information.
		pkt: A complete ICMP packet, with the checksum field set to 0
		laddr: The (fully-expanded) local address of the socket that will send pkt
		raddr: The (fully-expanded) remote address of the host to which the pkt will be sent
		returns: A bytes object representing the checksum
	"""

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
		total += packet[-1] << 8

	# Fold 32-bits into 16-bits
	total = (total >> 16) + (total & 0xffff)
	total += total >> 16
	return ~total + 0x10000 & 0xffff

def ICMP_checksum(pkt: bytes, raddr: bytes = None) -> int:
	"""
	This is an abstraction used to allow calculation of a checksum to be
	agnostic of the protocol version in use.
	"""
	global LADDR
	return ICMPv6_checksum(pkt, LADDR, raddr) if raddr else ICMPv4_checksum(pkt)

class ICMPPkt():
	"""
	This object represents an ICMP packet, with associated convenience functions.
	"""

	fmt = "!BBH4s"
	version = 4 # common default

	def __init__(self, host:utils.Host, pkt:bytes = None, payload:bytes = None):
		"""
		Initializes an ICMP packet, either from raw bytes or a desired host and payload

		If constructed from a host/payload, will set the checksum and construct a 'ping'
		packet.
		"""
		if pkt:
			packetlen = len(pkt)
			if packetlen < 8:
				raise ValueError("Byte string %r too small to be ICMP packet!" % (pkt,))
			elif packetlen > 8:
				utils.warn("ICMP packet may not be valid (has length %d, expected 8)" % (packetlen,))
				pkt = pkt[:8]

			self.outbound = False
			self.Host = host
			Type, self.Code, self.Checksum, self.Payload = struct.unpack(self.fmt, pkt)

			if self.Host.family == socket.AF_INET6:
				self.version = 6
				self.Type = ICMPv6Type(Type)
			else:
				self.Type = ICMPv4Type(Type)

		elif payload:
			self.Host = host
			self.outbound = True
			self.fmt = self.fmt.replace('4', str(4+len(payload)))

			if self.Host[1] == socket.AF_INET6:
				self.version = 6
				self.Type = ICMPv6Type.Echo_Request
			else:
				self.Type = ICMPv4Type.Echo_Request

			self.Code = 0
			self.Payload = payload
			self.Checksum = self.calcChecksum()

		else:
			raise TypeError("ICMPPkt() must be called with a host, and either a packet or payload!")

	def calcChecksum(self) -> int:
		"""
		Calculates the checksum of this ICMP Packet
		"""
		global LADDR

		pkt = struct.pack(self.fmt.replace('H', "2s"), self.Type, self.Code, b'\x00\x00\x00\x00', self.Payload)

		if self.version == 6:

			hostaddr = socket.inet_pton(self.Host.family, self.Host.addr)

			# packet was outbound, proceed as normal
			if self.outbound:
				return ICMP_checksum(pkt, hostaddr)

			# packet was inbound, LADDR and raddr are reversed
			return ICMPv6_checksum(pkt, hostaddr, LADDR)

		return ICMP_checksum(pkt)


	def __bytes__(self) -> bytes:
		"""
		Implements `bytes(self)`

		This builds the packet for sending along a socket.
		"""
		return struct.pack(self.fmt, self.Type, self.Code, self.Checksum, self.Payload)

	def __bool__(self) -> bool:
		"""
		Implements `bool(self)`

		Checks that the `Checksum` attribute matches the calculated checksum.
		"""
		return self.calcChecksum() == self.Checksum

	def __str__(self) -> str:
		"""
		Implements `str(self)`
		"""
		return "%s ICMPv%d packet, bound for %s" % (self.Type, self.version, self.Host.addr)

	def __repr__(self) -> str:
		"""
		Implements `repr(self)`
		"""
		return "ICMPPkt(Type=%r, Code=%d, Payload=%r, Host=%r)" % (self.Type, self.Code, self.Payload, self.Host)

	@property
	def seqno(self) -> int:
		"""
		Gives the sequence number if this is an Echo Request/Reply packet,
		else raises an AttributeError.
		"""
		if self.Type not in {ICMPv6Type.Echo_Reply,
		                     ICMPv6Type.Echo_Request,
		                     ICMPv4Type.Echo_Reply,
		                     ICMPv4Type.Echo_Request}:
			raise AttributeError("Only Echo Requests/Replies have seqno")

		return struct.unpack("!HH", self.Payload)[1]


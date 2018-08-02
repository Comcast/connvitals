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
This module contains functions for scanning some specific hosts for specific
information. Currently has functionality for http(s) servers on ports 80/443
and MySQL servers on port 3306.
"""

import socket
import time
import multiprocessing.pool
import typing
import ssl
from . import utils

class Scanner():
	"""
	Holds persistent information that can be used to repeatedly
	do port scans.
	"""

	# Message constant - so it doesn't need to be re-allocated at runtime.
	HTTP_MSG = b'HEAD / HTTP/1.1\r\nConnection: Keep-Alive\r\nHost: '


	def __init__(self, host:utils.Host):
		"""
		Sets up this scanner, including opening three sockets for
		scanning.
		"""

		self.host = host
		self.HTTP_MSG += self.host.addr.encode() + b'\r\n\r\n'

		# Sets up two TCP sockets, each with a dedicated message
		# buffer - 1 to check the http port, and 1 to check the
		# https port.
		self.buffers = [bytearray(1024), bytearray(1024)]
		self.socks = [
		                 socket.socket(family=host.family),
		                 ssl.wrap_socket(socket.socket(family=host.family), ssl_version=3),
		             ]

		for sock in self.socks:
			sock.settimeout(0.08)


		# When HTTP(S) connections fail, close them immediately. The individual
		# scanners will re-attempt the connection (mysql server connections)
		# shouldn't persist, because there's no mysql 'NOOP' to my knowledge).
		try:
			self.socks[0].connect((self.host.addr, 80))
		except (ConnectionRefusedError, socket.timeout, socket.gaierror):
			utils.warn("Connection Refused by %s on port 80" % self.host.addr)
			self.socks[0].close()

		try:
			self.socks[1].connect((self.host.addr, 443))
		except ssl.SSLError as e:
			utils.warn("SSL handshake with %s failed: %s" % (url[0], e))
			self.socks[1].close()
		except (ConnectionRefusedError, socket.timeout, socket.gaierror):
			utils.warn("Connection Refused by %s on port 443" % self.host.addr)
			self.socks[1].close()


	def __enter__(self) -> 'Scanner':
		"""
		Context-managed `Scanner` object.
		"""

		return self

	def __exit__(self, exc_type, exc_value, traceback):
		"""
		Context-cleanup for `Scanner` object.
		"""
		for sock in self.socks:
			sock.shutdown(socket.SHUT_RDWR)
			sock.close()

		if exc_type and exc_value:
			utils.error("Unknown error occurred (Traceback: %s)" % traceback)
			utils.error(exc_type(exc_value), True)

	def __del__(self):
		"""
		Non-context-managed cleanup.
		"""
		try:
			for sock in self.socks:
				sock.close()
		except AttributeError:
			# Context-management handled the sockets already
			pass


	def scan(self, pool:typing.Union[multiprocessing.pool.Pool, bool] = None) -> utils.ScanResult:
		"""
		Performs a full portscan of the host, and returns a format-able result.

		If the `pool` argument is given, it should be either a usable
		`multiprocessing.pool.Pool` ancestor (i.e. ThreadPool or Pool), or a
		boolean. If `pool` is literally `True`, a new ThreadPool will be
		created to perform the scan.

		If `pool` is `None`, each scan is done sequentially.
		"""
		if pool:
			if pool is True:
				with multiprocessing.pool.ThreadPool(3) as p:
					httpresult = p.apply_async(self.http, ())
					httpsresult = p.apply_async(self.https, ())
					mysqlresult = p.apply_async(self.mysql, ())

					return utils.ScanResult(httpresult.get(), httpsresult.get(), mysqlresult.get())

			httpresult = pool.apply_async(self.http, ())
			httpsresult = pool.apply_async(self.https, ())
			mysqlresult = pool.apply_async(self.mysql, ())

			return utils.ScanResult(httpresult.get(), httpsresult.get(), mysqlresult.get())

		return utils.ScanResult(self.http(), self.https(), self.mysql())

	def http(self) -> typing.Optional[typing.Tuple[float, str, str]]:
		"""
		Checks for http content on port 80.

		This uses a HEAD / HTTP/1.1 request, and returns a tuple containing
		the total latency, the server's status code and reason, and the server's
		name/version (if found in the first kilobyte of data).
		"""

		s = self.socks[0]

		try:
			rtt = time.time()
			s.send(self.HTTP_MSG)
			_ = s.recv_into(self.buffers[0])
			rtt = time.time() - rtt

		except OSError:
			# Possibly the connection was closed; try to re-open.
			try:
				self.socks[0].close()
				self.socks[0] = socket.socket(family=self.host.family)
				self.socks[0].settimeout(0.08)
				self.socks[0].connect((self.host.addr, 80))
				rtt = time.time()
				self.socks[0].send(self.HTTP_MSG)
				_ = self.socks[0].recv_into(self.buffers[0])
				rtt = time.time() - rtt

			except (OSError, socket.gaierror, socket.timeout) as e:
				# If this happens, the server likely went down
				utils.warn("Could not connect to %s:80 - %s" % (self.host.addr, e))
				return None

		except (socket.gaierror, socket.timeout) as e:
			utils.warn("Could not connect to %s:80 - %s" % (self.host.addr, e))
			return None

		if not self.buffers[0]:
			return None

		status = self.buffers[0][9:12].decode()

		try:
			srv = self.buffers[0].index(b'Server: ')
			srv = self.buffers[0][srv+8:self.buffers[0].index(b'\r', srv)].decode()
		except ValueError:
			# Server header not found
			return rtt*1000, status, "Unkown"
		else:
			return rtt*1000, status, srv
		finally:
			# Creating a new buffer is faster than clearing the old one
			self.buffers[0] = bytearray(1024)

	def https(self) -> typing.Optional[typing.Tuple[float, str, str]]:
		"""
		Checks for http content on port 433.

		This uses a HEAD / HTTP/1.1 request, and returns a tuple containing
		the total latency, the server's status code and reason, and the server's
		name/version (if found in the first kilobyte of data).

		Note that this is principally the same as `self.http`, but in the interest
		of favoring time optimization (no conditional branching, fewer dereferences)
		over space optimization the process is repeated nearly verbatim.
		"""

		s = self.socks[1]
		try:
			rtt = time.time()
			s.send(self.HTTP_MSG)
			_ = s.recv_into(self.buffers[1])
			rtt = time.time() - rtt
		except ssl.SSLError as e:
			utils.warn("SSL handshake with %s failed: %s" % (url[0], e))
			return None

		except OSError:
			# Possibly the connection was closed; try to re-open.
			try:
				self.socks[1].close()
				self.socks[1] = ssl.wrap_socket(socket.socket(family=self.host.family), ssl_version=3)
				self.socks[1].settimeout(0.08)
				self.socks[1].connect((self.host.addr, 443))
				rtt = time.time()
				self.socks[1].send(self.HTTP_MSG)
				_ = self.socks[1].recv_into(self.buffers[1])
				rtt = time.time() - rtt
			except ssl.SSLError as e:
				utils.warn("SSL handshake with %s failed: %s" % (url[0], e))
				return None

			except (OSError, socket.gaierror, socket.timeout) as e:
				# If this happens, the server likely went down
				utils.warn("Could not connect to %s:443 - %s" % (self.host.addr, e))
				return None

		except (socket.gaierror, socket.timeout) as e:
			utils.warn("Could not connect to %s:443 - %s" % (self.host.addr, e))
			return None

		if not self.buffers[1]:
			return None

		status = self.buffers[1][9:12].decode()

		try:
			srv = self.buffers[1].index(b'Server: ')
			srv = self.buffers[1][srv+8:self.buffers[1].index(b'\r', srv)].decode()
		except ValueError:
			# Server header not found
			return rtt*1000, status, "Unkown"
		else:
			return rtt*1000, status, srv
		finally:
			# Creating a new buffer is faster than clearing the old one
			self.buffers[1] = bytearray(1024)

	def mysql(self) -> typing.Optional[typing.Tuple[float, str]]:
		"""
		Checks for a MySQL server running on port 3306.

		Returns a tuple containing the total latency and the server version if one is found.
		"""

		with socket.socket(family=self.host.family) as s:

			try:
				rtt = time.time()
				s.connect((self.host.addr, 3306))
				_ = s.recv_into(self.buffers[2])
				ret = sock.recv(1024)

			except (OSError, socket.gaierror, socket.timeout) as e:
				utils.warn("Could not connect to %s:3306 - %s" % (self.host.addr, e))
				return None

		rtt = (time.time() - rtt)*1000
		try:
			return rtt, ret[5:10].decode()
		except UnicodeError:
			utils.warn("Server at %s:3306 doesn't appear to be mysql." % self.host.addr)
			return rtt, "Unknown"


# Functional implementation provided for convenience/legacy support


def http(url: utils.Host, port: int=80) -> typing.Optional[typing.Tuple[float, str, str]]:
	"""
	Checks for http content being served by url on a port passed in ssl.
		(If ssl is 443, wraps the socket with ssl to communicate HTTPS)
	Returns a HEAD request's status code if a server is found, else None
	"""

	# Create socket (wrap for ssl as needed)
	sock = socket.socket(family=url[1])
	if port == 443:
		sock = ssl.wrap_socket(sock, ssl_version=3)
	sock.settimeout(0.08)

	# Send request, and return "None" if anything goes wrong
	try:
		rtt = time.time()
		sock.connect((url[0], port))
		sock.send(b"HEAD / HTTP/1.1\r\n\r\n")
		ret = sock.recv(1000)
		rtt = time.time() - rtt
	except (OSError, ConnectionRefusedError, socket.gaierror, socket.timeout) as e:
		utils.error(Exception("Could not connect to %s: %s" % (url[0], e)))
		return None
	except ssl.SSLError as e:
		utils.warn("SSL handshake with %s failed: %s" % (url[0], e))
		return None
	finally:
		sock.close()

	# Servers that enforce ssl encryption when our socket isn't wrapped - or don't
	# recognize encrypted requests when it is - will sometimes send empty responses
	if not ret:
		return None

	# Check for "Server" header if available.
	# Note - this assumes that both the contents of the "Server" header and the response code are
	# utf8-decodable, which may need to be patched in the future
	try:
		srv = ret.index(b'Server: ')
	except ValueError:
		return rtt*1000, ret[9:12].decode(), "Unkown"
	return rtt*1000, ret[9:12].decode(), ret[srv+8:ret.index(b'\r', srv)].decode()


def mysql(url: utils.Host) -> typing.Optional[typing.Tuple[float, str]]:
	"""
	Checks for a MySQL server running on the host specified by url.
	Returns the server version if one is found, else None.
	"""

	sock = socket.socket(family=url[1])
	sock.settimeout(0.08)
	try:
		rtt = time.time()
		sock.connect((url[0], 3306))
		return (time.time() - rtt)* 1000, sock.recv(1000)[5:10].decode()
	except (UnicodeError, OSError, ConnectionRefusedError, socket.gaierror, socket.timeout) as e:
		utils.error(Exception("Could not connect to %s: %s" % (url[0], e)))
		return None
	finally:
		sock.close()

def portScan(host:utils.Host, pool:multiprocessing.pool.Pool)-> typing.Tuple[str, utils.ScanResult]:
	"""
	Scans a host using a multiprocessing worker pool to see if a specific set of ports are open,
	possibly returning extra information in the case that they are.

	Returns a tuple of (host, information) where host is the ip of the host scanned and information
	is any and all information gathered from each port as a tuple in the order (80, 443).
	If the specified port is not open, its spot in the tuple will contain `None`, but will otherwise
	contain some information related to the port.
	"""

	# Dispatch the workers
	hypertext = pool.apply_async(http, (host,))
	https = pool.apply_async(http, (host, 443))
	mysqlserver = pool.apply_async(mysql, (host,))

	# Collect and return
	return utils.ScanResult(hypertext.get(), https.get(), mysqlserver.get())

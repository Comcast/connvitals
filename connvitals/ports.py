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

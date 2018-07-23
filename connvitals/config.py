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
This module defines the config options for the 'connvitals' command
"""

import socket
from . import __version__, utils

# Configuration values

class Config():
	"""
	Represents a configuration.
	"""

	def __init__(self,*,HOPS     = 30,
	                    JSON     = False,
	                    PAYLOAD  = b'The very model of a modern Major General.',
	                    TRACE    = False,
	                    NOPING   = False,
	                    PORTSCAN = False,
	                    NUMPINGS = 10,
	                    HOSTS    = None):
		"""
		Initializes a configuration
		"""
		self.HOPS     = HOPS
		self.JSON     = JSON
		self.PAYLOAD  = PAYLOAD
		self.TRACE    = TRACE
		self.NOPING   = NOPING
		self.PORTSCAN = PORTSCAN
		self.NUMPINGS = NUMPINGS
		self.HOSTS    = HOSTS if HOSTS is not None else {}

CONFIG = None

def init():
	"""
	Initializes the configuration.
	"""
	global __version__, CONFIG

	from argparse import ArgumentParser as Parser
	parser = Parser(description="A utility to check connection vitals with a remote host.",
	              epilog="'host' can be an ipv4 or ipv6 address, or a fully-qualified domain name.")

	parser.add_argument("hosts",
	                    help="The host or hosts to check connection to. "\
	                         "These can be ipv4 addresses, ipv6 addresses, fqdn's, "\
	                         "or any combination thereof.",
	                    nargs="*")

	parser.add_argument("-H", "--hops",
	                    dest="hops",
	                    help="Sets max hops for route tracing (default 30).",
	                    default=30,
	                    type=int)

	parser.add_argument("-p", "--pings",
	                    dest="numpings",
	                    help="Sets the number of pings to use for aggregate statistics (default 10).",
	                    default=10,
	                    type=int)

	parser.add_argument("-P", "--no-ping",
	                    dest="noping",
	                    help="Don't run ping tests.",
	                    action="store_true")

	parser.add_argument("-t", "--trace",
	                    dest="trace",
	                    help="Run route tracing.",
	                    action="store_true")

	parser.add_argument("-s", "--port-scan",
	                    dest="portscan",
	                    help="Scan the host(s)'s ports for commonly-used services",
	                    action="store_true")

	parser.add_argument("--payload-size",
	                    dest="payload",
	                    help="Sets the size (in B) of ping packet payloads (default 41).",
	                    default=b'The very model of a modern Major General.',
	                    type=int)

	parser.add_argument("-j", "--json",
	                    dest="json",
	                    help="Outputs in machine-readable JSON (no newlines)",
	                    action="store_true")

	parser.add_argument("-V", "--version",
	                    dest="version",
	                    help="Print the program's version, then exit.",
	                    action="store_true")

	args = parser.parse_args()

	if args.version:
		print("python3-connvitals Version %s" % __version__)
		exit(0)

	# Before doing anything else, make sure we have permission to open raw sockets
	try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, proto=1)
		sock.close()
		del sock
	except PermissionError:
		from sys import argv
		utils.error(PermissionError("You do not have the permissions necessary to run %s" % (argv[0],)))
		utils.error("(Hint: try running as root, with `capsh` or with `sudo`)", True)

	CONFIG = Config(HOPS     = args.hops,
	                JSON     = args.json,
	                PAYLOAD  = args.payload,
	                TRACE    = args.trace,
	                NOPING   = args.noping,
	                PORTSCAN = args.portscan,
	                NUMPINGS = args.numpings)

	# Parse the list of hosts and try to find valid addresses for each
	CONFIG.HOSTS = {}

	for host in args.hosts:
		info = utils.getaddr(host)
		if not info:
			utils.error("Unable to resolve host ( %s )" % host)
		else:
			CONFIG.HOSTS[host] = info

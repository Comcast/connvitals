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
A utility to check connection vitals with a remote host.

	Usage: connvitals [ -h --help ] [ -H --hops HOPS ] [ -p --pings PINGS ] [ -P --no-ping ]
	                  [ -t --trace ] [ --payload-size PAYLOAD ] [ --port-scan ] [ -j --json ]
	                  host [hosts... ]

Each 'host' can be an ipv4 address, ipv6 address, or a fully-qualified domain name.

Submodules:
	utils:      Contains utility functionality such as error/warning reporting and host address parsing
	ping:       Groups functionality related to ICMP/ICMPv6 tests
	traceroute: Contains a function for tracing a route to a host
	ports:      Specifies functions for checking specific host ports for http(s) and MySQL servers

"""
import socket

__version__ = "4.0.2"
__author__ = "Brennan Fieck"

def main() -> int:
	"""
	Runs the utility with the arguments specified on sys.argv.
	Returns: Always 0 to indicate "Success", unless the utility terminates
		prematurely with a fatal error.
	"""

	# Before doing anything else, make sure we have permission to open raw sockets
	try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, proto=1)
		sock.close()
		del sock
	except PermissionError:
		from .utils import error
		from sys import argv
		error(PermissionError("You do not have the permissions necessary to run %s" % (argv[0],)))
		error("(Hint: try running as root or with `sudo`)", True)

	from . import utils
	from . import config
	from . import collector

	config.init()

	# No hosts could be parsed
	if not config.HOSTS:
		utils.error("No hosts could be parsed! Exiting...", True)

	collectors = [collector.Collector(host) for host in config.HOSTS]

	# Start all the collectors
	for collect in collectors:
		collect.start()

	# Wait for every collector to finish
	# Print JSON if requested
	if config.JSON:
		for collect in collectors:
			_ = collect.join()
			collect.result = collect.recv()
			print(repr(collect))

	# ... else print plaintext
	else:
		for collect in collectors:
			_ = collect.join()
			collect.result = collect.recv()
			print(collect)


	# Errors will be indicated on stdout; because we query multiple hosts, as
	# long as the main routine doesn't crash, we have exited successfully.
	return 0

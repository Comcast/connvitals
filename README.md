# connvitals

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Checks a machines connection to a specific host or list of hosts in terms of packet loss, icmp latency, routing, and anything else that winds up getting added.

*Note: Does not recognize duplicate hosts passed via `argv`, and will test all of them as though unique.*

*Note: Under normal execution conditions, requires super-user permissions to run.*

## Dependencies
The utility was built using Go, and binaries should work without dependencies.
Building requires the getopt/v2, x/net/icmp, x/net/ipv6 and x/net/ipv4 libraries, which can in most cases be downloaded with:
```bash
go get golang.org/x/net/icmp
go get golang.org/x/net/ipv4
go get golang.org/x/net/ipv6
go get github.com/pborman/getopt/v2
```

## Usage
```bash
connvitals [ -h --help ] [ -V --version ] [ -H --hops HOPS ] [ -p --pings PINGS ] [ -P --no-ping ] [ -t --trace ] [ --payload-size PAYLOAD ] [ --port-scan ] [ -j --json ] host [ hosts... ]
```

* `hosts` - A list of one or more hosts to check connection to. They can be ipv4 addresses, ipv6 addresses, fqdn's or any combination thereof.
* `-h` or `--help` - Prints help text, then exits successfully.
* `-V` or `--version` - Prints the program's version information, then exits successfully.
* `-H` or `--hops` - Sets max hops for route tracing (default 30).
* `-p` or `--pings` - Sets the number of pings to use for aggregate statistics (default 4).
* `-P` or `--no-ping` - Don't run ping tests.
* `-t` or `--trace` - Run route tracing.
* `-j` or `--json` - Print output a single line in JSON format.
* `--payload-size` - Sets the size (in B) of ping packet payloads (default 41).
* `--port-scan` - Perform a limited scan on each hosts' ports.

### Output Format

#### Normal Output
For each host tested, results are printed in the newline-separated order "host->Ping Results->Route Trace Results->Port Scan Results" where "host" is the name of the host, as passed on argv. If the name passed for a host on `argv` is not what ends up being used to test connection vitals (e.g. the program may translate `google.com` into `216.58.218.206`), then the "host" line will contain `host-as-typed (host IP used)`.

Ping tests output their results as a tab-separated list containing - in this order - minimum round-trip time in milliseconds (rtt), mean rtt, maximum rtt, rtt standard deviation, and packet loss in percent. If all packets are lost, the min/mean/max/std are all reported as -1.

Route traces output their results as a list of network hops, separated from each other by newlines. Each network hop is itself a tab-separated list of data containing - in this order - a network address for the machine this hop ended at, and the rtt of a packet traversing this route. If the packet was lost, a star (`*`) is shown instead of an address and rtt.

Port scans check for http(s) servers on ports 80 and 443, and MySQL servers running on port 3306. It outputs its results as a tab-separated list containing - in this order - port 80 results, port 443 results, port 3306 results. Results for ports 80 and 443 consist of sending a `HEAD / HTTP/1.1` request and recording "rtt (in milliseconds), response code, server" from the server's response. "server" will be the contents of the "Server" header if found within the first kilobyte of the response, but if it is not found will simply be "Unknown". Port 3306 results report the version of the MySQL server listening on that port if one is found (Note that this version number may be mangled if the server allows unauthenticated connection or supports some other automatic authentication mechanism for the machine running connvitals). If a server is not found on a port, its results are reported as "None", indicating no listening server. If a server on port 80 expects encryption or a server on port 443 does not expect encryption, they will be "erroneously" reported as not existing.

example output:
```bash
root@hostname / # connvitals -t --port-scan google.com 127.0.0.1 2607:f8b0:400f:807::200e
google.com (172.217.3.14)
5.696	14.684	20.647	3.641	0.000
10.169.240.1	5.689
10.168.253.8	10.870
10.168.254.252	9.621
10.168.255.226	2.238
198.178.8.94	3.038
69.241.22.33	3.790
68.86.103.13	4.332
68.86.92.121	6.097
68.86.86.77	5.397
68.86.83.6	7.255
173.167.58.142	10.740
*
216.239.49.247	3.886
172.217.3.14	4.132
64.778, 200, gws	65.069, 200, gws	None
127.0.0.1
0.847	2.378	3.701	0.654	0.000
127.0.0.1	0.931
None	None	2.073, 5.7.2
2607:f8b0:400f:807::200e
6.031	12.674	19.786	3.638	0.000
2001:558:1418:49::1	11.922
2001:558:3da:74::1	9.625
2001:558:3da:6f::1	2.740
2001:558:3da:1::2	2.221
2001:558:3c2:15::1	3.993
2001:558:fe1c:6::1	5.599
2001:558:1c0:65::1	3.877
2001:558:0:f71e::1	7.185
*
2001:558:0:f8c1::2	3.977
2001:559::10c6	4.074
*
2001:4860:0:1::10ad	3.773
2607:f8b0:400f:807::200e	3.631
66.074, 200, gws	73.950, 200, gws	None
```

#### JSON Output Format
The JSON output format option (`-j` or `--json`) will render the output on one line. Each host is represented as an object, indexed by its **address**. This is not necessarily the same as the host as given on the command line, which may be found as an attribute of the host, named `'name'`.
Results for ping tests are a dictionary attribute named `'ping'`, with floating point values labeled as `'min'`, `'avg'`, `'max'`, `'std'` and `'loss'`. As with all floating point numbers in json output, these values are **not rounded or truncated** and are printed exactly as calculated, to the greatest degree of precision afforded by the system.
Route traces are output as a list attribute, labeled `'route'`, where each each step in the route is itself a list. The first element in each list is either the address of the discovered host at that point in the route, or the special string `'*'` which indicates the packet was lost and no host was discovered at this point. The second element, if it exists, is a floating point number giving the round-trip-time of the packet sent at this step, in milliseconds. Once again, unlike normal output format, these floating point numbers **are not rounded or truncated** and are printed exactly as calculated, to the greatest degree of precision afforded by the system.
Port scans are represented as a dictionary attribute named `'scan'`. The label of each element of `'scan'` is the name of the server checked for. `'http'` and `'https'` results will report a dictionary of values containing:
	* `'rtt'` - the time taken for the server to respond
	* `'response code'` - The decimal representation of the server's response code to a `HEAD / HTML/1.1` request.
	* `'server'` - the name of the server, if found within the first kilobyte of the server's response, otherwise "Unknown".
`'mysql'` fields will also contain a dictionary of values, and that dictionary should also contain the `'rtt'` field with the same meaning as for `'http'` and `'https'`, but will replace the other two fields used by those protocols with `'version'`, which will give the version number of the MySQL server.
If any of these three server types is not detected, the value of its label will be the string 'None', rather than a dictionary of values.

Example JSON Output (with localhost running mysql server):
```bash
root@hostname / # sudo connvitals -j --port-scan -tp 100 google.com 2607:f8b0:400f:807::200e localhost
```
```json
{"addr":"172.217.3.14","name":"google.com","ping":{"min": 3.525257110595703, "avg": 4.422152042388916, "max": 5.756855010986328, "std": 0.47761748430602524, "loss": 0.0},"route":[["*"], ["10.168.253.8", 2.187013626098633], ["10.168.254.252", 4.266977310180664], ["10.168.255.226", 3.283977508544922], ["198.178.8.94", 2.7751922607421875], ["69.241.22.33", 3.7970542907714844], ["68.86.103.13", 3.8001537322998047], ["68.86.92.121", 7.291316986083984], ["68.86.86.77", 5.874156951904297], ["68.86.83.6", 4.465818405151367], ["173.167.58.142", 4.443883895874023], ["*"], ["216.239.49.231", 4.090785980224609], ["172.217.3.14", 4.895925521850586]],"scan":{"http": {"rtt": 59.095, "response code": "200", "server": "gws"}, "https": {"rtt": 98.238, "response code": "200", "server": "gws"}, "mysql": "None"}}}
{"addr":"2607:f8b0:400f:807::200e","name":"2607:f8b0:400f:807::200e","ping":{"min": 3.62396240234375, "avg": 6.465864181518555, "max": 24.2769718170166, "std": 5.133322111766303, "loss": 0.0},"route":[["*"], ["2001:558:3da:74::1", 1.9710063934326172], ["2001:558:3da:6f::1", 2.904176712036133], ["2001:558:3da:1::2", 2.5751590728759766], ["2001:558:3c2:15::1", 2.7141571044921875], ["2001:558:fe1c:6::1", 4.7512054443359375], ["2001:558:1c0:65::1", 3.927946090698242], ["*"], ["*"], ["2001:558:0:f8c1::2", 3.635406494140625], ["2001:559:0:18::2", 3.8270950317382812], ["*"], ["2001:4860:0:1::10ad", 4.517078399658203], ["2607:f8b0:400f:807::200e", 3.91387939453125]],"scan":{"http": {"rtt": 51.335, "response code": "200", "server": "gws"}, "https": {"rtt": 70.521, "response code": "200", "server": "gws"}, "mysql": "None"}}}
"addr":"127.0.0.1","name":"localhost","ping":{"min": 0.04792213439941406, "avg": 0.29621124267578125, "max": 0.5612373352050781, "std": 0.0995351687014057, "loss": 0.0},"route":[["127.0.0.1", 1.9199848175048828]],"scan":{"http": "None", "https": "None", "mysql": {"rtt": 0.148, "version": "5.7.2"}}}

```

#### Error Output Format
When an error occurs, it is printed to `stderr` in the following format:
```
EE: <Error Type>: <Error Description>:	-	<Timestamp>
```
`EE: ` is prepended for ease of readability in the common case that stdout and stderr are being read/parsed from the same place. `<Error Type>` is commonly just `str` or `Exception`, but can in some cases represent more specific error types. `<Error Description>` holds extra information describing why the error occurred. Note that stack traces are not commonly logged, and only occur when the program crashes for unforseen reasons. `<Timestamp>` is the time at which the error occurred, given in the system's `ctime` format, which will usually look like `Mon Jan 1 12:59:59 2018`.

Some errors do not affect execution in a large scope, and are logged to `stderr` as warnings in the following format:
```
WW: <Warning> -	<Timestamp>
```
where `WW: ` is printed both for ease of readability and to distinguish warnings from errors, `<Warning>` is the warning message, and `<Timestamp>` is the time at which the warning was issued, given in the system's `ctime` format.

In the case that `stderr` is a tty, `connvitals` will print errors in red, and warnings in yellow using ANSI control sequences (currently supports most Linux/Unix distributions).

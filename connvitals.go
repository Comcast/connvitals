package main

// Copyright 2018 Comcast Cable Communications Management, LLC

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

// http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import "fmt"
import "connvitals/ping"
import "connvitals/traceroute"
import "connvitals/ports"
import "sync"
import "github.com/pborman/getopt/v2"
import "net"
import "connvitals/utils"
import "bytes"
import "os"

// Constants
const IP4LEN = 4;
const IP6LEN = 16;
const SOFTWARE_VERSION = "3.0.0";

//Holds results until the end of execution
var pingResults map[*net.IPAddr]string = make(map[*net.IPAddr]string);
var traceResults map[*net.IPAddr]string = make(map[*net.IPAddr]string);
var scanResults map[*net.IPAddr]string = make(map[*net.IPAddr]string);

// Concurrency locks
var pinglock = sync.RWMutex{};
var tracelock = sync.RWMutex{};
var scanlock = sync.RWMutex{};

/*
	Thread-safe function to write a ping result to the results map.
*/
func writePingResult(host *net.IPAddr, res string) {
	pinglock.Lock();
	defer pinglock.Unlock();
	pingResults[host] = res;
}

/*
	Thread-safe function to write a route trace result to the results map.
*/
func writeRoute(host *net.IPAddr, res string) {
	tracelock.Lock();
	defer tracelock.Unlock();
	traceResults[host] = res;
}

/*
	Thread-safe function to write a ping result to the results map.
*/
func writeScan(host *net.IPAddr, res string) {
	scanlock.Lock();
	defer scanlock.Unlock();
	scanResults[host] = res;
}

func main() {

	MAX_HOPS := getopt.IntLong("hops", 'H', 30, "Sets max hops for route tracing (default 30).");
	HELP := getopt.BoolLong("help", 'h', "Prints help text and exits.");
	NUMPINGS := getopt.IntLong("pings", 'p', 10, "Sets the number of pings to use for aggregate statistics (default 10).");
	NOPINGS := getopt.BoolLong("no-ping", 'P', "Don't run ping tests.");
	TRACE := getopt.BoolLong("trace", 't', "Run route tracing.");
	JSON := getopt.BoolLong("json", 'j', "Print output as one line of JSON formatted information.")
	PAYLOAD := getopt.IntLong("payload-size", 0, 41, "Sets the size (in B) of ping packet payloads (default 41).");
	PORTSCAN := getopt.BoolLong("port-scan", 's', "Perform a limited scan on each host's ports.")
	VERSION := getopt.BoolLong("version", 'V', "Print the version information, then exit.")
	getopt.Parse();

	if *VERSION {
		fmt.Printf("connvitals Version %s\n", SOFTWARE_VERSION);
		os.Exit(0);
	} else if *HELP {
		getopt.Usage();
		os.Exit(0);
	}

	args := getopt.Args();
	if len(args) < 1 {
		getopt.Usage();
		os.Exit(1);
	}


	//Holds the original names of hosts, for easier identification in output
	hostnames := make(map[*net.IPAddr]string);

	// Multiprocessing worker pool
	var pool sync.WaitGroup;

	for arg := range args {

		// Parse the host for an IP Address
		var host string = args[arg];
		targetIP, err := net.ResolveIPAddr("ip", host);
		if err != nil {
			utils.Error(utils.GenericError{"Host '"+host+"' could not be resolved"}, 0);
			continue;
		}


		// Determine if IP is ipv4 or ipv6
		var IPv6 bool;
		if len(targetIP.IP.To4()) == IP4LEN {
			IPv6 = false;
		} else if len(targetIP.IP) == IP6LEN {
			IPv6 = true;
		} else {
			utils.Error(utils.GenericError{"Host '"+host+"' could not be resolved"}, 0);
			continue;
		}


		//Store the user-specified name of this host
		hostnames[targetIP] = host;

		// Asynchronously ping this host
		if ! *NOPINGS {
			pool.Add(1);
			go func () {
				defer pool.Done();
				min, avg, max, std, loss, err := ping.PingHost(targetIP, IPv6, *NUMPINGS, *PAYLOAD);
				if err != nil {
					utils.Error(err, 0);
				}

				var format string;

				// create json-ified text if necessary...
				if *JSON {
					format = "{\"min\":%f,\"avg\":%f,\"max\":%f,\"std\":%f,\"loss\":%f}";

				// ...otherwise just format the results
				} else {
					format = "%.3f\t%.3f\t%.3f\t%.3f\t%.3f";
				}

				writePingResult(targetIP, fmt.Sprintf(format, min, avg, max, std, loss));
			}();
		}


		if *TRACE {
			pool.Add(1);
			go func() {
				defer pool.Done();
				tracer, err := traceroute.New(targetIP, *MAX_HOPS, IPv6);
				if err != nil {
					utils.Error(err, 0);
					return;
				}

				result, err := tracer.Run();
				if err != nil {
					utils.Error(err, 0);
				}

				var buffer bytes.Buffer;

				// create json-ified text if necessary...
				if *JSON {
					buffer.WriteRune('[');
					buffer.WriteString(result[0].JSON());
					for step := range result[1:] {
						buffer.WriteRune(',');
						buffer.WriteString(result[step+1].JSON());
					}
					buffer.WriteRune(']');

				// ...otherwise just format the results
				} else {
					buffer.WriteString(result[0].String());
					for step := range result[1:] {
						buffer.WriteRune('\n');
						buffer.WriteString(result[step+1].String());
					}
				}

				writeRoute(targetIP, buffer.String());
			}();
		}

		if *PORTSCAN {
			pool.Add(1);
			go func () {
				defer pool.Done();
				httpScanResult, httpsScanResult, mysqlScanResult := ports.Scan(targetIP.String(), IPv6);

				var buffer bytes.Buffer;

				// create json-ified text if necessary...
				if *JSON {
					buffer.WriteString("{\"http\":");
					buffer.WriteString(httpScanResult.JSON());
					buffer.WriteString(",\"https\":");
					buffer.WriteString(httpsScanResult.JSON());
					buffer.WriteString(",\"mysql\":");
					buffer.WriteString(mysqlScanResult.JSON());
					buffer.WriteRune('}');

				// ...otherwise just format the results
				} else {
					buffer.WriteString(httpScanResult.String());
					buffer.WriteRune('\t');
					buffer.WriteString(httpsScanResult.String());
					buffer.WriteRune('\t');
					buffer.WriteString(mysqlScanResult.String());
				}
				writeScan(targetIP, buffer.String());
			}();
		}
	}

	pool.Wait();

	utils.Print(*JSON, hostnames, pingResults, traceResults, scanResults);

	// // Print results
	// for key, value := range hostnames {
	// 	if key.String() == value {
	// 		fmt.Println(key.String());
	// 	} else {
	// 		fmt.Printf("%s (%s)\n", value, key.String());
	// 	}
	// 	if ! *NOPINGS && len(pingResults[key]) > 0 {
	// 		fmt.Print(pingResults[key]);
	// 	}
	// 	if *TRACE && len(traceResults[key]) > 0 {
	// 		fmt.Print(traceResults[key]);
	// 	}
	// 	if *PORTSCAN && len(scanResults[key]) > 0 {
	// 		fmt.Println(scanResults[key]);
	// 	}
	// }
}

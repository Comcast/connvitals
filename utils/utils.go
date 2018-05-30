package utils

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
import "os"
import "time"
import "bytes"
import "net"
import "syscall"
import "unsafe"
import "runtime"

////////////////////////////////////////////////////////
//                Route Trace Objects                 //
////////////////////////////////////////////////////////

/*
	A type that holds information about a specific step in a route trace
*/
type Step struct {
	Host string;
	RTT float64;
};

/*
	Returns a Step object's representation in JSON format
*/
func (step Step) JSON() string {
	if step.RTT < 0 || step.Host == "*" {
		return "[\"*\"]";
	}
	return fmt.Sprintf("[\"%s\", %f]", step.Host, step.RTT);
}

/*
	Returns a Step objects representation as a tab-separated list
*/
func (step Step) String() string {
	if step.RTT < 0 || step.Host == "*" {
		return "*";
	}
	return fmt.Sprintf("%s\t%.3f", step.Host, step.RTT);
}


////////////////////////////////////////////////////////
//                 Port Scan Objects                  //
////////////////////////////////////////////////////////

/*
	A type that represents the information gathered during an http(s) port scan
*/
type HttpScanResult struct {
	RTT float64;
	Response string;
	Server string;
};

/*
	Returns an HttpScanResult object's representation in JSON format
*/
func (res HttpScanResult) JSON() string {
	if res.RTT < 0 || (res.Response == "" && res.Server == "") {
		return "\"None\"";
	}
	return fmt.Sprintf("{\"rtt\":%f,\"response code\":\"%s\",\"server\":\"%s\"}", res.RTT, res.Response, res.Server);
}

/*
	Returns an HttpScanResult object's representation as a delimited list
*/
func (res HttpScanResult) String() string {
	if res.RTT < 0 || (res.Response == "" && res.Server == "") {
		return "None";
	}
	return fmt.Sprintf("%.3f, %s, %s", res.RTT, res.Response, res.Server);
}

/*
	A type that represents the information gathered during a mysql port scan
*/
type MysqlScanResult struct {
	RTT float64;
	Version string;
};

/*
	Returns the JSON representation of a MysqlScanResult object
*/
func (res MysqlScanResult) JSON() string {
	if res.RTT < 0 || res.Version == "" {
		return "\"None\"";
	}
	return fmt.Sprintf("{\"rtt\":%f,\"version\":\"%s\"}", res.RTT, res.Version);
}

/*
	Returns the delimited, string representation of a MysqlScanResult object
*/
func (res MysqlScanResult) String() string {
	if res.RTT < 0 || res.Version == "" {
		return "None";
	}
	return fmt.Sprintf("%.3f, %s", res.RTT, res.Version);
}


////////////////////////////////////////////////////////
//                 Printing/Logging                   //
////////////////////////////////////////////////////////

/*
	Prints results, in either JSON or plaintext format, as specified by `json`
*/
func Print(json bool, hostnames, pingResults, traceResults, scanResults map[*net.IPAddr]string) {
	var output_buffer bytes.Buffer;

	if json {
		for addr, name := range hostnames {
			output_buffer.WriteString("{\"addr\":\"");
			var wrotePings, wroteRoutes bool;
			output_buffer.WriteString(addr.String());
			output_buffer.WriteString("\",\"name\":\"");
			output_buffer.WriteString(name);
			output_buffer.WriteString("\",");
			if pingResult, resultsRecorded := pingResults[addr]; resultsRecorded {
				output_buffer.WriteString("\"ping\":");
				output_buffer.WriteString(pingResult);
				wrotePings = true;
			}

			if traceResult, resultsRecorded := traceResults[addr]; resultsRecorded {
				if wrotePings {
					output_buffer.WriteRune(',');
				}
				output_buffer.WriteString("\"trace\":");
				output_buffer.WriteString(traceResult);
				wroteRoutes = true;
			}

			if scanResult, resultsRecorded := scanResults[addr]; resultsRecorded {
				if wrotePings || wroteRoutes {
					output_buffer.WriteRune(',');
				}
				output_buffer.WriteString("\"scan\":");
				output_buffer.WriteString(scanResult);
			}
			output_buffer.WriteRune('}');
			fmt.Println(output_buffer.String());
			output_buffer.Reset();
		}


	} else {
		for addr, name := range hostnames {
			if addr.String() == name {
				fmt.Println(addr.String());
			} else {
				fmt.Printf("%s (%s)\n", name, addr.String());
			}
			if pingResult, resultsRecorded := pingResults[addr]; resultsRecorded {
				fmt.Println(pingResult);
			}
			if traceResult, resultsRecorded := traceResults[addr]; resultsRecorded {
				fmt.Println(traceResult);
			}
			if scanResult, resultsRecorded := scanResults[addr]; resultsRecorded {
				fmt.Println(scanResult);
			}
		}
	}
}


func isatty(fd uintptr) bool {
	var termios syscall.Termios;
	var call uintptr;

	switch runtime.GOOS {
		case "linux":
			call = 0x5401;
		case "freebsd":
			fallthrough;
		case "openbsd":
			fallthrough;
		case "netbsd":
			fallthrough;
		case "dragonfly":
			fallthrough;
		case "darwin":
			call = 0x40487413;
		default:
			return false;
	}

	_, _, err := syscall.Syscall6(syscall.SYS_IOCTL, fd, call, uintptr(unsafe.Pointer(&termios)), 0, 0, 0);
	return err == 0;
}

/*
	Prints a warning and timestamp to stderr
*/
func Warn(warning string) {
	printstr := "WW: %s -\t%s\n";

	if isatty(os.Stderr.Fd()) {
		printstr = "\033[38;2;238;216;78m" + printstr + "\033[m";
	}
	fmt.Fprintf(os.Stderr, "WW: %s -\t%s\n", warning, time.Now().Format(time.UnixDate));
}

/*
	Generic Error type to aid error construction.
*/
type GenericError struct {
	Msg string;
};

/*
	Returns the error message as a string
	(Necessary to implement the `error` interface)
*/
func (err GenericError) Error() string {
	return err.Msg;
}

/*
	Prints an error and associated information to stderr, and exits with the exit code indicated by fatal if fatal is non-zero
*/
func Error(err interface{ Error() string}, fatal int) {
	printstr := "EE: %T: %s -\t%s\n";

	if isatty(os.Stderr.Fd()) {
		printstr = "\033[38;2;255;0;0m" + printstr + "\033[m";
	}

	fmt.Fprintf(os.Stderr, printstr, err, err.Error(), time.Now().Format(time.UnixDate));
	if fatal != 0 {
		os.Exit(fatal);
	}
}

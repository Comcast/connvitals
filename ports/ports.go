package ports

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

import "net"
import "connvitals/utils"
import "time"
import "sync"
import "crypto/tls"
import "bytes"



var request []byte = []byte("HEAD / HTTP/1.1\r\n\r\n");
const ms = float64(time.Millisecond);
/*
	Attempts to connect to a host specified by "host" and return a result of the form:
		Response Code, Server Info
	where Response Code is the code of a response to a "HEAD / HTTP/1.1" request and
	Server Info is the contents of the "Server: " header if present, or "Unkown" otherwise.
	If anything goes wrong, it will instead return "None".
*/
func http(host string) utils.HttpScanResult {
	// Create socket
	conn, err := net.DialTimeout("tcp", host+":http", 25 * time.Millisecond);
	if err != nil {
		return  utils.HttpScanResult{-1, "", ""};
	}
	defer conn.Close();

	// Set timestamp
	ts := time.Now();

	// Set socket "timeout"
	err = conn.SetDeadline(ts.Add(100 * time.Millisecond));
	if err != nil {
		return utils.HttpScanResult{-1, "", ""}; // I have no idea why this would happen, unless the fd gets closed for some reason
	}

	// Immediately send request
	_, err = conn.Write(request);
	if err != nil {
		return utils.HttpScanResult{-1, "", ""};
	}

	buff := make([]byte, 1000);
	_, err = conn.Read(buff);
	if err != nil {
		return utils.HttpScanResult{-1, "", ""};
	}

	var srv string = "Unkown";
	if srvHeader := bytes.Index(buff, []byte("Server: ")); srvHeader > 0 {
		srvEnd := bytes.Index(buff[srvHeader+8:], []byte("\r\n"))
		srv = string(buff[srvHeader+8:srvHeader+8+srvEnd]);
	}

	return utils.HttpScanResult{float64(time.Since(ts))/ms, string(buff[9:12]), srv};

}

/*
	Attempts to connect via TLS to a host specified by "host" and return a result of the form:
		Response Code, Server Info
	where Response Code is the code of a response to a "HEAD / HTTP/1.1" request and
	Server Info is the contents of the "Server: " header if present or "Unkown" otherwise.
	If anything goes wrong, it will instead return "None".
*/
func https(host string) utils.HttpScanResult {
	conn, err := tls.Dial("tcp", host+":https", &tls.Config{InsecureSkipVerify: true});
	if err != nil {
		return  utils.HttpScanResult{-1, "", ""};
	}

	ts := time.Now();
	err = conn.SetDeadline(ts.Add(100 * time.Millisecond));
	if err != nil {
		return  utils.HttpScanResult{-1, "", ""};
	}

	_, err = conn.Write(request);
	if err != nil {
		return  utils.HttpScanResult{-1, "", ""};
	}

	buff := make([]byte, 1000);
	_, err = conn.Read(buff);
	if err != nil {
		return  utils.HttpScanResult{-1, "", ""};
	}

	var srv string = "Unkown";
	if srvHeader := bytes.Index(buff, []byte("Server: ")); srvHeader > 0 {
		srvEnd := bytes.Index(buff[srvHeader+8:], []byte("\r\n"))
		srv = string(buff[srvHeader+8:srvHeader+8+srvEnd]);
	}

	return utils.HttpScanResult{float64(time.Since(ts))/ms, string(buff[9:12]), srv};
}

/*
	Attempts to connect to a host specified by "host" and return the version of a
	MySQL server listening on port 3306 if one can be found. Will otherwise return
	"None".
*/
func mysql(host string) utils.MysqlScanResult {
	conn, err := net.DialTimeout("tcp", host+":3306", 25 * time.Millisecond);
	if err != nil {
		return utils.MysqlScanResult{-1, ""};
	}

	ts := time.Now();
	err = conn.SetDeadline(ts.Add(10 * time.Millisecond));
	if err != nil {
		return utils.MysqlScanResult{-1, ""};
	}

	buff := make([]byte, 1000);
	_, err = conn.Read(buff);
	if err != nil {
		return utils.MysqlScanResult{-1, ""};
	}

	return utils.MysqlScanResult{float64(time.Since(ts))/ms, string(buff[5:10])};
}

/*
	Scans the ports of the host specified by "host" for http(s) and MySQL servers
	returns a result that is the concatenation of the results of tests for each server type.
*/
func Scan(host string, IPv6 bool) (utils.HttpScanResult, utils.HttpScanResult, utils.MysqlScanResult) {
	if IPv6 {
		host = "["+host+"]";
	}
	var httpresult, httpsresult utils.HttpScanResult;
	var mysqlresult utils.MysqlScanResult;
	var pool sync.WaitGroup;
	pool.Add(3);
	go func () {
		defer pool.Done();
		httpresult = http(host);
	}();
	go func () {
		defer pool.Done();
		httpsresult = https(host);
	}();
	go func () {
		defer pool.Done();
		mysqlresult = mysql(host);
	}();

	pool.Wait();

	return httpresult, httpsresult, mysqlresult;
}

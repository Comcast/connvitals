package traceroute

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

import "golang.org/x/net/ipv4"
import "golang.org/x/net/icmp"
import "time"
import "net"
import "golang.org/x/net/ipv6"
import "connvitals/utils"

const ICMP4 = 1
const ICMP6 = 58


/*
	Contains a transparent interface for ipv4 and ipv6 communication
		IPv6: tells whether this structure should serve ipv4 or ipv6
		ipv6connection: either a reference to an ipv6 packet connection, or nil if !IPv6
		ipv4connection: either a reference to an ipv4 packet connection, or nil if IPv6
*/
type Conn struct {
	IPv6 bool;
	ipv6connection *ipv6.PacketConn;
	ipv4connection *ipv4.PacketConn;
};

/*
	Constructs and returns a new Conn object. Will listen on "0.0.0.0" for ipv4, or let the machine decide
		what address to bind for ipv6
*/
func NewConn(IPv6 bool) (conn Conn, err error) {
	// Empty connection
	conn = Conn{
		IPv6,
		nil,
		nil,
	};

	// Set network and listening address according to whether or not we're using ipv6
	var network, laddr string;
	if IPv6 {
		network = "ip6:ipv6-icmp";
		laddr = "";
	} else {
		network = "ip4:icmp";
		laddr = "0.0.0.0";
	}

	// Construct basic packet connection
	c, err := net.ListenPacket(network, laddr);
	if err != nil {
		return;
	}

	// Wrap the connection appropriately
	if IPv6 {
		conn.ipv6connection = ipv6.NewPacketConn(c);
	} else {
		conn.ipv4connection = ipv4.NewPacketConn(c);
	}

	return;
}


/*
	Sends a sequential ping to the host.
	Returns an error if packet construction or writing returns an error
*/
func (conn *Conn) SendTo(seqno int, host net.IPAddr) (err error) {
	var pkt []byte;
	var psh []byte = nil;

	if conn.IPv6 {
		// Oh, you were kidding me
		psh = icmp.IPv6PseudoHeader(conn.ipv6connection.LocalAddr().(*net.IPAddr).IP, host.IP);
	}

	msg := conn.MkPacket(seqno);
	pkt, err = msg.Marshal(psh);
	if err != nil {
		return;
	}

	if conn.IPv6 {
		_, err = conn.ipv6connection.WriteTo(pkt, nil, net.Addr(&host));
	} else {
		_, err = conn.ipv4connection.WriteTo(pkt, nil, net.Addr(&host));
	}
	return;
}


/*
	Transparently sets a deadline, returning any error thereby incurred
*/
func (conn *Conn) SetDeadline(t time.Time) (error) {
	if conn.IPv6 {
		return conn.ipv6connection.SetDeadline(t);
	} else {
		return conn.ipv4connection.SetDeadline(t);
	}
}

/*
	Sets hop limit on IPv6, and ttl on ipv4, without requiring the caller to know which
*/
func (conn *Conn) SetMaxHops(n int) error {
	if conn.IPv6 {
		return conn.ipv6connection.SetHopLimit(n);
	}
	return conn.ipv4connection.SetTTL(n);
}

/*
	Reads data from an ipv4 or ipv6 connection into the buffer provided by buff.
	Returns the amount of data read, the address that sent the data, and any errors raised by the read.
	(control flags are dropped on receipt)
*/
func (conn *Conn) RecvFrom(buff []byte) (amt int, addr net.Addr, err error) {
	if conn.IPv6 {
		amt, _, addr, err = conn.ipv6connection.ReadFrom(buff);
	} else {
		amt, _, addr, err = conn.ipv4connection.ReadFrom(buff);
	}
	return;
}


/*
	Parses ICMP and ICMPv6 messages, returning the message if successful, else an error
*/
func (conn *Conn) ICMPParse(pkt []byte) (msg *icmp.Message, err error) {
	if conn.IPv6 {
		msg, err = icmp.ParseMessage(ICMP6, pkt);
	} else {
		msg, err = icmp.ParseMessage(ICMP4, pkt);
	}
	if err != nil {
		return nil, err;
	}

	return;
}

/*
	Closes a Conn object's underlying ipv4 or ipv6 connection
*/
func (conn *Conn) Close() {
	if conn.IPv6 {
		conn.ipv6connection.Close();
	} else {
		conn.ipv4connection.Close();
	}
}

/*
	Contains the data necessary to run a route trace.
	    Host: the ip address of the host to which the trace runs
	    Max: Maximum number of network hops to go through before giving up
	    Connection: A persistent network connection to the Host.
*/
type Tracer struct {
	Host *net.IPAddr;
	Max int;
	Connection Conn;
	IPv6 bool;
};

/*
	Constructs a new Tracer object, initializing its Connection.
*/
func New(host *net.IPAddr, max int, IPv6 bool) (tracer *Tracer, err error) {
	conn, err := NewConn(IPv6);
	if err != nil {
		return;
	}

	tracer = &Tracer{
		host,
		max,
		conn,
		IPv6,
	};
	return;
}

/*
	Runs route tracing by sequentially sending packets with a TTL that increments from 1 to the Tracer's Max value.
	Returns a string of results, and prints warnings to stderr if a non-timeout error occurs.
	Returns an error if the maximum number of hops was reached without finding a route to the Host.
*/
func (tracer *Tracer) Run() ([]utils.Step, error) {
	defer tracer.Connection.Close();

	// pre-allocated memory for message contents
	buff := make([]byte, 1500);

	// allocate enough memory to hold all of our results
	results := make([]utils.Step, tracer.Max);

	// increments ttl each iteration
	for i := 0; i < tracer.Max; i++ {
		tracer.Connection.SetMaxHops(i+1);

		// Re-set deadline for this hop
		ts := time.Now();
		tracer.Connection.SetDeadline(ts.Add(100*time.Millisecond));

		// Send a packet
		err := tracer.Connection.SendTo(i, *tracer.Host);
		if err != nil {
			results[i] = utils.Step{"*", -1};
			utils.Warn(err.Error());
			continue;
		}

		var rtt float64;        // stores round-trip-time in milliseconds
		var size int;           // the amount of data received/size of the packet
		var addr net.Addr;      // address that sent the data
		var dest net.IP;        // original destination (used when received data implements an ICMP Time Exceeded response packet)
		var msg *icmp.Message;  // holds the received data in the form of an ICMP packet

		// Keep receiving packets until we get a response to the packet we sent
		for true {

			// Receive a packet
			size, addr, err = tracer.Connection.RecvFrom(buff);
			if err != nil {
				//Likely a timeout
				results[i] = utils.Step{"*", -1};
				break;
			}

			// Record the round-trip-time immediately
			rtt = float64(time.Since(ts)) / float64(time.Millisecond);

			msg, err = tracer.Connection.ICMPParse(buff[:size]);
			if err != nil {
				results[i] = utils.Step{"*", -1};
				utils.Warn(err.Error());
				break;
			}

			//Handle the different message types. Will set the 'dest' var if the type is TimeExceeded
			switch msg.Type {

				// TTL/Hop_Limit Exceeded - figure out how far it got
				case ipv6.ICMPTypeTimeExceeded:
					dest = net.IP((*msg).Body.(*icmp.TimeExceeded).Data[24:40]);
				case ipv4.ICMPTypeTimeExceeded:
					var parts []byte = (*msg).Body.(*icmp.TimeExceeded).Data[16:20];
					dest = net.IPv4(parts[0], parts[1], parts[2], parts[3]);

				// Reply from target, figure out if it's our target and the packet was sent by a tracer
				case ipv4.ICMPTypeEchoReply:
					fallthrough;
				case ipv6.ICMPTypeEchoReply:
					if addr.(*net.IPAddr).IP.Equal(tracer.Host.IP) && msg.Body.(*icmp.Echo).ID == 1 {
						results[i] = utils.Step{addr.String(), rtt};
						return results[:i+1], nil;
					}
			}

			// If the packet was a Time Exceeded message, check if it was sent by our tracer. If yes, record result and move on.
			if dest.Equal(tracer.Host.IP) {
				results[i] = utils.Step{addr.String(), rtt};
				break;
			}

		}
	}

	// This statement should only be reached if the maximum number of hops was used to try (and fail) to reach the target.
	err := utils.GenericError{"Route was longer than the maximum-allowed TTL, or host '"+tracer.Host.String()+"' could not be reached"};
	return results, err;
}


/*
	Constructs an icmp packet to send along a connection
*/
func (conn *Conn) MkPacket(seqno int) (msg icmp.Message) {
	var typ icmp.Type;
	if conn.IPv6 {
		typ = ipv6.ICMPTypeEchoRequest;
	} else {
		typ = ipv4.ICMPTypeEcho;
	}

	msg = icmp.Message{
		Type: typ,
		Code: 0,
		Body: &icmp.Echo{
			ID: 1,
			Seq: seqno,
			Data: make([]byte, 1),
		},
	};
	return;
}

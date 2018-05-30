package ping

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
import "golang.org/x/net/ipv4"
import "golang.org/x/net/ipv6"
import "golang.org/x/net/icmp"
import "time"
import "sync"
import "math"
import "connvitals/utils"

const IPV6_NETWORK_STRING = "ip6:ipv6-icmp";
const IPV4_NETWORK_STRING = "ip4:icmp"

/*
	A data structure that handles sending/receiving ICMP Echo ("ping") packets
*/
type Pinger struct {
	Host *net.IPAddr;
	IPv6 bool;
	Payload []byte;
	Connection *icmp.PacketConn;
	timestamps []time.Time;
	RTTS []time.Duration;
};

/*
	Builds a Pinger object, initializing the connection and setting the rtts to -1
*/
func New(host *net.IPAddr, IPv6 bool, payload int, numpings int) (pinger *Pinger, err error) {
	initialrtts := make([]time.Duration, numpings);
	for i := 0; i < numpings; i++ {
		initialrtts[i] = time.Duration(-1);
	}

	pinger = &Pinger{
	             host,
	             IPv6,
	             make([]byte, payload),
	             nil,
	             make([]time.Time, numpings),
	             initialrtts,
	         };

	if IPv6 {
		pinger.Connection, err = icmp.ListenPacket(IPV6_NETWORK_STRING, "::");
		if err != nil {
			return;
		}
		pinger.Connection.IPv6PacketConn().SetDeadline(time.Now().Add(2 * time.Second));
	} else {
		pinger.Connection, err = icmp.ListenPacket(IPV4_NETWORK_STRING, "0.0.0.0");
		if err != nil {
			return;
		}
		pinger.Connection.IPv4PacketConn().SetDeadline(time.Now().Add(2 * time.Second));
	}

	return;
}

/*
	Constructs an icmp packet to send along a connection
*/
func (pinger *Pinger) MkPacket(seqno int) (msg icmp.Message) {
	var typ icmp.Type;
	if pinger.IPv6 {
		typ = ipv6.ICMPTypeEchoRequest;
	} else {
		typ = ipv4.ICMPTypeEcho;
	}

	msg = icmp.Message{
		Type: typ,
		Code: 0,
		Body: &icmp.Echo{
			ID: 2,
			Seq: seqno,
			Data: pinger.Payload,
		},
	};

	return;
}

/*
	Sends a single packet on the Pinger's Connection, identified by the sequence number specified with seqno.
	It returns any errors generated from constructing the packet or sending it through the socket.
*/
func (pinger *Pinger) Send(seqno int) ( err error ) {
	pkt := pinger.MkPacket(seqno);
	var psh []byte = nil;
	if pinger.IPv6 {
		psh = icmp.IPv6PseudoHeader(pinger.Connection.LocalAddr().(*net.IPAddr).IP, pinger.Host.IP);
	}

	encodedPacket, err := pkt.Marshal(psh);
	if err != nil {
		return;
	}

	pinger.timestamps[seqno] = time.Now();
	if pinger.IPv6 {
		_, err = pinger.Connection.WriteTo(encodedPacket, pinger.Host);
	} else {
		_, err = pinger.Connection.WriteTo(encodedPacket, net.Addr(&net.IPAddr{IP: pinger.Host.IP.To4()}));
	}

	return;
}

/*
	Receives a single packet on the Pinger's Connection, and figures out what its sequence number is
	to calculate a round-trip time (rtt) for the packet. Returns errors caused by parsing messages.
*/
func (pinger *Pinger) Recv() (err error) {
	buf := make([]byte, 65536);
	var size int;
	var addr net.Addr;
	var msg *icmp.Message;

	// Wait for a ping from the host that we actually pinged
	for true {
		size, addr, err = pinger.Connection.ReadFrom(buf);
		if err != nil {
			err = nil; // This is almost certainly a timeout, so just ignore it (for now)
			return;
		} else if addr.(*net.IPAddr).IP.Equal(pinger.Host.IP) {
			var proto int;
			if pinger.IPv6 {
				proto = ipv6.ICMPTypeEchoRequest.Protocol();
			} else {
				proto = ipv4.ICMPTypeEcho.Protocol();
			}

			msg, err = icmp.ParseMessage(proto, buf[:size]);
			if err != nil {
				return;
			} else if (msg.Type == ipv4.ICMPTypeEchoReply || msg.Type == ipv6.ICMPTypeEchoReply ) && msg.Body.(*icmp.Echo).ID == 2 {
				break;
			}

		}
	}



	seqno := msg.Body.(*icmp.Echo).Seq;
	pinger.RTTS[seqno] = time.Since(pinger.timestamps[seqno]);
	return;
}



/*
	Pings a single host passed as an argument, and returns a result string that's ready for printing.
*/
func PingHost(host *net.IPAddr, IPv6 bool, numpings int, payload int) (min, avg, max, std, loss float64, err error) {
	pinger, err := New(host, IPv6, payload, numpings);
	if err != nil {
		return;
	}
	defer pinger.Connection.Close();

	var pool sync.WaitGroup;

	for i := 0; i < numpings; i++ {
		pool.Add(2);

		go func (seqno int) {
			defer pool.Done();
			err = pinger.Send(seqno);
			if err != nil {
				utils.Warn(err.Error());
			}
		}(i);

		go func () {
			defer pool.Done();
			err = pinger.Recv();
			if err != nil {
				utils.Warn(err.Error());
			}
		}();
	}

	// Wait for results
	pool.Wait();

	min = math.Inf(0);
	number_of_lost_packets := 0;
	for i := 0; i < numpings; i++ {
		rtt := float64(pinger.RTTS[i]) / float64(time.Millisecond);
		if rtt < 0 {
			number_of_lost_packets++;
			continue;
		}

		if min > rtt {
			min = rtt;
		}
		if max < rtt {
			max = rtt;
		}

		avg += rtt
	}

	avg /= float64(numpings - number_of_lost_packets);

	//Need to loop again once the average is found to get std
	for i := 0; i < numpings; i++ {
		rtt := float64(pinger.RTTS[i]) / float64(time.Millisecond);
		if rtt > 0 {
			std += math.Pow(rtt - avg, 2);
		}
	}
	std /= float64(numpings - 1 - number_of_lost_packets);
	std = math.Sqrt(std);

	// if all packets are lost, the values of min/avg/max/std are meaningless, so print this instead to avoid confusion
	if number_of_lost_packets >= numpings {
		return -1, -1, -1, -1, 100, nil;
	} else {
		loss = float64(number_of_lost_packets)/ float64(numpings) * 100.0;
	}

	return;
}

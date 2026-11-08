"""Probe the LAN NTP server without changing any system clock or firewall."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import struct
import time

EPOCH = 2208988800


def stamp(value):
    seconds = value + EPOCH
    whole = int(seconds)
    return struct.pack('!II', whole, int((seconds-whole)*2**32))


def unix(data):
    seconds, fraction = struct.unpack('!II', data)
    return seconds-EPOCH+fraction/2**32


def probe(host, port):
    packet = bytearray(48)
    packet[0] = 0x23  # NTP version 4, client mode.
    sent = time.time()
    packet[40:48] = stamp(sent)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(5)
        connection.sendto(packet, (host, port))
        response, _ = connection.recvfrom(512)
        received = time.time()
    if len(response) < 48 or response[0] & 7 != 4 or response[0] >> 6 == 3:
        raise ValueError('Invalid or unsynchronized NTP response')
    if not 1 <= response[1] <= 15 or response[24:32] != packet[40:48]:
        raise ValueError('Invalid stratum or mismatched request timestamp')
    server_received, server_sent = unix(response[32:40]), unix(response[40:48])
    offset = ((server_received-sent)+(server_sent-received))/2
    return {'timestamp': datetime.now(timezone.utc).isoformat(), 'host':host, 'port':port,
            'stratum':response[1], 'offset_ms':round(offset*1000,3),
            'round_trip_ms':round(((received-sent)-(server_sent-server_received))*1000,3),
            'pass':abs(offset)<2, 'scope':'Laptop UDP probe; ESP32 boot and LAN firewall are separate acceptance steps'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=123)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=probe(args.host,args.port)
    body=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(body+'\n',encoding='utf-8')
    print(body)
    return 0 if result['pass'] else 1


if __name__=='__main__': raise SystemExit(main())

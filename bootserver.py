import socket
import sys

port = 58000
if len(sys.argv) == 3 and sys.argv[1] == "-p":
    port = int(sys.argv[2])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", port))
print("Servidor de arranque UDP na porta {}".format(port))

rings = {}   # x -> (id, ip, tcp)

while True:
    data, addr = s.recvfrom(1024)
    msg = data.decode().strip()
    parts = msg.split()
    reply = None

    try:
        if parts[0] == "BQRY" and len(parts) == 2:
            x = int(parts[1])
            if x not in rings:
                reply = "EMPTY"
            else:
                i, ip, tcp = rings[x]
                reply = "BRSP {} {} {} {}".format(x, i, ip, tcp)

        elif parts[0] == "REG" and len(parts) == 5:
            x, i = int(parts[1]), int(parts[2])
            rings[x] = (i, parts[3], parts[4])
            reply = "OK"

        elif parts[0] == "UNR" and len(parts) == 2:
            rings.pop(int(parts[1]), None)
            reply = "OK"
    except (ValueError, IndexError):
        pass

    if reply is None:
        print("Mensagem invalida de {}: {!r}".format(addr, msg))
        continue

    print("<- {}\n-> {}".format(msg, reply))
    s.sendto(reply.encode(), addr)
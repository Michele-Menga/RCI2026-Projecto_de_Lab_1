import socket
import select
import sys
import time
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("-t", type=int, default=5000)
ap.add_argument("-i", default="192.168.56.21")
ap.add_argument("-p", type=int, default=58000)
args = ap.parse_args()


ring = None          
my_id = None         
succ = None          
pred = None          
succ_sock = None     
pred_sock = None    
is_boot = False      
pending = []         
bufs = {}            
id_conns = []      
id_waiting = {}      


def my_ip():
    """Descobre o meu IP na rede (o que fica registado no servidor de arranque)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((args.i, args.p))      
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


MY_IP = my_ip()



def boot_request(msg):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(3)
    try:
        u.sendto(msg.encode(), (args.i, args.p))
        data, _ = u.recvfrom(1024)
        return data.decode().strip()
    except (socket.timeout, OSError) as e:
        print("Erro a falar com o servidor de arranque:", e)
        return None
    finally:
        u.close()



def send(sock, msg):
    """Envia uma mensagem terminada em nova linha."""
    if sock is None:
        print("Sem sessao TCP para enviar '{}'".format(msg))
        return False
    try:
        sock.sendall((msg + "\n").encode())
        return True
    except OSError as e:
        print("Erro a enviar '{}': {}".format(msg, e))
        return False


def tcp_connect(ip, port):
    """Abre uma sessao TCP para (ip, port). Devolve o socket ou None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((ip, port))
    except OSError as e:
        print("Nao consegui ligar a {}:{} ({})".format(ip, port, e))
        s.close()
        return None
    s.settimeout(None)
    bufs[s] = b""
    return s


def close_sock(s):
    if s is not None:
        bufs.pop(s, None)
        try:
            s.close()
        except OSError:
            pass


def read_lines(sock):
    """Le o que chegou ao socket. Devolve (lista de linhas completas, fechado?)."""
    try:
        data = sock.recv(1024)
    except OSError:
        return [], True
    if not data:
        return [], True
    buf = bufs.get(sock, b"") + data
    lines = []
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        text = line.decode("utf-8", "replace").strip()
        if text:
            lines.append(text)
    bufs[sock] = buf          
    return lines, False


def wait_line(sock, timeout):
    """Espera ate 'timeout' segundos por uma linha. Devolve a linha ou None."""
    end = time.time() + timeout
    while True:
        left = end - time.time()
        if left <= 0:
            return None
        r, _, _ = select.select([sock], [], [], left)
        if not r:
            return None
        lines, closed = read_lines(sock)
        if lines:
            return lines[0]
        if closed:
            return None



srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", args.t))
srv.listen(5)



def responsible(k):
    """True se este no e responsavel pelo identificador k.
    Responsabilidade: ids entre pred (exclusive) e eu (inclusive), em anel."""
    p = pred[0]
    if p == my_id:                  
        return True
    if p < my_id:                   
        return p < k <= my_id
    return k > p or k <= my_id      



def handle_new(conn, nid, nip, nport):
    """Recebi NEW: o no 'nid' passa a ser o meu predecessor."""
    global pred, pred_sock, succ, succ_sock
    pending.remove(conn)
    alone = (succ is not None and succ[0] == my_id)   
    old_sock = pred_sock
    pred = (nid, nip, nport)
    pred_sock = conn
    print("\n[NEW] novo predecessor: {}".format(nid))
    if alone:
      
        s = tcp_connect(nip, nport)
        if s is None:
            return
        send(s, "NEW {} {} {}".format(my_id, MY_IP, args.t))
        succ = (nid, nip, nport)
        succ_sock = s
        print("[NEW] novo sucessor: {}".format(nid))
    elif old_sock is not None and old_sock is not conn:
      
        send(old_sock, "CON {} {} {}".format(nid, nip, nport))
        close_sock(old_sock)


def handle_id(conn, k):
    """Recebi ID k de um no novo: pesquisar o sucessor dele no anel."""
    pending.remove(conn)
    if pred is None or succ is None:
        print("\nRecebi ID mas o meu anel ainda nao esta completo.")
        close_sock(conn)
        return
    id_conns.append(conn)
    print("\n[ID] o no {} quer entrar. A pesquisar o sucessor dele...".format(k))
    if responsible(k):
       
        send(conn, "SUCC {} {} {}".format(my_id, MY_IP, args.t))
    else:
        id_waiting[k] = conn
        send(succ_sock, "QRY {} {}".format(my_id, k))


def handle_succ_line(line):
    """Mensagens que chegam pela sessao do sucessor: CON e RSP."""
    global succ, succ_sock, pred, pred_sock
    parts = line.split()

    if parts and parts[0] == "CON" and len(parts) == 4:
        try:
            cid, cip, cport = int(parts[1]), parts[2], int(parts[3])
        except ValueError:
            print("\nCON mal formada:", line)
            return
        if cid == my_id:
            
            close_sock(succ_sock)
            close_sock(pred_sock)
            succ_sock = None
            pred_sock = None
            succ = pred = (my_id, MY_IP, args.t)
            print("\n[CON] o outro no saiu. Fiquei sozinho no anel.")
            return
        s = tcp_connect(cip, cport)
        if s is None:
            return
        send(s, "NEW {} {} {}".format(my_id, MY_IP, args.t))
        old = succ_sock
        succ = (cid, cip, cport)
        succ_sock = s
        close_sock(old)
        print("\n[CON] novo sucessor: {}".format(cid))

    elif parts and parts[0] == "RSP" and len(parts) == 6:
        # RSP j k l l.IP l.TCP
        try:
            j, k, l = int(parts[1]), int(parts[2]), int(parts[3])
            lip, lport = parts[4], int(parts[5])
        except ValueError:
            print("\nRSP mal formada:", line)
            return
        if j == my_id:
            if k in id_waiting:
                
                c = id_waiting.pop(k)
                send(c, "SUCC {} {} {}".format(l, lip, lport))
            else:
                
                print("\nResultado da pesquisa de {}: no {} em {}:{}".format(
                    k, l, lip, lport))
        else:
            
            send(pred_sock, "RSP {} {} {} {} {}".format(j, k, l, lip, lport))

    else:
        print("\nMensagem invalida do sucessor:", line)


def handle_pred_line(line):
    """Mensagens que chegam pela sessao do predecessor: QRY e BOOT."""
    global is_boot
    parts = line.split()
    if parts and parts[0] == "QRY" and len(parts) == 3:
        try:
            j, k = int(parts[1]), int(parts[2])
        except ValueError:
            print("\nQRY mal formada:", line)
            return
        if not (0 <= k <= 63):
            print("\nQRY com identificador invalido:", line)
            return
        if responsible(k):
            send(pred_sock, "RSP {} {} {} {} {}".format(
                j, k, my_id, MY_IP, args.t))
        else:
            send(succ_sock, "QRY {} {}".format(j, k))
    elif parts and parts[0] == "BOOT" and len(parts) == 1:
        is_boot = True
        print("\n[BOOT] passei a ser o no de arranque do anel.")
    else:
        print("\nMensagem invalida do predecessor:", line)


def classify(conn, line):
    """Primeira mensagem de uma ligacao nova (NEW ou ID). False se rejeitou."""
    parts = line.split()
    if ring is not None and len(parts) == 4 and parts[0] == "NEW":
        try:
            nid, nip, nport = int(parts[1]), parts[2], int(parts[3])
            ok = (0 <= nid <= 63)
        except ValueError:
            ok = False
        if ok:
            handle_new(conn, nid, nip, nport)
            return True
    elif ring is not None and len(parts) == 2 and parts[0] == "ID":
        try:
            k = int(parts[1])
            ok = (0 <= k <= 63)
        except ValueError:
            ok = False
        if ok:
            handle_id(conn, k)
            return True
    print("\nMensagem inesperada numa ligacao nova: {!r}".format(line))
    pending.remove(conn)
    close_sock(conn)
    return False


def service(sock):
    """Ha dados (ou fecho) num socket de sessao."""
    global pred, pred_sock, succ, succ_sock

    if sock in id_conns:
       
        lines, closed = read_lines(sock)
        if closed or lines:
            id_conns.remove(sock)
            for k in [k for k, c in id_waiting.items() if c is sock]:
                del id_waiting[k]
            close_sock(sock)
        return

    lines, closed = read_lines(sock)
    for line in lines:
        if sock in pending:
            if not classify(sock, line):
                return
        elif sock is pred_sock:
            handle_pred_line(line)
        elif sock is succ_sock:
            handle_succ_line(line)
        else:
            return                     
    if not closed:
        return
    if sock in pending:
        pending.remove(sock)
        close_sock(sock)
    elif sock is pred_sock:
        print("\nO predecessor fechou a ligacao.")
        pred = None
        pred_sock = None
        close_sock(sock)
    elif sock is succ_sock:
        print("\nO sucessor fechou a ligacao.")
        succ = None
        succ_sock = None
        close_sock(sock)
    else:
        close_sock(sock)


def join_existing(x, i, reply):
    """Adesao a um anel que ja tem nos (resposta BRSP do servidor de arranque)."""
    global ring, my_id, succ, succ_sock
    p = reply.split()
    try:
        if len(p) != 5 or p[0] != "BRSP" or int(p[1]) != x:
            raise ValueError
        j, jip, jport = int(p[2]), p[3], int(p[4])
    except ValueError:
        print("Resposta invalida do servidor de arranque:", reply)
        return

    if j == i:
        print("O identificador {} e o do no de arranque. Escolhe outro.".format(i))
        return

    
    s = tcp_connect(jip, jport)
    if s is None:
        print("O no de arranque nao responde. Se for um anel antigo ficou "
              "registado, apaga-o com UNR no servidor de arranque.")
        return
    if not send(s, "ID {}".format(i)):
        close_sock(s)
        return
    line = wait_line(s, 10)
    close_sock(s)                   
    if line is None:
        print("Sem resposta do no de arranque (timeout).")
        return

    q = line.split()
    try:
        if len(q) != 4 or q[0] != "SUCC":
            raise ValueError
        l, lip, lport = int(q[1]), q[2], int(q[3])
    except ValueError:
        print("Mensagem invalida do no de arranque:", line)
        return

    if l == i:
        print("O identificador {} ja esta em uso no anel. Escolhe outro.".format(i))
        return


    conn = tcp_connect(lip, lport)
    if conn is None:
        return
    if not send(conn, "NEW {} {} {}".format(i, MY_IP, args.t)):
        close_sock(conn)
        return
    ring, my_id = x, i
    succ = (l, lip, lport)
    succ_sock = conn
    print("Entrei no anel {} com o id {}. Sucessor: {}.".format(x, i, l))


def cmd_join(parts):
    global ring, my_id, succ, pred, succ_sock, is_boot
    if ring is not None:
        print("Ja pertences ao anel", ring)
        return

    if len(parts) == 3:                           
        try:
            x, i = int(parts[1]), int(parts[2])
        except ValueError:
            print("Uso: join x i")
            return
        if not (0 <= i <= 63):
            print("O identificador tem de estar entre 0 e 63")
            return
        reply = boot_request("BQRY {}".format(x))
        if reply is None:
            return
        if reply == "EMPTY":
            r = boot_request("REG {} {} {} {}".format(x, i, MY_IP, args.t))
            if r == "OK":
                ring, my_id = x, i
                succ = pred = (i, MY_IP, args.t)
                is_boot = True                      # criei o anel: sou o no de arranque
                print("Anel {} criado. Sou o no {}.".format(x, i))
            else:
                print("Resposta inesperada:", r)
        elif reply.startswith("BRSP"):
            join_existing(x, i, reply)
        else:
            print("Resposta inesperada:", reply)

    elif len(parts) == 6:                            # join x i succ succ.IP succ.TCP
        try:
            x, i, s_id = int(parts[1]), int(parts[2]), int(parts[3])
            s_ip, s_port = parts[4], int(parts[5])
        except ValueError:
            print("Uso: join x i succ succ.IP succ.TCP")
            return
        if not (0 <= i <= 63 and 0 <= s_id <= 63):
            print("Os identificadores tem de estar entre 0 e 63")
            return
        if i == s_id:
            print("O sucessor tem de ser um no diferente de ti")
            return
        conn = tcp_connect(s_ip, s_port)
        if conn is None:
            return
        if not send(conn, "NEW {} {} {}".format(i, MY_IP, args.t)):
            close_sock(conn)
            return
        ring, my_id = x, i
        succ = (s_id, s_ip, s_port)
        succ_sock = conn
        print("Entrei no anel {} com o id {}. Sucessor: {}.".format(x, i, s_id))
    else:
        print("Uso: join x i   |   join x i succ succ.IP succ.TCP")


def cmd_show():
    if ring is None:
        print("Nao estas em nenhum anel.")
        return
    print("Anel: {}".format(ring))
    print("No: {}".format(my_id))
    print("Sucessor: {}".format(succ[0] if succ else "(nenhum)"))
    print("Predecessor: {}".format(pred[0] if pred else "(a aguardar)"))
    print("No de arranque: {}".format("sim" if is_boot else "nao"))


def cmd_search(parts):
    if ring is None:
        print("Nao estas em nenhum anel.")
        return
    if len(parts) != 2:
        print("Uso: search k")
        return
    try:
        k = int(parts[1])
    except ValueError:
        print("Uso: search k")
        return
    if not (0 <= k <= 63):
        print("O identificador tem de estar entre 0 e 63")
        return
    if pred is None or succ is None:
        print("O anel ainda nao esta completo (falta predecessor ou sucessor).")
        return
    if responsible(k):
        print("Resultado da pesquisa de {}: no {} em {}:{}".format(
            k, my_id, MY_IP, args.t))
    else:
        send(succ_sock, "QRY {} {}".format(my_id, k))
        print("Pesquisa enviada, a aguardar resposta...")


def reset_state():
    """Esquece o anel: fecha todas as sessoes e volta ao estado inicial."""
    global ring, my_id, succ, pred, succ_sock, pred_sock, is_boot
    for c in list(id_conns):
        close_sock(c)
    del id_conns[:]
    id_waiting.clear()
    close_sock(succ_sock)
    close_sock(pred_sock)
    ring = my_id = succ = pred = None
    succ_sock = pred_sock = None
    is_boot = False


def cmd_leave():
    if ring is None:
        print("Nao estas em nenhum anel.")
        return
    x = ring

  
    if succ is None or pred is None:
        print("Aviso: o anel esta incompleto. Saio apenas localmente.")
        reset_state()
        return


    if succ[0] == my_id:
        r = boot_request("UNR {}".format(x))
        if r == "OK":
            print("Saiste do anel {} (anel anulado).".format(x))
            reset_state()
        else:
            print("O servidor de arranque nao confirmou o UNR ({}). "
                  "Tenta de novo.".format(r))
        return

    s_id, s_ip, s_port = succ


    if is_boot:
        r = boot_request("REG {} {} {} {}".format(x, s_id, s_ip, s_port))
        if r != "OK":
            print("O servidor de arranque nao confirmou o REG ({}). "
                  "Tenta de novo.".format(r))
            return
        send(succ_sock, "BOOT")


    close_sock(succ_sock)
    send(pred_sock, "CON {} {} {}".format(s_id, s_ip, s_port))
    print("Saiste do anel {}.".format(x))
    reset_state()


def handle_command(line):
    parts = line.split()
    if not parts:
        return True
    c = parts[0]
    if c == "join":
        cmd_join(parts)
    elif c == "show":
        cmd_show()
    elif c == "search":
        cmd_search(parts)
    elif c == "leave":
        cmd_leave()
    elif c == "exit":
        if ring is not None:
            cmd_leave()               
        return False
    else:
        print("Comando desconhecido:", c)
    return True



print("ddt a correr. TCP na porta {}. Arranque: {}:{}".format(
    args.t, args.i, args.p))
running = True
while running:
    print("> ", end="", flush=True)
    watch = [sys.stdin, srv] + pending + id_conns
    if succ_sock is not None:
        watch.append(succ_sock)
    if pred_sock is not None:
        watch.append(pred_sock)
    readable, _, _ = select.select(watch, [], [])
    for r in readable:
        if r is sys.stdin:
            line = sys.stdin.readline()
            if line == "":
                running = False
            else:
                running = handle_command(line.strip())
        elif r is srv:
            conn, addr = srv.accept()
            bufs[conn] = b""
            pending.append(conn)
        else:
            service(r)

for s in pending + id_conns + [succ_sock, pred_sock, srv]:
    close_sock(s)
print("Adeus.")
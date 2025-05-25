import socket
import threading
import struct
import sqlite3
import time
import logging

ROUTE_CACHE = {}
DB_PATH = "db/proxy.db"
SQL_FILE = "db/schema.sql"
logger = logging.getLogger("proxy")

def load_routes():
    old_len = len(ROUTE_CACHE)
    global ROUTE_CACHE
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT hostname, target_ip, target_port FROM routes")
            new_cache = {
                hostname: (ip, port)
                for hostname, ip, port in cur.fetchall()
            }
            if new_cache!= ROUTE_CACHE:
                ROUTE_CACHE = new_cache
                logger.info(f"Cache updated: {len(ROUTE_CACHE)-old_len} routes loaded.")
    except Exception as e:
        logger.error("Failed to load routes:", e)

def start_cache_updater(interval=30):
    def updater():
        while True:
            load_routes()
            time.sleep(interval)
    t = threading.Thread(target=updater, daemon=True)
    t.start()

def get_target_from_cache(hostname):
    return ROUTE_CACHE.get(hostname)

    
def get_target_from_db(hostname):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT target_ip, target_port FROM routes WHERE hostname = ?", (hostname,))
            res = cur.fetchone()
            if res:
                ip, port = res
                ROUTE_CACHE[hostname] = (ip, port)
                return (ip, port)
    except Exception as e:
        logger.error(f"Error fetching from DB:", e)
    return None

def read_varint(sock):
    result = 0
    shift = 0
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("Connection closed")
        b = byte[0]
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result

def read_n_bytes(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data



def parse_handshake(client_sock):
    packet_length = read_varint(client_sock)
    data = read_n_bytes(client_sock, packet_length)
    i = 0

    def read_varint_from_data():
        nonlocal i
        result = 0
        shift = 0
        while True:
            b = data[i]
            i += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return result

    packet_id = read_varint_from_data()
    if packet_id != 0x00:
        raise ValueError("Not a handshake")

    protocol_version = read_varint_from_data()
    hostname_length = read_varint_from_data()
    hostname = data[i:i+hostname_length].decode()
    i += hostname_length
    port = int.from_bytes(data[i:i+2], "big")
    i += 2
    next_state = data[i]

    logger.info(f"Handshake detected: Host={hostname}, Port={port}, Version={protocol_version}")

    return hostname, data[:i+1]  # We return the full handshake payload



def handle_client(client_sock, client_addr):
    try:
        hostname, handshake_data = parse_handshake(client_sock)
        backend = get_target_from_cache(hostname) or get_target_from_db(hostname)
        logger.info(f"Client {client_addr} requested hostname: {hostname}")
        if not backend:
            logger.error(f"No route found for hostname: {hostname}")
            client_sock.close()
            return
        logger.info(f"Found backend for {hostname}: {backend[0]}:{backend[1]}")
        server_sock = socket.create_connection(backend)

        # Send the handshake to the server
        total_len = len(handshake_data)
        varint_len = b''
        value = total_len
        while True:
            part = value & 0x7F
            value >>= 7
            if value != 0:
                part |= 0x80
            varint_len += bytes([part])
            if value == 0:
                break

        server_sock.sendall(varint_len + handshake_data)
        logger.info(f"Connected to backend: {backend[0]}:{backend[1]} for {hostname}")
        threading.Thread(target=pipe, args=(client_sock, server_sock), daemon=True).start()
        threading.Thread(target=pipe, args=(server_sock, client_sock), daemon=True).start()

    except Exception as e:
        logger.error(f"Error: {e}")
        client_sock.close()

def pipe(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except:
        pass
    finally:
        src.close()
        dst.close()

def start_proxy():
    load_routes()
    start_cache_updater()

    sock = socket.socket()
    sock.bind(("0.0.0.0", 25565))
    sock.listen()
    logger.info("Proxy listening on 25565")

    while True:
        client_sock, client_addr = sock.accept()
        threading.Thread(target=handle_client, args=(client_sock,client_addr), daemon=True).start()

def create_db():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        with open(SQL_FILE, "r", encoding="utf-8") as f:
            sql_script = f.read()
        cur.executescript(sql_script)
        conn.commit()
    logger.info("Database initialized.")

if __name__ == "__main__":
    create_db()
    start_proxy()

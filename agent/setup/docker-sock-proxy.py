#!/usr/bin/env python3
"""Forward a user-owned unix socket to /var/run/docker.sock.

Event box only: the systemd user manager started before dell joined the docker group, so the
OpenShell gateway user service can't open docker.sock (no sudo to restart user@1000). Run this
from a shell that has the docker group; the gateway drop-in sets DOCKER_HOST to the proxy socket.
"""
import os, socket, sys, threading

SRC = sys.argv[1] if len(sys.argv) > 1 else f"/run/user/{os.getuid()}/docker-proxy.sock"
DST = "/var/run/docker.sock"


def pipe(a, b):
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def serve(client):
    upstream = socket.socket(socket.AF_UNIX)
    try:
        upstream.connect(DST)
    except OSError:
        client.close()
        return
    threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()
    pipe(client, upstream)
    client.close()
    upstream.close()


if os.path.exists(SRC):
    os.unlink(SRC)
srv = socket.socket(socket.AF_UNIX)
srv.bind(SRC)
os.chmod(SRC, 0o600)
srv.listen(128)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=serve, args=(conn,), daemon=True).start()

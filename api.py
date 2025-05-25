from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3

app = FastAPI()
DB = "db/proxy.db"

class Route(BaseModel):
    hostname: str
    target_ip: str
    target_port: int

@app.post("/routes/")
def add_route(route: Route):
    with sqlite3.connect(DB) as conn:
        try:
            conn.execute(
                "INSERT INTO routes (hostname, target_ip, target_port) VALUES (?, ?, ?)",
                (route.hostname, route.target_ip, route.target_port)
            )
            return {"status": "ok"}
        except sqlite3.IntegrityError:
            raise HTTPException(400, "Hostname already exists")

@app.get("/routes/")
def get_routes():
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT hostname, target_ip, target_port FROM routes")
        routes = cur.fetchall()
        return [{"hostname": r[0], "ip": r[1], "port": r[2]} for r in routes]
    
@app.delete("/routes/{hostname}")
def delete_route(hostname: str):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM routes WHERE hostname = ?", (hostname,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Route not found")
        return {"status": "ok"}

@app.get("/routes/{hostname}")
def get_route(hostname: str):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT target_ip, target_port FROM routes WHERE hostname = ?", (hostname,))
        res = cur.fetchone()
        if res:
            return {"ip": res[0], "port": res[1]}
        raise HTTPException(404, "Route not found")

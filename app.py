"""Backend Flask pour le dashboard ascenseur SOFIA."""
from __future__ import annotations

import os
import shutil
from functools import wraps
from pathlib import Path

from flask import Flask, request, session, redirect, url_for, jsonify

from src.db import get_connection
from src.ascenseur.export_dashboard import generate_dashboard_data, generate_html
from src.ascenseur.votes import mettre_a_jour_vote, initialiser_votes

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

ACCESS_CODE = os.environ.get("ACCESS_CODE", "1234")

# ── Persistance volume Railway ──────────────────────────────
VOLUME_DB = Path(os.environ.get("DB_PATH", "data/sofia.db"))
BUNDLED_DB = Path(__file__).resolve().parent / "data" / "sofia.db"

if str(VOLUME_DB).startswith("/data/"):
    VOLUME_DB.parent.mkdir(parents=True, exist_ok=True)
    if not VOLUME_DB.exists() and BUNDLED_DB.exists():
        shutil.copy2(BUNDLED_DB, VOLUME_DB)

os.environ.setdefault("DB_PATH", str(VOLUME_DB))


def _db():
    return get_connection(VOLUME_DB)


# ── Auth ────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Accès — Dashboard Ascenseur SOFIA</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f1119;display:flex;align-items:center;justify-content:center;min-height:100vh;
color:rgba(255,255,255,0.92)}
body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;
background:radial-gradient(ellipse at 20% 50%,rgba(108,138,255,0.08) 0%,transparent 50%),
radial-gradient(ellipse at 80% 20%,rgba(76,217,123,0.05) 0%,transparent 50%);
pointer-events:none;z-index:-1}
.card{background:rgba(255,255,255,0.06);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
border:1px solid rgba(255,255,255,0.10);border-radius:16px;padding:40px;
box-shadow:0 8px 32px rgba(0,0,0,.3);width:100%;max-width:360px;text-align:center}
h1{font-size:20px;color:#6c8aff;margin-bottom:8px}
p.sub{font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:24px}
input{width:100%;padding:12px;border:1px solid rgba(255,255,255,0.12);border-radius:8px;font-size:16px;
text-align:center;letter-spacing:4px;outline:none;transition:border-color .2s;
background:rgba(255,255,255,0.06);color:white}
input:focus{border-color:#6c8aff;box-shadow:0 0 0 3px rgba(108,138,255,0.15)}
button{width:100%;padding:12px;background:rgba(108,138,255,0.3);color:#fff;
border:1px solid rgba(108,138,255,0.5);border-radius:8px;
font-size:15px;font-weight:600;cursor:pointer;margin-top:16px;transition:all .2s}
button:hover{background:rgba(108,138,255,0.4);border-color:#6c8aff}
.error{color:#ff6b6b;font-size:13px;margin-top:12px}
</style></head><body>
<div class="card">
<h1>Dashboard Ascenseur</h1>
<p class="sub">Copropriété SOFIA — Bâtiment A</p>
<form method="post">
<input type="password" name="code" placeholder="Code d'accès" autofocus required>
<button type="submit">Accéder</button>
<!-- error -->
</form></div></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("code") == ACCESS_CODE:
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        error = '<p class="error">Code incorrect</p>'
    return LOGIN_HTML.replace("<!-- error -->", error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ───────────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    conn = _db()
    try:
        data = generate_dashboard_data(conn)
        html = generate_html(data)
        return html
    finally:
        conn.close()


# ── API Votes ───────────────────────────────────────────────
@app.route("/api/votes", methods=["GET"])
@login_required
def get_votes():
    conn = _db()
    try:
        from src.ascenseur.votes import get_votes_detail, calculer_resultats
        detail = get_votes_detail(conn)
        resultats = calculer_resultats(conn)
        return jsonify({"detail": detail, "resultats": resultats})
    finally:
        conn.close()


@app.route("/api/votes/<int:lot_id>", methods=["POST"])
@login_required
def update_vote(lot_id):
    data = request.get_json(silent=True) or {}
    vote = data.get("vote")
    confiance = data.get("confiance")
    if not vote:
        return jsonify({"error": "vote requis"}), 400

    conn = _db()
    try:
        ok = mettre_a_jour_vote(conn, lot_id, vote, confiance)
        if not ok:
            return jsonify({"error": "lot introuvable"}), 404
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/contact/<int:lot_id>", methods=["POST"])
@login_required
def update_contact(lot_id):
    data = request.get_json(silent=True) or {}
    contact_fait = 1 if data.get("contact_fait") else 0
    conn = _db()
    try:
        result = conn.execute(
            "UPDATE vote_simulation SET contact_fait = ? WHERE lot_id = ?",
            (contact_fait, lot_id),
        )
        conn.commit()
        if result.rowcount == 0:
            return jsonify({"error": "lot introuvable"}), 404
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/api/votes/reset", methods=["POST"])
@login_required
def reset_votes():
    conn = _db()
    try:
        conn.execute("DELETE FROM vote_simulation")
        conn.commit()
        initialiser_votes(conn)
        return jsonify({"ok": True})
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")

"""
Pro VPS Panel - Pure Render Optimized
Owner: Dark / DARK
"""
import os, json, time, uuid, shutil, subprocess, threading, secrets, zipfile, ast
from collections import deque
from pathlib import Path
from functools import wraps
from flask import (
    Flask, request, redirect, url_for, session,
    render_template, jsonify, Response, send_from_directory, abort
)
from werkzeug.utils import secure_filename

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
PRICING_FILE = DATA_DIR / "pricing.json"
FILES_ROOT = APP_DIR / "user_files"

DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_ROOT.mkdir(parents=True, exist_ok=True)

OWNER_USER = "Dark"
OWNER_PASS = "6151"

DEFAULT_PRICING = {
    "currency": "₹",
    "contact": "Telegram: @DARKxERA",
    "plans": [
        {"name": "Starter", "duration": "24 Hours",  "price": "49",  "features": "1 file run, 512MB RAM, Real-time logs"},
        {"name": "Basic",   "duration": "7 Days",    "price": "199", "features": "Multi-file upload, pip/npm install, 24/7 uptime"},
        {"name": "Pro",     "duration": "30 Days",   "price": "599", "features": "Unlimited modules, Priority support, Auto-restart"},
        {"name": "Premium", "duration": "Lifetime",  "price": "1999","features": "All features, Custom domain, Dedicated help"},
    ],
}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB upload

_lock = threading.Lock()

def load_users():
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {}

def save_users(u):
    with _lock:
        USERS_FILE.write_text(json.dumps(u, indent=2))

def load_pricing():
    if not PRICING_FILE.exists():
        save_pricing(DEFAULT_PRICING)
        return DEFAULT_PRICING
    try:
        return json.loads(PRICING_FILE.read_text())
    except Exception:
        return DEFAULT_PRICING

def save_pricing(p):
    with _lock:
        PRICING_FILE.write_text(json.dumps(p, indent=2))

def user_dir(username):
    d = FILES_ROOT / username
    d.mkdir(parents=True, exist_ok=True)
    return d

PROCS = {}

def _reader(username, proc):
    buf = PROCS[username]["logs"]
    try:
        for line in iter(proc.stdout.readline, b""):
            try:
                txt = line.decode("utf-8", errors="replace").rstrip()
            except Exception:
                txt = str(line)
            buf.append(f"[{time.strftime('%H:%M:%S')}] {txt}")
    except Exception as e:
        buf.append(f"[reader-error] {e}")
    finally:
        buf.append(f"[exit] process ended with code {proc.poll()}")

def extract_imports_from_file(fpath):
    """AST ka use karke python file se import kiye gaye modules nikalta hai (jaise httpx, requests)"""
    imports = set()
    try:
        tree = ast.parse(fpath.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        print(f"AST Parse Error: {e}")
    return imports

def start_process(username, filename):
    stop_process(username)
    udir = user_dir(username)
    fpath = udir / filename
    if not fpath.exists():
        return False, "File not found"
    
    ext = fpath.suffix.lower()
    
    if ext == ".py":
        # 🔥 Auto-Detect & Auto-Install Missing Imports for Single Python Files
        required_modules = extract_imports_from_file(fpath)
        stdlib = {
            'os', 'sys', 'json', 'time', 'uuid', 'shutil', 'subprocess', 'threading', 
            'signal', 'secrets', 'pathlib', 'functools', 'collections', 'math', 'random', 
            'datetime', 're', 'urllib', 'http', 'socket', 'sqlite3', 'hashlib', 'base64',
            'ast', 'zipfile', 'logging', 'io', 'csv', 'xml', 'html', 'imaplib', 'smtplib',
            'typing', 'asyncio', 'httpcore', 'email', 'wsgiref', 'uu', 'queue'
        }
        
        missing_modules = [mod for mod in required_modules if mod not in stdlib]
        
        if missing_modules:
            try:
                subprocess.run(["pip", "install"] + missing_modules, cwd=str(udir), check=True, capture_output=True)
            except Exception as e:
                print(f"Auto-install modules error: {e}")

        cmd = ["python", "-u", str(fpath)]
        
    elif ext in (".js", ".mjs", ".cjs"):
        cmd = ["node", str(fpath)]
    elif ext == ".sh":
        cmd = ["bash", str(fpath)]
    else:
        return False, f"Unsupported file type: {ext}"
        
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(udir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1,
        )
    except FileNotFoundError as e:
        return False, f"Runtime not installed: {e}"
        
    logs = deque(maxlen=2000)
    logs.append(f"[start] {' '.join(cmd)}")
    PROCS[username] = {"proc": proc, "logs": logs, "file": filename}
    t = threading.Thread(target=_reader, args=(username, proc), daemon=True)
    t.start()
    PROCS[username]["thread"] = t
    return True, "started"

def stop_process(username):
    info = PROCS.get(username)
    if not info:
        return False
    p = info["proc"]
    if p.poll() is None:
        try:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass
        info["logs"].append("[stop] process terminated")
    return True

def is_running(username):
    info = PROCS.get(username)
    return bool(info and info["proc"].poll() is None)

def get_logs(username):
    info = PROCS.get(username)
    if not info:
        return []
    return list(info["logs"])

INSTALL_LOGS = {}

def run_install(username, command):
    parts = command.strip().split()
    if not parts:
        return False, "empty command"
    if parts[0] not in ("pip", "pip3", "npm"):
        return False, "Only 'pip install <pkg>' or 'npm install <pkg>' allowed"
    if len(parts) < 3 or parts[1] != "install":
        return False, "Format: pip install <module>  OR  npm install <module>"
    logs = INSTALL_LOGS.setdefault(username, deque(maxlen=1000))
    logs.append(f"[install] $ {command}")
    cwd = str(user_dir(username))
    def worker():
        try:
            p = subprocess.Popen(parts, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for line in iter(p.stdout.readline, b""):
                logs.append(line.decode("utf-8", errors="replace").rstrip())
            p.wait()
            logs.append(f"[install] finished with code {p.returncode}")
        except Exception as e:
            logs.append(f"[install-error] {e}")
    threading.Thread(target=worker, daemon=True).start()
    return True, "installing"

def is_owner():
    return session.get("role") == "owner"

def current_user():
    return session.get("username")

def user_valid(username):
    users = load_users()
    u = users.get(username)
    if not u:
        return False, "User not found"
    if u.get("expires_at") and time.time() > u["expires_at"]:
        del users[username]
        save_users(users)
        stop_process(username)
        return False, "Account expired"
    return True, u

def require_owner(f):
    @wraps(f)
    def w(*a, **kw):
        if not is_owner():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return w

def require_user(f):
    @wraps(f)
    def w(*a, **kw):
        u = current_user()
        if not u or session.get("role") != "user":
            return redirect(url_for("login"))
        ok, _ = user_valid(u)
        if not ok:
            session.clear()
            return redirect(url_for("login"))
        return f(*a, **kw)
    return w

# ---------- ROUTES ----------
@app.route("/")
def home():
    if is_owner():
        return redirect(url_for("owner_dashboard"))
    if current_user():
        return redirect(url_for("user_dashboard"))
    return redirect(url_for("landing"))

@app.route("/home")
def landing():
    return render_template("landing.html", pricing=load_pricing())

@app.route("/pricing")
def pricing_page():
    return render_template("pricing.html", pricing=load_pricing())

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if u == OWNER_USER and p == OWNER_PASS:
            session.clear()
            session["role"] = "owner"
            session["username"] = u
            return redirect(url_for("owner_dashboard"))
        users = load_users()
        info = users.get(u)
        if info and info["password"] == p:
            ok, _ = user_valid(u)
            if not ok:
                error = "Account expired"
            else:
                session.clear()
                session["role"] = "user"
                session["username"] = u
                return redirect(url_for("user_dashboard"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route("/auto/<token>")
def auto_login(token):
    users = load_users()
    for uname, info in users.items():
        if info.get("token") == token:
            ok, _ = user_valid(uname)
            if not ok:
                return "Account expired", 403
            session.clear()
            session["role"] = "user"
            session["username"] = uname
            return redirect(url_for("user_dashboard"))
    return "Invalid link", 404

# ---------- EMOJI JSON API FOR USER CREATION / UPDATE ----------
@app.route("/add", methods=["GET", "POST"])
def api_add_user():
    base_url = request.host_url.rstrip("/")
    username = request.args.get("user") or request.form.get("user")
    password = request.args.get("pass") or request.form.get("pass")
    valid_hours = request.args.get("valid") or request.form.get("valid")

    if not username or not password:
        return jsonify({
            "status": "error",
            "emoji": "❌",
            "message": "Username and password parameters are required! (e.g., /add?user=myname&pass=mypass&valid=24)"
        }), 400

    try:
        hours = float(valid_hours) if valid_hours else 24.0
    except ValueError:
        hours = 24.0

    users = load_users()
    is_update = username in users
    
    token = users[username]["token"] if is_update else secrets.token_urlsafe(16)
    expires_at = time.time() + hours * 3600 if hours > 0 else 0

    users[username] = {
        "password": password,
        "created_at": users.get(username, {}).get("created_at", time.time()),
        "expires_at": expires_at,
        "token": token
    }
    save_users(users)
    user_dir(username)

    action_word = "updated" if is_update else "created successfully"
    auto_login_link = f"{base_url}/auto/{token}"

    return jsonify({
        "status": "success",
        "emoji": "🚀",
        "message": f"User '{username}' {action_word} with validity of {hours} hours! 🥳",
        "data": {
            "username": username,
            "password": password,
            "expires_in_hours": hours,
            "auto_login_link": auto_login_link
        }
    })

# ---------- OWNER ROUTES ----------
@app.route("/owner")
@require_owner
def owner_dashboard():
    users = load_users()
    now = time.time()
    base = request.host_url.rstrip("/")
    return render_template("owner.html", users=users, now=now, base_url=base, pricing=load_pricing())

@app.route("/owner/create", methods=["POST"])
@require_owner
def owner_create():
    u = request.form.get("username", "").strip()
    p = request.form.get("password", "").strip()
    try:
        hours = float(request.form.get("hours", "24"))
    except ValueError:
        hours = 24
    if not u or not p or u == OWNER_USER:
        return redirect(url_for("owner_dashboard"))
    users = load_users()
    users[u] = {
        "password": p,
        "created_at": time.time(),
        "expires_at": time.time() + hours * 3600 if hours > 0 else 0,
        "token": secrets.token_urlsafe(16),
    }
    save_users(users)
    user_dir(u)
    return redirect(url_for("owner_dashboard"))

@app.route("/owner/delete/<username>", methods=["POST"])
@require_owner
def owner_delete(username):
    users = load_users()
    if username in users:
        stop_process(username)
        del users[username]
        save_users(users)
        shutil.rmtree(FILES_ROOT / username, ignore_errors=True)
    return redirect(url_for("owner_dashboard"))

@app.route("/owner/extend/<username>", methods=["POST"])
@require_owner
def owner_extend(username):
    try:
        hours = float(request.form.get("hours", "24"))
    except ValueError:
        hours = 24
    users = load_users()
    if username in users:
        base = max(users[username].get("expires_at") or time.time(), time.time())
        users[username]["expires_at"] = base + hours * 3600
        save_users(users)
    return redirect(url_for("owner_dashboard"))

@app.route("/owner/pricing", methods=["POST"])
@require_owner
def owner_pricing():
    pricing = load_pricing()
    pricing["currency"] = request.form.get("currency", "₹").strip() or "₹"
    pricing["contact"] = request.form.get("contact", "").strip()
    plans, names, durs, prices, feats = [], request.form.getlist("p_name"), request.form.getlist("p_duration"), request.form.getlist("p_price"), request.form.getlist("p_features")
    for i in range(len(names)):
        if not names[i].strip(): continue
        plans.append({"name": names[i].strip(), "duration": durs[i].strip() if i < len(durs) else "", "price": prices[i].strip() if i < len(prices) else "0", "features": feats[i].strip() if i < len(feats) else ""})
    pricing["plans"] = plans
    save_pricing(pricing)
    return redirect(url_for("owner_dashboard") + "#pricing")

# ---------- USER DASHBOARD & ZIP AUTO-EXTRACT & INSTALLER ----------
@app.route("/dashboard")
@require_user
def user_dashboard():
    u = current_user()
    info = load_users().get(u, {})
    files = sorted([f.name for f in user_dir(u).iterdir() if f.is_file()])
    return render_template("user.html", username=u, info=info, files=files, running=is_running(u), running_file=(PROCS.get(u, {}).get("file") if is_running(u) else None), expires_at=info.get("expires_at", 0), now=time.time())

@app.route("/upload", methods=["POST"])
@require_user
def upload():
    u = current_user()
    udir = user_dir(u)
    files = request.files.getlist("files")
    
    for f in files:
        if not f or not f.filename: continue
        name = secure_filename(f.filename)
        if not name: continue
        
        save_path = udir / name
        f.save(save_path)
        
        # ZIP Auto-Extraction Logic
        if name.endswith(".zip"):
            try:
                with zipfile.ZipFile(save_path, 'r') as zip_ref:
                    zip_ref.extractall(udir)
                os.remove(save_path)
            except Exception as e:
                print(f"Zip extraction error: {e}")
                
        # requirements.txt auto-install logic
        req_file = udir / "requirements.txt"
        if req_file.exists():
            try:
                subprocess.Popen(["pip", "install", "-r", str(req_file)], cwd=str(udir))
            except Exception as e:
                print(f"Auto-install requirements error: {e}")

    return redirect(url_for("user_dashboard"))

@app.route("/file/delete/<name>", methods=["POST"])
@require_user
def file_delete(name):
    p = user_dir(current_user()) / secure_filename(name)
    if p.exists() and p.is_file(): p.unlink()
    return redirect(url_for("user_dashboard"))

@app.route("/file/view/<name>")
@require_user
def file_view(name):
    return send_from_directory(user_dir(current_user()), secure_filename(name), as_attachment=False)

@app.route("/server/start", methods=["POST"])
@require_user
def server_start():
    ok, msg = start_process(current_user(), secure_filename(request.form.get("file", "")))
    return jsonify({"ok": ok, "msg": msg})

@app.route("/server/stop", methods=["POST"])
@require_user
def server_stop():
    stop_process(current_user())
    return jsonify({"ok": True})

@app.route("/server/restart", methods=["POST"])
@require_user
def server_restart():
    u = current_user()
    info = PROCS.get(u)
    fname = info["file"] if info else secure_filename(request.form.get("file", ""))
    if not fname: return jsonify({"ok": False, "msg": "no file"})
    stop_process(u)
    time.sleep(0.3)
    ok, msg = start_process(u, fname)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/server/delete", methods=["POST"])
@require_user
def server_delete():
    u = current_user()
    stop_process(u)
    PROCS.pop(u, None)
    return jsonify({"ok": True})

@app.route("/logs")
@require_user
def logs_api():
    u = current_user()
    return jsonify({"running": is_running(u), "file": PROCS.get(u, {}).get("file"), "logs": get_logs(u), "install": list(INSTALL_LOGS.get(u, []))})

@app.route("/install", methods=["POST"])
@require_user
def install():
    ok, msg = run_install(current_user(), request.form.get("command", "").strip())
    return jsonify({"ok": ok, "msg": msg})

@app.route("/healthz")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
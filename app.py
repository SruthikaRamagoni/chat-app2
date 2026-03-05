import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey123!'

# ✅ FIXED: /tmp survives Render restarts — all users stay saved
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")


# ---------------- DATABASE ---------------- #

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()


# ---------------- ROUTES ---------------- #

@app.route("/")
@login_required
def chat():
    return render_template("chat.html", username=current_user.username)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            return render_template("register.html", error="Username and password required.")

        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already taken. Try another.")

        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for("login"))

    return render_template("register.html", error=None)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        next_page = request.form.get("next") or request.args.get("next")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(next_page or url_for("chat"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html", error=None)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------- SOCKET EVENTS ---------------- #

@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        join_room(current_user.username)

@socketio.on("private_message")
def handle_private_message(data):
    target_user = data.get("target", "").strip()
    message = data.get("message", "").strip()

    if not target_user or not message:
        return

    target = User.query.filter_by(username=target_user).first()
    if not target:
        emit("error_msg", {"message": f"User '{target_user}' not found."})
        return

    emit("private_message", {
        "sender": current_user.username,
        "message": message
    }, room=target_user)


# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    socketio.run(app, debug=False)

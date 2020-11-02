import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
# db = SQL("sqlite:///finance.db")
db = SQL("postgres://pidjnvvssnwpuo:555e49aa2554f2f9d7414faf5b2dcd8f990d98aa846b173cbae1f0bc014c04d5@ec2-3-210-23-22.compute-1.amazonaws.com:5432/da8gk85auqkp45")

# Make sure API key is set
# if not os.environ.get("API_KEY"):
#     raise RuntimeError("API_KEY not set")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query db for cash and portfolio
    cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    rows = db.execute("SELECT symbol, SUM(shares) AS shares FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])

    # Remove stocks with 0 shares
    rows = [i for i in rows if (i["shares"] > 0)]

    # Check current stock prices and make calculations
    total = cash[0]["cash"]
    for row in rows:
        current = lookup(row["symbol"])
        row["name"] = current["name"]
        row["price"] = usd(current["price"])
        row["sum"] = usd(row["shares"] * current["price"])
        total += (row["shares"] * current["price"])

    return render_template("index.html", rows=rows, cash=usd(cash[0]["cash"]), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    else:

        # Set variables
        user = session["user_id"]
        symbol = request.form.get("symbol").lower()
        shares = request.form.get("shares")

        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide a symbol", 403)

        # Ensure symbol is valid
        if not lookup(symbol):
            return apology("symbol is not valid", 403)

        # Ensure positive integer was submitted
        try:
            if int(shares) <= 0:
                return apology("must provide a positive number", 403)
        except ValueError:
            return apology("must provide an integer", 403)

        # Check stock's current price and user's cash
        res = lookup(symbol)
        data = db.execute("SELECT cash FROM users WHERE id=?", user)
        balance = data[0]["cash"] - res["price"] * int(shares)
        if balance < 0:
            return apology("insufficient funds", 403)

        # Insert transaction in db
        db.execute("INSERT INTO transactions (user_id, time, symbol, price, shares) VALUES (:user_id, :time, :symbol, :price, :shares)",
                    user_id=user, time=datetime.now(), symbol=symbol, price=res["price"], shares=shares)

        # Update user's cash
        db.execute("UPDATE users SET cash=? WHERE id=?", balance, user)

        # Redirect user to index page
        return redirect("/")


@app.route("/buy/<symbol>")
@login_required
def indexbuy(symbol):
    """Buy shares of stock"""
    return render_template("buy.html", symbol=symbol)



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query db for transactions
    rows = db.execute("SELECT symbol, shares, price, time FROM transactions WHERE user_id=? ORDER BY time DESC", session["user_id"])

    # Convert prices in USD
    for row in rows:
        row["price"] = usd(row["price"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        res = lookup(request.form.get("symbol"))

        if not res:
            return apology("symbol is not valid", 403)

        label = res["name"] + " (" + res["symbol"] + ")"
        price = usd(res["price"])

        return render_template("quoted.html", label=label, price=price)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        # Ensure both passwords match
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords do not match", 403)

        # Set variables
        username = request.form.get("username")
        password = request.form.get("password")
        hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)

        # Ensure username is not taken
        if len(rows) == 1 :
            return apology("username already exists", 403)

        # Create user in db
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

        # Redirect user to login form
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    rows = db.execute("SELECT DISTINCT symbol, SUM(shares) AS shares FROM transactions WHERE user_id=? GROUP BY symbol", session["user_id"])
    rows = [i for i in rows if (i["shares"] > 0)]

    if request.method == "GET":
        return render_template("sell.html", rows=rows)
    else:

        # Set variables
        user = session["user_id"]
        symbol = request.form.get("symbol").lower()
        shares = request.form.get("shares")

        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide a symbol", 403)

        # Ensure shares was submitted
        if not shares:
            return apology("must provide number of shares", 403)

        # Ensure positive integer was submitted
        try:
            if int(shares) <= 0:
                return apology("must provide a positive number", 403)
        except ValueError:
            return apology("must provide an integer", 403)

        # Ensure user owns enough shares
        for row in rows:
            if row["symbol"] == symbol and int(shares) > row["shares"]:
                return apology("not enough shares", 403)

        # Insert transaction in db
        res = lookup(symbol)
        shares = int(shares) * -1
        db.execute("INSERT INTO transactions (user_id, time, symbol, price, shares) VALUES (:user_id, :time, :symbol, :price, :shares)",
                    user_id=user, time=datetime.now(), symbol=symbol, price=res["price"], shares=shares)

        # Update user's cash
        cash = db.execute("SELECT cash FROM users WHERE id=?", user)
        balance = cash[0]["cash"] - (shares * res["price"])
        db.execute("UPDATE users SET cash=? WHERE id=?", balance, user)

        return redirect("/")


@app.route("/sell/<symbol>")
@login_required
def indexsell(symbol):
    """Sell shares of stock"""

    if request.method == "GET":
        return render_template("sell.html", symbol=symbol)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

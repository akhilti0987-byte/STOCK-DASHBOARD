import base64
import os
from io import BytesIO

import yfinance as yf
from flask import Flask, Response, jsonify, render_template, request
from matplotlib.figure import Figure   # Figure (not pyplot) is safe for web servers

app = Flask(__name__)

# Optional password: only active when APP_USER and APP_PASS are set (e.g. on Render)
@app.before_request
def require_password():
    user, pw = os.environ.get("APP_USER"), os.environ.get("APP_PASS")
    if not user or not pw:
        return None
    auth = request.authorization
    if auth and auth.username == user and auth.password == pw:
        return None
    return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="Stocks"'})

# period -> candle interval
PERIODS = {"1d": "5m", "5d": "15m", "1mo": "1d", "3mo": "1d",
           "6mo": "1d", "1y": "1d", "5y": "1wk"}

# A few popular stocks for instant suggestions
POPULAR = [
    ("RELIANCE.NS", "Reliance Industries"), ("TCS.NS", "Tata Consultancy Services"),
    ("INFY.NS", "Infosys"), ("HDFCBANK.NS", "HDFC Bank"), ("ICICIBANK.NS", "ICICI Bank"),
    ("SBIN.NS", "State Bank of India"), ("BHARTIARTL.NS", "Bharti Airtel"),
    ("ITC.NS", "ITC Limited"), ("LT.NS", "Larsen & Toubro"), ("WIPRO.NS", "Wipro"),
    ("MARUTI.NS", "Maruti Suzuki"), ("TATAMOTORS.NS", "Tata Motors"),
    ("TATASTEEL.NS", "Tata Steel"), ("ADANIENT.NS", "Adani Enterprises"),
    ("TITAN.NS", "Titan Company"), ("ZOMATO.NS", "Zomato"), ("IRCTC.NS", "IRCTC"),
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"),
    ("GOOGL", "Alphabet (Google)"), ("AMZN", "Amazon"), ("TSLA", "Tesla"),
    ("META", "Meta Platforms"), ("NFLX", "Netflix"),
]


def local_matches(query):
    q = query.lower()
    return [(s, n) for s, n in POPULAR if q in s.lower() or q in n.lower()]


def yahoo_matches(query, limit=5):
    try:
        quotes = yf.Search(query, max_results=limit).quotes
    except Exception:
        return []
    return [(q["symbol"], q.get("shortname", "")) for q in quotes if q.get("symbol")]


# ---------------- Simple matplotlib charts ----------------
def to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return base64.b64encode(buf.getvalue()).decode()


def make_chart(title, labels, kind, values, color, extra_lines=None):
    """One helper for every chart: kind is 'line' or 'bar'."""
    fig = Figure(figsize=(10, 4))
    ax = fig.subplots()
    x = range(len(values))            # plot by position -> no gaps for weekends

    if kind == "line":
        ax.plot(x, values, color=color, label="Close")
        for name, series, line_color in (extra_lines or []):
            ax.plot(x, series, color=line_color, label=name)
        ax.legend()
    else:
        ax.bar(x, values, color=color)

    step = max(1, len(labels) // 6)   # show about 6 labels on the x-axis
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(labels[::step], fontsize=8)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    return to_base64(fig)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    results = [{"symbol": s, "name": n} for s, n in local_matches(query)]
    if len(results) < 6 and len(query) >= 2:
        seen = {r["symbol"] for r in results}
        for s, n in yahoo_matches(query):
            if s not in seen:
                results.append({"symbol": s, "name": n})
    return jsonify(results[:8])


@app.route("/api/stock")
def get_stock():
    ticker = request.args.get("ticker", "").strip().upper()
    period = request.args.get("period", "1mo")

    if not ticker:
        return jsonify({"error": "Please enter a stock symbol."}), 400
    if period not in PERIODS:
        return jsonify({"error": "Invalid period."}), 400

    try:
        data = yf.Ticker(ticker).history(period=period, interval=PERIODS[period])

        # If user typed a name (e.g. "reliance"), try to find the symbol
        if data.empty and "." not in ticker:
            found = local_matches(ticker) or yahoo_matches(ticker, 1)
            if found:
                ticker = found[0][0]
                data = yf.Ticker(ticker).history(period=period, interval=PERIODS[period])

        if data.empty:
            return jsonify({"error": f"No data found for {ticker}."}), 404

        data = data.dropna(subset=["Close"])
        close = data["Close"]
        fmt = "%d %b %H:%M" if period in ("1d", "5d") else "%d %b %Y"
        labels = [d.strftime(fmt) for d in data.index]

        # Day change from the last two daily candles
        daily = yf.Ticker(ticker).history(period="5d", interval="1d").dropna(subset=["Close"])
        change = change_percent = volume = None
        if len(daily) >= 2:
            prev = float(daily["Close"].iloc[-2])
            change = float(daily["Close"].iloc[-1]) - prev
            change_percent = change / prev * 100
        if len(daily) >= 1:
            volume = int(daily["Volume"].iloc[-1])

        # Charts
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        returns = (close.pct_change() * 100).fillna(0)
        return_colors = ["green" if r >= 0 else "red" for r in returns]

        charts = {
            "price": make_chart(f"{ticker} - closing price", labels, "line", close, "teal",
                                [("20-period avg", ma20, "orange"), ("50-period avg", ma50, "red")]),
            "volume": make_chart("Trading volume", labels, "bar", data["Volume"], "steelblue"),
            "returns": make_chart("Price returns (%)", labels, "bar", returns, return_colors),
        }

        return jsonify({
            "ticker": ticker,
            "latest_price": float(close.iloc[-1]),
            "change": change,
            "change_percent": change_percent,
            "high": float(data["High"].max()),
            "low": float(data["Low"].min()),
            "volume": volume,
            "last_updated": data.index[-1].strftime("%d %b %Y, %H:%M"),
            "charts": charts,
        })
    except Exception:
        app.logger.exception("Stock request failed")
        return jsonify({"error": "Unable to fetch stock data right now. Try again."}), 502


if __name__ == "__main__":
    app.run(debug=True, port=5000)

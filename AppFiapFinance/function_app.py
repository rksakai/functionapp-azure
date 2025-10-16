# __init__.py
import azure.functions as func
import yfinance as yf
import time

app = func.FunctionApp()

SYMBOLS = ["PETR4.SA", "BBAS3.SA", "ITUB4.SA"]  # Ouro, Petróleo, Prata

def fetch_last_price(sym: str, retries: int = 3, pause: float = 0.8):
    for i in range(retries):
        try:
            df = yf.download(sym, period="1d", interval="1m", progress=False)
            if df is not None and not df.empty:
                return float(df["Close"].iloc[-1])
            # Fallback diário
            df = yf.download(sym, period="5d", interval="1d", progress=False)
            if df is not None and not df.empty:
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
        time.sleep(pause * (1.6 ** i))  # backoff
    return None

@app.function_name(name="CommoditiesSimple")
@app.route(route="commodities", auth_level=func.AuthLevel.ANONYMOUS)
def commodities(req: func.HttpRequest) -> func.HttpResponse:
    rows = []
    for sym in SYMBOLS:
        price = fetch_last_price(sym)
        rows.append((sym, price))

    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Commodities</title></head><body>",
        "<h1>Últimos preços (USD)</h1>",
        "<ul>",
    ]
    for sym, price in rows:
        val = "n/d" if price is None else f"{price:.2f} USD"
        html.append(f"<li>{sym}: {val}</li>")
    html.append("</ul></body></html>")

    return func.HttpResponse("\n".join(html), status_code=200, mimetype="text/html")


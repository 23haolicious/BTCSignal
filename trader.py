import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
from flask import Flask, render_template, request
import pandas as pd
from binance.client import Client
import ta
import matplotlib.pyplot as plt
import io
import base64

# Rest of your Flask app code remains unchanged


app = Flask(__name__)

# Replace with your Binance API key and secret
API_KEY = "XXXX-XXXXXX-XXXX-XXXX-XXXX"
API_SECRET = "XXXX-XXXXXX-XXXX-XXXX-XXXX"

client = Client(API_KEY, API_SECRET)

def fetch_data_in_chunks(client, symbol, interval, start_time, end_time):
    """Fetch historical data in chunks to cover long timeframes."""
    data = []
    start_time_ms = int(pd.Timestamp(start_time).timestamp() * 1000)
    end_time_ms = int(pd.Timestamp(end_time).timestamp() * 1000)

    while start_time_ms < end_time_ms:
        candles = client.get_klines(
            symbol=symbol,
            interval=interval,
            startTime=start_time_ms,
            endTime=end_time_ms,
            limit=1000  # Binance max limit per request
        )
        if not candles:
            break

        data.extend(candles)
        start_time_ms = candles[-1][6]  # Use the close time of the last candle

    return data

@app.route('/', methods=['GET', 'POST'])
def index():
    chart_url = None
    signals = []
    total_profit = 0
    asset_to_sell = None

    if request.method == 'POST':
        interval = request.form.get('interval', '4h')
        budget = float(request.form.get('budget', 1000))  # Default budget is 1000 USD if not provided
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        try:
            # Fetch data in chunks
            candles = fetch_data_in_chunks(client, "BTCUSDT", interval, start_time, end_time)

            # Create DataFrame
            df = pd.DataFrame(candles, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
                'taker_buy_quote_asset_volume', 'ignore'
            ])

            if df.empty:
                signals.append("No data available for the selected time range.")
            else:
                # Preprocess data
                df['close'] = pd.to_numeric(df['close'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)

                # Calculate RSI
                df['RSI'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()

                # Initialize state and signal tracking
                state = "WAIT_BUY"
                last_buy_price = None
                buy_signals = []
                sell_signals = []
                btc_owned = 0  # Track BTC owned based on the budget
                rsi_buy_condition = float(request.form.get('rsi_buy_condition', 30))  # Default is 30
                sell_percentage = float(request.form.get('sell_percentage', 1))  # Default is 1%

                for index, row in df.iterrows():
                    if state == "WAIT_BUY" and row['RSI'] <= rsi_buy_condition:
                        # Trigger a BUY signal
                        btc_owned = budget / row['close']  # Calculate BTC to buy
                        last_buy_price = row['close']
                        buy_signals.append((index, last_buy_price))
                        signals.append(f"BUY Signal: {index} | Price: ${last_buy_price:,.2f} | RSI: {row['RSI']:,.2f}")
                        state = "WAIT_SELL"


                    elif state == "WAIT_SELL":
                        # Check if RSI >= 70 or the price is 1% greater than the last BUY price
                        # if row['RSI'] >= 70 and row['close'] > last_buy_price:
                        #     # SELL based on RSI >= 70
                        #     last_sell_price = row['close']
                        #     sell_signals.append((index, last_sell_price))
                        #     profit = btc_owned * (last_sell_price - last_buy_price)  # Calculate profit
                        #     total_profit += profit
                        #     signals.append(
                        #         f"SELL Signal (RSI): {index} | Price: ${last_sell_price:.2f} | Profit: ${profit:.2f}")
                        #     state = "WAIT_BUY"

                        if row['close'] >= last_buy_price * (1 + sell_percentage / 100):
                            # SELL based on price being user-defined % greater than BUY price
                            last_sell_price = row['close']
                            sell_signals.append((index, last_sell_price))
                            profit = btc_owned * (last_sell_price - last_buy_price)  # Calculate profit
                            total_profit += profit
                            signals.append(
                                f"SELL Signal (Price): {index} | Price: ${last_sell_price:,.2f} | Profit: ${profit:,.2f}")
                            state = "WAIT_BUY"

                # Visualization
                plt.figure(figsize=(25, 15))  # Increase figure size
                plt.plot(df.index, df['close'], label="BTC Price", alpha=0.6)
                if buy_signals:
                    plt.scatter(*zip(*buy_signals), color="green", label="BUY Signal", marker="^", alpha=1)
                if sell_signals:
                    plt.scatter(*zip(*sell_signals), color="red", label="SELL Signal", marker="v", alpha=1)

                # Add annotations for prices
                for x, y in buy_signals:
                    plt.annotate(f"${y:.2f}", (x, y), textcoords="offset points", xytext=(0, 10), ha="center",
                                 color="green")
                for x, y in sell_signals:
                    plt.annotate(f"${y:.2f}", (x, y), textcoords="offset points", xytext=(0, -20), ha="center",
                                 color="red")

                plt.title("BTC Price with RSI-Based BUY/SELL Signals")
                plt.xlabel("Date")
                plt.ylabel("Price (USDT)")
                plt.legend()
                plt.grid(True)

                # Save plot to a string buffer
                img = io.BytesIO()
                plt.savefig(img, format='png', bbox_inches="tight")  # Ensures entire chart fits within image
                img.seek(0)
                chart_url = base64.b64encode(img.getvalue()).decode('utf8')
                plt.close()


        except Exception as e:
            signals.append(f"Error: {str(e)}")

    formatted_total_profit = f"{total_profit:,.2f}"
    return render_template('index.html', chart_url=chart_url, signals=signals, total_profit=formatted_total_profit)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

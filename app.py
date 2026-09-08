import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# Streamlit Page Config
st.set_page_config(
    page_title="Supply & Demand Trade Journal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# File paths for local/persistent storage
DB_FILE = "trade_history.csv"

# Contract Multipliers mapping
MULTIPLIERS = {
    "MNQ": 2.0,   # Micro Nasdaq
    "NQ": 20.0,   # E-mini Nasdaq
    "MES": 5.0,   # Micro S&P
    "ES": 50.0,   # E-mini S&P
    "M2K": 5.0,   # Micro Russell
    "RTY": 50.0,  # E-mini Russell
    "MGC": 10.0,  # Micro Gold
    "GC": 100.0,  # Gold
    "SIL": 1000.0 # Micro Silver
}

def get_multiplier(symbol):
    clean_sym = ''.join([c for c in str(symbol) if not c.isdigit()]).upper()
    for key in MULTIPLIERS:
        if clean_sym.startswith(key):
            return MULTIPLIERS[key]
    return 1.0

def load_trade_db():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    else:
        return pd.DataFrame(columns=[
            'Trade ID', 'Date', 'Symbol', 'Side', 'Zone Type', 'Timeframe', 
            'Qty', 'Entry Time', 'Exit Time', 'Entry Price', 'Exit Price', 
            'Planned SL', 'Planned TP', 'Exit Reason', 'Planned Risk ($)', 
            'Planned Reward ($)', 'Gross PnL ($)', 'Net PnL ($)', 'Notes'
        ])

def save_trade_db(df):
    df.to_csv(DB_FILE, index=False)

def parse_tradovate_csv(orders_df, account_df=None):
    """
    Matches filled entry orders with filled exit orders to reconstruct trades.
    """
    filled = orders_df[orders_df['Status'] == 'Filled'].copy()
    if filled.empty:
        return []

    filled['Update Time'] = pd.to_datetime(filled['Update Time'])
    filled = filled.sort_values('Update Time')

    trades = []
    
    # Simple pairing engine for single contract bracket orders
    open_positions = []

    for idx, row in filled.iterrows():
        order_type = str(row['Type'])
        side = str(row['Side'])
        symbol = str(row['Symbol'])
        price = float(row['Avg Fill Price'])
        time = row['Update Time']
        qty = float(row['Qty'])
        mult = get_multiplier(symbol)

        # Entry Order (Limit or Market)
        if order_type in ['Limit', 'Market']:
            open_positions.append({
                'symbol': symbol,
                'side': 'Long' if side == 'Buy' else 'Short',
                'entry_price': price,
                'entry_time': time,
                'qty': qty,
                'multiplier': mult,
                'order_id': row['Order ID']
            })
        
        # Exit Order (Stop Loss or Take Profit)
        elif order_type in ['Stop Loss', 'Take Profit'] and open_positions:
            # Match with earliest open position of same symbol
            pos_idx = next((i for i, p in enumerate(open_positions) if p['symbol'] == symbol), None)
            if pos_idx is not None:
                pos = open_positions.pop(pos_idx)
                
                # Determine PnL
                if pos['side'] == 'Short':
                    pnl_pts = pos['entry_price'] - price
                else:
                    pnl_pts = price - pos['entry_price']
                
                gross_pnl = pnl_pts * mult * qty
                
                # Estimate commissions ~$1.90 roundtrip per micro contract
                comm = 1.90 * qty
                net_pnl = gross_pnl - comm

                trades.append({
                    'Trade ID': f"{time.strftime('%Y%m%d%H%M%S')}_{symbol}",
                    'Date': time.strftime('%Y-%m-%d'),
                    'Symbol': symbol,
                    'Side': pos['side'],
                    'Zone Type': 'Supply Zone' if pos['side'] == 'Short' else 'Demand Zone',
                    'Timeframe': '15m',
                    'Qty': qty,
                    'Entry Time': pos['entry_time'].strftime('%H:%M:%S'),
                    'Exit Time': time.strftime('%H:%M:%S'),
                    'Entry Price': pos['entry_price'],
                    'Exit Price': price,
                    'Planned SL': price if order_type == 'Stop Loss' else 0.0,
                    'Planned TP': price if order_type == 'Take Profit' else 0.0,
                    'Exit Reason': order_type,
                    'Planned Risk ($)': abs(pos['entry_price'] - price) * mult * qty if order_type == 'Stop Loss' else 30.0,
                    'Planned Reward ($)': abs(price - pos['entry_price']) * mult * qty if order_type == 'Take Profit' else 90.0,
                    'Gross PnL ($)': gross_pnl,
                    'Net PnL ($)': net_pnl,
                    'Notes': 'Auto-parsed from Tradovate export'
                })

    return trades

# Load Master DB
db = load_trade_db()

# --- SIDEBAR & AUTH ---
st.sidebar.title("📈 S&D Trading Journal")
password = st.sidebar.text_input("Enter Passcode", type="password")

# Passcode check (Change "supplydemand123" to your preferred password)
if password != "supplydemand123":
    st.title("🔒 Supply & Demand Trade Journal")
    st.info("Please enter the passcode in the sidebar to access your trade dashboard.")
    st.stop()

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["Dashboard", "Import Tradovate CSV", "Trade Log History", "Strategy Analytics"])

# --- TAB 1: DASHBOARD ---
if menu == "Dashboard":
    st.title("📊 Supply & Demand Performance Dashboard")
    
    if db.empty:
        st.warning("No trade data found. Please go to 'Import Tradovate CSV' to upload your trades.")
    else:
        # Top KPI Cards
        col1, col2, col3, col4, col5 = st.columns(5)
        
        total_pnl = db['Net PnL ($)'].sum()
        total_trades = len(db)
        wins = db[db['Net PnL ($)'] > 0]
        losses = db[db['Net PnL ($)'] < 0]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = wins['Net PnL ($)'].sum()
        gross_loss = abs(losses['Net PnL ($)'].sum())
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else gross_profit

        avg_win = wins['Net PnL ($)'].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses['Net PnL ($)'].mean()) if len(losses) > 0 else 0
        payout_ratio = (avg_win / avg_loss) if avg_loss > 0 else avg_win

        col1.metric("Net Cumulative P&L", f"${total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
        col2.metric("Win Rate", f"{win_rate:.1f}%")
        col3.metric("Profit Factor", f"{profit_factor:.2f}")
        col4.metric("Avg Risk:Reward", f"1 : {payout_ratio:.2f}")
        col5.metric("Total Trades Logged", total_trades)

        st.markdown("---")

        # Equity Curve Chart
        st.subheader("📈 Cumulative Equity Curve")
        db_sorted = db.sort_values('Date').copy()
        db_sorted['Cumulative Net PnL'] = db_sorted['Net PnL ($)'].cumsum()
        
        fig_equity = px.line(
            db_sorted, 
            x='Date', 
            y='Cumulative Net PnL', 
            markers=True,
            labels={'Cumulative Net PnL': 'Net P&L ($)', 'Date': 'Date'},
            title="Equity Growth Over Time"
        )
        fig_equity.update_traces(line_color='#2962FF', line_width=3)
        st.plotly_chart(fig_equity, use_container_width=True)

        # Breakdowns
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.subheader("🎯 Performance by Zone Type")
            zone_perf = db.groupby('Zone Type')['Net PnL ($)'].agg(['sum', 'count']).reset_index()
            fig_zone = px.bar(
                zone_perf, 
                x='Zone Type', 
                y='sum', 
                color='Zone Type',
                labels={'sum': 'Net P&L ($)'},
                color_discrete_map={'Supply Zone': '#FF5252', 'Demand Zone': '#00E676'}
            )
            st.plotly_chart(fig_zone, use_container_width=True)

        with col_b:
            st.subheader("📊 Win / Loss Breakdown")
            exit_reasons = db['Exit Reason'].value_counts().reset_index()
            fig_pie = px.pie(
                exit_reasons, 
                names='Exit Reason', 
                values='count', 
                hole=0.4,
                color_discrete_sequence=['#00E676', '#FF5252', '#FFD600']
            )
            st.plotly_chart(fig_pie, use_container_width=True)

# --- TAB 2: IMPORT TRADOVATE CSV ---
elif menu == "Import Tradovate CSV":
    st.title("📥 Import Tradovate Daily CSV Data")
    st.write("Upload your `tradovate-orders-all-*.csv` file below to automatically extract filled trades and calculate metrics.")

    uploaded_file = st.file_uploader("Choose a Tradovate Orders CSV file", type=['csv'])

    if uploaded_file is not None:
        try:
            orders_df = pd.read_csv(uploaded_file)
            st.success("File uploaded successfully! Parsing execution log...")
            
            parsed_trades = parse_tradovate_csv(orders_df)

            if not parsed_trades:
                st.warning("No filled entries/exits matched in this CSV file.")
            else:
                parsed_df = pd.DataFrame(parsed_trades)
                st.subheader("Preview Parsed Trades")
                st.dataframe(parsed_df)

                if st.button("💾 Append & Save Trades to Master Database"):
                    # Avoid duplicate records by checking Trade ID
                    existing_ids = set(db['Trade ID']) if not db.empty else set()
                    new_trades = [t for t in parsed_trades if t['Trade ID'] not in existing_ids]

                    if not new_trades:
                        st.info("All trades in this file are already saved in your database.")
                    else:
                        new_df = pd.DataFrame(new_trades)
                        updated_db = pd.concat([db, new_df], ignore_index=True)
                        save_trade_db(updated_db)
                        st.success(f"Successfully added {len(new_trades)} new trade(s) to your journal!")
                        st.balloons()

        except Exception as e:
            st.error(f"Error parsing file: {e}")

# --- TAB 3: TRADE LOG HISTORY ---
elif menu == "Trade Log History":
    st.title("📖 Complete Trade Log & Zone Tagging")
    st.write("Review, edit, or tag zone details (timeframes, strategy notes) for all logged trades.")

    if db.empty:
        st.warning("No trade records available.")
    else:
        edited_df = st.data_editor(
            db, 
            num_rows="dynamic",
            use_container_width=True
        )

        if st.button("💾 Save Edits"):
            save_trade_db(edited_df)
            st.success("Trade log updated successfully!")

# --- TAB 4: STRATEGY ANALYTICS ---
elif menu == "Strategy Analytics":
    st.title("🔬 Supply & Demand Strategy Analysis")
    
    if db.empty:
        st.warning("No trade data available for analysis.")
    else:
        st.subheader("Distribution of Trade Results ($)")
        fig_hist = px.histogram(db, x='Net PnL ($)', nbins=15, color='Zone Type', marginal="box")
        st.plotly_chart(fig_hist, use_container_width=True)

        st.subheader("Risk vs. Realized Reward")
        fig_scatter = px.scatter(
            db, 
            x='Planned Risk ($)', 
            y='Net PnL ($)', 
            color='Side', 
            size='Qty', 
            hover_data=['Symbol', 'Date', 'Notes']
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
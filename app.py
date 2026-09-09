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

# File paths for persistent storage
DB_FILE = "trade_history.csv"

# Contract Multipliers mapping
MULTIPLIERS = {
    "MNQ": 2.0,   # Micro Nasdaq ($2/pt)
    "NQ": 20.0,   # E-mini Nasdaq ($20/pt)
    "MES": 5.0,   # Micro S&P ($5/pt)
    "ES": 50.0,   # E-mini S&P ($50/pt)
    "M2K": 5.0,   # Micro Russell ($5/pt)
    "RTY": 50.0,  # E-mini Russell ($50/pt)
    "MGC": 10.0,  # Micro Gold ($10/pt)
    "GC": 100.0,  # Gold ($100/pt)
    "SIL": 1000.0 # Micro Silver
}

def get_multiplier(symbol):
    clean_sym = ''.join([c for c in str(symbol) if not c.isdigit()]).upper()
    for key in MULTIPLIERS:
        if clean_sym.startswith(key):
            return MULTIPLIERS[key]
    return 1.0

def create_empty_trade_df():
    return pd.DataFrame(columns=[
        'Trade ID', 'Date', 'Symbol', 'Side', 'Zone Type', 'Timeframe', 
        'Qty', 'Entry Time', 'Exit Time', 'Entry Price', 'Exit Price', 
        'Planned SL', 'Planned TP', 'Exit Reason', 'Planned Risk ($)', 
        'Planned Reward ($)', 'Gross PnL ($)', 'Net PnL ($)', 'Notes'
    ])

def load_trade_db():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE)
            if not df.empty and 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                df['Date'] = df['Date'].fillna(pd.Timestamp.now().strftime('%Y-%m-%d'))
            return df
        except pd.errors.EmptyDataError:
            return create_empty_trade_df()
    return create_empty_trade_df()

def save_trade_db(df):
    df.to_csv(DB_FILE, index=False)

def parse_tradovate_multi_files(files_dict):
    orders_df = files_dict.get('orders')
    account_df = files_dict.get('account')

    if orders_df is None or orders_df.empty:
        return [], None

    orders_df['Update Time'] = pd.to_datetime(orders_df['Update Time'])
    filled = orders_df[orders_df['Status'] == 'Filled'].sort_values('Update Time').copy()

    trades = []
    open_positions = []

    for idx, row in filled.iterrows():
        order_type = str(row['Type'])
        side = str(row['Side'])
        symbol = str(row['Symbol'])
        price = float(row['Avg Fill Price'])
        time = row['Update Time']
        qty = float(row['Qty'])
        mult = get_multiplier(symbol)

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
        elif order_type in ['Stop Loss', 'Take Profit'] and open_positions:
            pos_idx = next((i for i, p in enumerate(open_positions) if p['symbol'] == symbol), None)
            if pos_idx is not None:
                pos = open_positions.pop(pos_idx)
                
                if pos['side'] == 'Short':
                    pnl_pts = pos['entry_price'] - price
                else:
                    pnl_pts = price - pos['entry_price']
                
                gross_pnl = pnl_pts * mult * qty
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
                    'Notes': 'Imported from Tradovate CSV'
                })

    account_metrics = None
    if account_df is not None and not account_df.empty:
        account_metrics = {
            'Total P/L': float(account_df['Total P/L'].iloc[0]) if 'Total P/L' in account_df.columns else 0.0,
            'Net Liq': float(account_df['Net Liq'].iloc[0]) if 'Net Liq' in account_df.columns else 0.0,
            'Available Margin': float(account_df['Available Margin'].iloc[0]) if 'Available Margin' in account_df.columns else 0.0
        }

    return trades, account_metrics

# Load Master DB
db = load_trade_db()

# --- SIDEBAR & AUTH ---
st.sidebar.title("📈 S&D Trading Journal")
password = st.sidebar.text_input("Enter Passcode", type="password")

if password != "supplydemand123":
    st.title("🔒 Supply & Demand Trade Journal")
    st.info("Please enter the passcode in the sidebar to access your trade dashboard.")
    st.stop()

# --- NAVIGATION ---
menu = st.sidebar.radio("Navigation", ["Dashboard", "Import Multiple CSVs", "Trade Log History", "Strategy Analytics"])

# --- TAB 1: DASHBOARD ---
if menu == "Dashboard":
    st.title("📊 Supply & Demand Performance Dashboard")
    
    if db.empty:
        st.warning("No trade data found. Please go to 'Import Multiple CSVs' to upload your files.")
    else:
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

# --- TAB 2: IMPORT MULTIPLE CSVS ---
elif menu == "Import Multiple CSVs":
    st.title("📥 Import Tradovate Session Data")
    st.write("Drag and drop **all 3 Tradovate CSV files** at once (`orders-all`, `account-info`, and `notifications-log`). The app will automatically identify and reconcile them.")

    uploaded_files = st.file_uploader("Upload all Tradovate CSV files for today", type=['csv'], accept_multiple_files=True)

    if uploaded_files:
        files_dict = {}
        for f in uploaded_files:
            fname = f.name.lower()
            
            if f.size == 0:
                st.warning(f"Skipping empty file: `{f.name}`")
                continue
                
            try:
                df = pd.read_csv(f)
                if df.empty:
                    continue
                    
                if 'orders-all' in fname or 'order' in fname:
                    files_dict['orders'] = df
                elif 'account-info' in fname or 'account' in fname:
                    files_dict['account'] = df
                elif 'notifications-log' in fname or 'notification' in fname:
                    files_dict['notifications'] = df
            except pd.errors.EmptyDataError:
                st.warning(f"Skipping empty CSV file: `{f.name}`")
                continue

        st.info(f"Loaded {len(files_dict)} file type(s): " + ", ".join(files_dict.keys()))

        if 'orders' in files_dict:
            parsed_trades, acc_metrics = parse_tradovate_multi_files(files_dict)

            if acc_metrics:
                st.success(f"**Account Balance Sync**: Net Liq: ${acc_metrics['Net Liq']:,.2f} | Total Session P/L: ${acc_metrics['Total P/L']:,.2f}")

            if parsed_trades:
                parsed_df = pd.DataFrame(parsed_trades)
                st.subheader("Reconciled Trades Preview")
                st.dataframe(parsed_df)

                if st.button("💾 Append & Save Session to Master Database"):
                    existing_ids = set(db['Trade ID']) if not db.empty else set()
                    new_trades = [t for t in parsed_trades if t['Trade ID'] not in existing_ids]

                    if not new_trades:
                        st.info("These trades are already saved in your database.")
                    else:
                        new_df = pd.DataFrame(new_trades)
                        updated_db = pd.concat([db, new_df], ignore_index=True)
                        save_trade_db(updated_db)
                        st.success(f"Successfully added {len(new_trades)} new trade(s) to your journal!")
                        st.balloons()
            else:
                st.warning("No matching filled trades were found in the uploaded orders file.")
        else:
            st.error("Please make sure to include the `tradovate-orders-all-*.csv` file in your selection.")

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

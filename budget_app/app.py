import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. SAFETY FUNCTIONS (The Fix for Crashes) ---
def ensure_df(data, date_cols=None):
    """
    The 'Bouncer': Forces any data (List, Dict, etc.) to be a clean Pandas DataFrame.
    This prevents 'AttributeError' and 'ValueError'.
    """
    try:
        if data is None:
            return pd.DataFrame()
        
        # If it's already a DataFrame, keep it. If not, convert it.
        if isinstance(data, pd.DataFrame):
            df = data
        else:
            # handle raw lists/dicts
            df = pd.DataFrame(data)

        # Fix Date Columns if they exist
        if date_cols and not df.empty:
            for col in date_cols:
                if col in df.columns:
                    # Force conversion to date objects
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
    except Exception as e:
        # If data is totally corrupted, return empty table rather than crashing
        st.error(f"Data Repair Error: {e}")
        return pd.DataFrame()

def convert_df_to_json(df):
    """Safely converts DataFrame to JSON string."""
    df_clean = ensure_df(df)
    df_copy = df_clean.copy()
    if 'Date' in df_copy.columns:
        df_copy['Date'] = df_copy['Date'].astype(str)
    return df_copy.to_json(orient="records", indent=4)

# --- 3. MATH LOGIC ---
def get_dates_monthly(start_date, end_date, day_of_month):
    dates = []
    cursor = pd.to_datetime(start_date)
    try:
        max_days = pd.Period(cursor, freq='M').days_in_month
        safe_day = min(day_of_month, max_days)
        cursor = cursor.replace(day=safe_day)
    except:
        pass
    if cursor < pd.to_datetime(start_date):
        cursor += relativedelta(months=1)
    while cursor <= pd.to_datetime(end_date):
        dates.append(cursor)
        cursor += relativedelta(months=1)
        max_d = pd.Period(cursor, freq='M').days_in_month
        safe_d = min(day_of_month, max_d)
        cursor = cursor.replace(day=safe_d)
    return dates

def get_dates_weekly(start_date, end_date, freq, day_str):
    dates = []
    cursor = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    days_map = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    target_idx = days_map.get(day_str, 0)
    days_ahead = (target_idx - cursor.weekday()) % 7
    cursor += timedelta(days=days_ahead)
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=7 if freq == 'Weekly' else 14)
    return dates

def generate_forecast(seed, start_val, df_monthly, df_weekly, df_onetime):
    start_date = pd.to_datetime(start_val)
    end_date = pd.Timestamp(year=start_date.year, month=12, day=31)
    all_transactions = []

    # 1. Force Clean DataFrames (Prevents math crashes)
    df_monthly = ensure_df(df_monthly)
    df_weekly = ensure_df(df_weekly)
    df_onetime = ensure_df(df_onetime, date_cols=['Date'])

    # Seed
    all_transactions.append({'Date': start_date, 'Description': 'Starting Balance', 'Category': 'Deposit', 'Amount': seed, 'Type': 'Seed'})

    # Monthly
    for _, row in df_monthly.iterrows():
        if row.get('Active', True):
            dates = get_dates_monthly(start_date, end_date, row.get('Day (1-31)', 1))
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': d, 'Description': row.get('Name', ''), 'Category': row.get('Category', ''), 'Amount': amt, 'Type': row['Type']})

    # Weekly
    for _, row in df_weekly.iterrows():
        if row.get('Active', True):
            dates = get_dates_weekly(start_date, end_date, row.get('Freq', 'Weekly'), row.get('Day Name', 'Monday'))
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': d, 'Description': row.get('Name',''), 'Category': row.get('Category',''), 'Amount': amt, 'Type': row['Type']})

    # One-Time
    for _, row in df_onetime.iterrows():
        if row.get('Active', True) and pd.notnull(row.get('Date')):
            item_date = pd.to_datetime(row['Date'])
            if start_date <= item_date <= end_date:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': item_date, 'Description': row.get('Name',''), 'Category': row.get('Category',''), 'Amount': amt, 'Type': row['Type']})

    if not all_transactions: return pd.DataFrame()

    df = pd.DataFrame(all_transactions)
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    return df[['Description', 'Category', 'Amount', 'Checking Balance', 'Date']]

# --- 4. INITIALIZATION ---
# Only set defaults if the key is totally missing.
if 'monthly_data' not in st.session_state:
    st.session_state['monthly_data'] = pd.DataFrame([
        {"Active": True, "Type": "Bill", "Name": "Rent (Drew)", "Category": "Housing", "Amount": 1000.0, "Day (1-31)": 1},
        {"Active": True, "Type": "Bill", "Name": "Rent (Alex)", "Category": "Housing", "Amount": 800.0, "Day (1-31)": 1},
    ])
if 'weekly_data' not in st.session_state:
    st.session_state['weekly_data'] = pd.DataFrame([
        {"Active": True, "Type": "Income", "Name": "Drew Paycheck", "Category": "Salary", "Amount": 1600.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
        {"Active": True, "Type": "Income", "Name": "Alex Paycheck", "Category": "Salary", "Amount": 1200.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
    ])
if 'onetime_data' not in st.session_state:
    st.session_state['onetime_data'] = pd.DataFrame([
        {"Active": True, "Type": "Bill", "Name": "Car Registration", "Category": "Auto", "Amount": 85.0, "Date": date(2026, 4, 15)},
    ])
if 'seed' not in st.session_state: st.session_state['seed'] = 3500.0
if 'start_date' not in st.session_state: st.session_state['start_date'] = date(2026, 3, 1)

# --- 5. SIDEBAR: MASTER CONTROLS ---
st.sidebar.header("⚙️ Master Controls")

# Master Load
master_uploaded = st.sidebar.file_uploader("📂 Load Full Budget", type=["json"], key="master_load")
if master_uploaded is not None:
    try:
        data = json.load(master_uploaded)
        st.session_state['seed'] = data['seed']
        st.session_state['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        
        # Load directly to state
        st.session_state['monthly_data'] = ensure_df(data['monthly'])
        st.session_state['weekly_data'] = ensure_df(data['weekly'])
        st.session_state['onetime_data'] = ensure_df(data.get('onetime', []), date_cols=['Date'])
        
        st.sidebar.success("Loaded!")
        # Rerun to refresh editors immediately
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Master Save
seed = st.sidebar.number_input("Starting Balance ($)", value=st.session_state['seed'], step=100.0)
start_date = st.sidebar.date_input("Start Date", value=st.session_state['start_date'])

# Safe Export (Uses ensure_df to prevent crashes)
export_ot = ensure_df(st.session_state['onetime_data'], date_cols=['Date']).copy()
if not export_ot.empty and 'Date' in export_ot.columns: 
    export_ot['Date'] = export_ot['Date'].astype(str)

master_export = {
    "seed": seed, 
    "start_date": str(start_date),
    "monthly": ensure_df(st.session_state['monthly_data']).to_dict(orient="records"),
    "weekly": ensure_df(st.session_state['weekly_data']).to_dict(orient="records"),
    "onetime": export_ot.to_dict(orient="records")
}
st.sidebar.download_button("💾 Save Full Budget", file_name="full_budget.json", data=json.dumps(master_export, indent=4), mime="application/json")

# --- 6. MAIN INTERFACE ---
st.title("💰 Family Cash Flow")

# --- MONTHLY ---
st.subheader("1. Monthly Items")
# Capture the output of the editor
edited_monthly = st.data_editor(
    st.session_state['monthly_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True), "Day (1-31)": st.column_config.NumberColumn(min_value=1, max_value=31), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="monthly_editor_view" 
)
# Update State IMMEDIATELY (Fixes Reset Issue)
st.session_state['monthly_data'] = edited_monthly

with st.expander("📂 Import / Export Monthly"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export Monthly", data=convert_df_to_json(st.session_state['monthly_data']), file_name="monthly.json", mime="application/json")
    up_m = c2.file_uploader("Import Monthly", type=["json"], key="up_m")
    if up_m:
        st.session_state['monthly_data'] = ensure_df(json.load(up_m))
        st.rerun()

# --- WEEKLY ---
st.subheader("2. Weekly Items")
edited_weekly = st.data_editor(
    st.session_state['weekly_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"]), "Freq": st.column_config.SelectboxColumn(options=["Weekly", "Bi-Weekly"]), "Day Name": st.column_config.SelectboxColumn(options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="weekly_editor_view"
)
st.session_state['weekly_data'] = edited_weekly # Sync

with st.expander("📂 Import / Export Weekly"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export Weekly", data=convert_df_to_json(st.session_state['weekly_data']), file_name="weekly.json", mime="application/json")
    up_w = c2.file_uploader("Import Weekly", type=["json"], key="up_w")
    if up_w:
        st.session_state['weekly_data'] = ensure_df(json.load(up_w))
        st.rerun()

# --- ONE-TIME ---
st.subheader("3. One-Time Items")
edited_onetime = st.data_editor(
    st.session_state['onetime_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"]), "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="onetime_editor_view"
)
st.session_state['onetime_data'] = edited_onetime # Sync

with st.expander("📂 Import / Export One-Time"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export One-Time", data=convert_df_to_json(st.session_state['onetime_data']), file_name="onetime.json", mime="application/json")
    up_o = c2.file_uploader("Import One-Time", type=["json"], key="up_o")
    if up_o:
        st.session_state['onetime_data'] = ensure_df(json.load(up_o), date_cols=['Date'])
        st.rerun()

# --- 7. RESULTS ---
st.divider()
if st.button("Generate Forecast", type="primary", use_container_width=True):
    # Pass current State to generator
    res = generate_forecast(seed, start_date, st.session_state['monthly_data'], st.session_state['weekly_data'], st.session_state['onetime_data'])
    
    if not res.empty:
        end_bal = res.iloc[-1]['Checking Balance']
        min_bal = res['Checking Balance'].min()
        surplus = (end_bal - seed) / max(1, 12 - start_date.month + 1)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("End Balance", f"${end_bal:,.2f}")
        c2.metric("Lowest Point", f"${min_bal:,.2f}", delta_color="inverse")
        c3.metric("Avg Surplus/Mo", f"${surplus:,.2f}", delta="Positive" if surplus > 0 else "Negative")
        
        st.dataframe(res.style.map(lambda v: f'color: {"green" if v>=0 else "red"}; font-weight: bold', subset=['Amount']).format({"Amount": lambda x: f"{'+' if x>=0 else '-'}${abs(x):,.2f}", "Checking Balance": "${:,.2f}"}), use_container_width=True, height=600)
    else:
        st.warning("Add items to see forecast.")

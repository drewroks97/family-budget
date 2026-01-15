import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. CALLBACKS (The Fix for the "Reset" Loop) ---
def sync_monthly():
    # Helper to save widget state back to permanent storage immediately
    st.session_state['monthly_data'] = st.session_state['monthly_editor']

def sync_weekly():
    st.session_state['weekly_data'] = st.session_state['weekly_editor']

def sync_onetime():
    st.session_state['onetime_data'] = st.session_state['onetime_editor']

# --- 3. HELPER FUNCTIONS ---
def convert_df_to_json(df):
    df_copy = df.copy()
    if 'Date' in df_copy.columns:
        df_copy['Date'] = df_copy['Date'].astype(str)
    return df_copy.to_json(orient="records", indent=4)

def load_json_to_df(uploaded_file, date_columns=None):
    try:
        data = json.load(uploaded_file)
        df = pd.DataFrame(data)
        if date_columns:
            for col in date_columns:
                if col in df.columns:
                    # Force conversion to date objects to prevent editor crashes
                    df[col] = pd.to_datetime(df[col]).dt.date
        return df
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return pd.DataFrame()

# --- 4. MATH LOGIC ---
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

    # Seed
    all_transactions.append({'Date': start_date, 'Description': 'Starting Balance', 'Category': 'Deposit', 'Amount': seed, 'Type': 'Seed'})

    # Monthly
    for _, row in df_monthly.iterrows():
        if row.get('Active', True):
            dates = get_dates_monthly(start_date, end_date, row['Day (1-31)'])
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': d, 'Description': row['Name'], 'Category': row['Category'], 'Amount': amt, 'Type': row['Type']})

    # Weekly
    for _, row in df_weekly.iterrows():
        if row.get('Active', True):
            dates = get_dates_weekly(start_date, end_date, row['Freq'], row['Day Name'])
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': d, 'Description': row['Name'], 'Category': row['Category'], 'Amount': amt, 'Type': row['Type']})

    # One-Time
    for _, row in df_onetime.iterrows():
        if row.get('Active', True) and pd.notnull(row['Date']):
            item_date = pd.to_datetime(row['Date'])
            if start_date <= item_date <= end_date:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                all_transactions.append({'Date': item_date, 'Description': row['Name'], 'Category': row['Category'], 'Amount': amt, 'Type': row['Type']})

    if not all_transactions: return pd.DataFrame()

    df = pd.DataFrame(all_transactions)
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    return df[['Description', 'Category', 'Amount', 'Checking Balance', 'Date']]

# --- 5. INITIALIZATION ---
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

# --- 6. SIDEBAR: MASTER CONTROLS ---
st.sidebar.header("⚙️ Master Controls")

# Master Load
master_uploaded = st.sidebar.file_uploader("📂 Load Full Budget", type=["json"], key="master_load")
if master_uploaded is not None:
    try:
        data = json.load(master_uploaded)
        st.session_state['seed'] = data['seed']
        st.session_state['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        st.session_state['monthly_data'] = pd.DataFrame(data['monthly'])
        st.session_state['weekly_data'] = pd.DataFrame(data['weekly'])
        
        df_ot = pd.DataFrame(data.get('onetime', []))
        if not df_ot.empty and 'Date' in df_ot.columns:
            df_ot['Date'] = pd.to_datetime(df_ot['Date']).dt.date
        st.session_state['onetime_data'] = df_ot
        
        # Clear editor caches to force refresh
        for key in ['monthly_editor', 'weekly_editor', 'onetime_editor']:
            if key in st.session_state: del st.session_state[key]
            
        st.sidebar.success("Loaded! (Click 'Rerun' if data doesn't appear immediately)")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Master Save
seed = st.sidebar.number_input("Starting Balance ($)", value=st.session_state['seed'], step=100.0)
start_date = st.sidebar.date_input("Start Date", value=st.session_state['start_date'])

export_ot = st.session_state['onetime_data'].copy()
if not export_ot.empty and 'Date' in export_ot.columns: export_ot['Date'] = export_ot['Date'].astype(str)

master_export = {
    "seed": seed, 
    "start_date": str(start_date),
    "monthly": st.session_state['monthly_data'].to_dict(orient="records"),
    "weekly": st.session_state['weekly_data'].to_dict(orient="records"),
    "onetime": export_ot.to_dict(orient="records")
}
st.sidebar.download_button("💾 Save Full Budget", file_name="full_budget.json", data=json.dumps(master_export, indent=4), mime="application/json")

# --- 7. MAIN INTERFACE ---
st.title("💰 Family Cash Flow")

# Monthly
st.subheader("1. Monthly Items")
st.data_editor(
    st.session_state['monthly_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True), "Day (1-31)": st.column_config.NumberColumn(min_value=1, max_value=31), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="monthly_editor",
    on_change=sync_monthly # <--- This callback fixes the reset loop
)

with st.expander("📂 Import / Export Monthly"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export Monthly", data=convert_df_to_json(st.session_state['monthly_data']), file_name="monthly.json", mime="application/json")
    up_m = c2.file_uploader("Import Monthly", type=["json"], key="up_m")
    if up_m:
        st.session_state['monthly_data'] = load_json_to_df(up_m)
        if 'monthly_editor' in st.session_state: del st.session_state['monthly_editor']
        st.rerun()

# Weekly
st.subheader("2. Weekly Items")
st.data_editor(
    st.session_state['weekly_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"]), "Freq": st.column_config.SelectboxColumn(options=["Weekly", "Bi-Weekly"]), "Day Name": st.column_config.SelectboxColumn(options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="weekly_editor",
    on_change=sync_weekly # <--- Callback
)

with st.expander("📂 Import / Export Weekly"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export Weekly", data=convert_df_to_json(st.session_state['weekly_data']), file_name="weekly.json", mime="application/json")
    up_w = c2.file_uploader("Import Weekly", type=["json"], key="up_w")
    if up_w:
        st.session_state['weekly_data'] = load_json_to_df(up_w)
        if 'weekly_editor' in st.session_state: del st.session_state['weekly_editor']
        st.rerun()

# One-Time
st.subheader("3. One-Time Items")
st.data_editor(
    st.session_state['onetime_data'],
    num_rows="dynamic",
    column_config={"Type": st.column_config.SelectboxColumn(options=["Bill", "Income"]), "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"), "Amount": st.column_config.NumberColumn(format="$%.2f")},
    use_container_width=True,
    key="onetime_editor",
    on_change=sync_onetime # <--- Callback
)

with st.expander("📂 Import / Export One-Time"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export One-Time", data=convert_df_to_json(st.session_state['onetime_data']), file_name="onetime.json", mime="application/json")
    up_o = c2.file_uploader("Import One-Time", type=["json"], key="up_o")
    if up_o:
        st.session_state['onetime_data'] = load_json_to_df(up_o, date_columns=['Date'])
        if 'onetime_editor' in st.session_state: del st.session_state['onetime_editor']
        st.rerun()

# --- 8. RESULTS ---
st.divider()
if st.button("Generate Forecast", type="primary", use_container_width=True):
    # Use the session_state directly to ensure we get the latest edits
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

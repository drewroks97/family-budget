import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import io

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. HELPER FUNCTIONS ---
def convert_df_to_json(df):
    """Converts a DataFrame to a JSON string, handling Date objects."""
    df_copy = df.copy()
    # If there is a 'Date' column, ensure it's string format for JSON
    if 'Date' in df_copy.columns:
        df_copy['Date'] = df_copy['Date'].astype(str)
    return df_copy.to_json(orient="records", indent=4)

def load_json_to_df(uploaded_file, date_columns=None):
    """Loads a JSON file into a DataFrame and fixes Date columns."""
    try:
        data = json.load(uploaded_file)
        df = pd.DataFrame(data)
        if date_columns:
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col]).dt.date
        return df
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return pd.DataFrame()

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
        if freq == 'Weekly':
            cursor += timedelta(days=7)
        else: 
            cursor += timedelta(days=14)
    return dates

def generate_forecast(seed, start_val, df_monthly, df_weekly, df_onetime):
    start_date = pd.to_datetime(start_val)
    end_date = pd.Timestamp(year=start_date.year, month=12, day=31)
    
    all_transactions = []

    # Seed
    all_transactions.append({
        'Date': start_date, 'Description': 'Starting Balance', 'Category': 'Deposit', 'Amount': seed, 'Type': 'Seed'
    })

    # Monthly
    for index, row in df_monthly.iterrows():
        if row['Active']:
            dates = get_dates_monthly(start_date, end_date, row['Day (1-31)'])
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row['Type'] == 'Income' else row['Category']
                all_transactions.append({'Date': d, 'Description': row['Name'], 'Category': cat, 'Amount': amt, 'Type': row['Type']})

    # Weekly
    for index, row in df_weekly.iterrows():
        if row['Active']:
            dates = get_dates_weekly(start_date, end_date, row['Freq'], row['Day Name'])
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row['Type'] == 'Income' else row['Category']
                all_transactions.append({'Date': d, 'Description': row['Name'], 'Category': cat, 'Amount': amt, 'Type': row['Type']})

    # One-Time Items
    for index, row in df_onetime.iterrows():
        if row['Active'] and row['Date'] is not None:
            item_date = pd.to_datetime(row['Date'])
            if start_date <= item_date <= end_date:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row['Type'] == 'Income' else row['Category']
                all_transactions.append({'Date': item_date, 'Description': row['Name'], 'Category': cat, 'Amount': amt, 'Type': row['Type']})

    if not all_transactions:
        return pd.DataFrame()

    df = pd.DataFrame(all_transactions)
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    
    return df[['Description', 'Category', 'Amount', 'Checking Balance', 'Date']]

# --- 4. SESSION STATE INIT ---
if 'monthly_data' not in st.session_state:
    st.session_state['monthly_data'] = pd.DataFrame([
        {"Active": True, "Type": "Bill", "Name": "Rent (Drew)", "Category": "Housing", "Amount": 1000.0, "Day (1-31)": 1},
        {"Active": True, "Type": "Bill", "Name": "Rent (Alex)", "Category": "Housing", "Amount": 800.0, "Day (1-31)": 1},
    ])

if 'weekly_data' not in st.session_state:
    st.session_state['weekly_data'] = pd.DataFrame([
        {"Active": True, "Type": "Income", "Name": "Drew Paycheck", "Category": "Salary", "Amount": 1600.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
        {"Active": True, "Type": "Income", "Name": "Alex Paycheck", "Category": "Salary", "Amount": 1200.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
        {"Active": True, "Type": "Bill", "Name": "Gas", "Category": "Auto", "Amount": 40.0, "Freq": "Weekly", "Day Name": "Monday"},
    ])

if 'onetime_data' not in st.session_state:
    st.session_state['onetime_data'] = pd.DataFrame([
        {"Active": True, "Type": "Bill", "Name": "Car Registration", "Category": "Auto", "Amount": 85.0, "Date": date(2026, 4, 15)},
        {"Active": True, "Type": "Income", "Name": "Tax Refund", "Category": "Gov", "Amount": 500.0, "Date": date(2026, 3, 20)},
    ])

if 'seed' not in st.session_state: st.session_state['seed'] = 3500.0
if 'start_date' not in st.session_state: st.session_state['start_date'] = date(2026, 3, 1)

# --- 5. SIDEBAR: MASTER SAVE/LOAD ---
st.sidebar.header("⚙️ Master Controls")
st.sidebar.markdown("**Global Save/Load** (All Data + Settings)")

# Master Load
master_uploaded = st.sidebar.file_uploader("📂 Load Full Budget", type=["json"], key="master_load")
if master_uploaded is not None:
    try:
        data = json.load(master_uploaded)
        st.session_state['seed'] = data['seed']
        st.session_state['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        st.session_state['monthly_data'] = pd.DataFrame(data['monthly'])
        st.session_state['weekly_data'] = pd.DataFrame(data['weekly'])
        
        # Load One-Time and fix dates
        df_ot = pd.DataFrame(data.get('onetime', []))
        if not df_ot.empty and 'Date' in df_ot.columns:
            df_ot['Date'] = pd.to_datetime(df_ot['Date']).dt.date
        st.session_state['onetime_data'] = df_ot
        st.sidebar.success("Full Budget Loaded!")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Master Inputs
seed = st.sidebar.number_input("Starting Balance ($)", value=st.session_state['seed'], step=100.0)
start_date = st.sidebar.date_input("Start Date", value=st.session_state['start_date'])

# Master Save Logic
export_onetime_clean = st.session_state['onetime_data'].copy()
if not export_onetime_clean.empty and 'Date' in export_onetime_clean.columns:
    export_onetime_clean['Date'] = export_onetime_clean['Date'].astype(str)

master_export_data = {
    "seed": seed,
    "start_date": str(start_date),
    "monthly": st.session_state['monthly_data'].to_dict(orient="records"),
    "weekly": st.session_state['weekly_data'].to_dict(orient="records"),
    "onetime": export_onetime_clean.to_dict(orient="records")
}
st.sidebar.download_button(
    label="💾 Save Full Budget",
    file_name="full_budget.json",
    mime="application/json",
    data=json.dumps(master_export_data, indent=4)
)

# --- 6. MAIN INTERFACE ---
st.title("💰 Family Cash Flow")

# --- SECTION 1: MONTHLY ---
st.subheader("1. Monthly Items (Recurring by Date)")
edited_monthly = st.data_editor(
    st.session_state['monthly_data'],
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Day (1-31)": st.column_config.NumberColumn(min_value=1, max_value=31, step=1, required=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="monthly_editor" 
)
st.session_state['monthly_data'] = edited_monthly # Sync back to state

with st.expander("📂 Import / Export Monthly Data"):
    c1, c2 = st.columns([1, 2])
    # Export
    c1.download_button("Export Monthly JSON", data=convert_df_to_json(edited_monthly), file_name="monthly_items.json", mime="application/json")
    # Import
    uploaded_monthly = c2.file_uploader("Import Monthly JSON", type=["json"], key="up_monthly")
    if uploaded_monthly:
        st.session_state['monthly_data'] = load_json_to_df(uploaded_monthly)
        st.rerun()

# --- SECTION 2: WEEKLY ---
st.subheader("2. Weekly Items (Recurring by Day of Week)")
edited_weekly = st.data_editor(
    st.session_state['weekly_data'],
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Freq": st.column_config.SelectboxColumn(options=["Weekly", "Bi-Weekly"], required=True),
        "Day Name": st.column_config.SelectboxColumn(options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], required=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="weekly_editor"
)
st.session_state['weekly_data'] = edited_weekly # Sync

with st.expander("📂 Import / Export Weekly Data"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export Weekly JSON", data=convert_df_to_json(edited_weekly), file_name="weekly_items.json", mime="application/json")
    uploaded_weekly = c2.file_uploader("Import Weekly JSON", type=["json"], key="up_weekly")
    if uploaded_weekly:
        st.session_state['weekly_data'] = load_json_to_df(uploaded_weekly)
        st.rerun()

# --- SECTION 3: ONE-TIME ---
st.subheader("3. One-Time Items (Specific Dates)")
edited_onetime = st.data_editor(
    st.session_state['onetime_data'],
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY", required=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="onetime_editor"
)
st.session_state['onetime_data'] = edited_onetime # Sync

with st.expander("📂 Import / Export One-Time Data"):
    c1, c2 = st.columns([1, 2])
    c1.download_button("Export One-Time JSON", data=convert_df_to_json(edited_onetime), file_name="onetime_items.json", mime="application/json")
    uploaded_onetime = c2.file_uploader("Import One-Time JSON", type=["json"], key="up_onetime")
    if uploaded_onetime:
        # Special loader to fix date column
        st.session_state['onetime_data'] = load_json_to_df(uploaded_onetime, date_columns=['Date'])
        st.rerun()

# --- 7. CALCULATION & STYLING ---
st.divider()

if st.button("Generate Forecast", type="primary", use_container_width=True):
    result_df = generate_forecast(seed, start_date, edited_monthly, edited_weekly, edited_onetime)
    
    if not result_df.empty:
        end_bal = result_df.iloc[-1]['Checking Balance']
        min_bal = result_df['Checking Balance'].min()
        
        total_growth = end_bal - seed
        months_remaining = max(1, 12 - start_date.month + 1)
        avg_monthly_surplus = total_growth / months_remaining
        
        c1, c2, c3 = st.columns(3)
        c1.metric("End of Year Balance", f"${end_bal:,.2f}")
        c2.metric("Lowest Point", f"${min_bal:,.2f}", delta_color="inverse")
        c3.metric("Avg. Monthly Surplus", f"${avg_monthly_surplus:,.2f}", 
                  delta="Positive" if avg_monthly_surplus > 0 else "Negative")
        
        def style_negative_red_positive_green(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}; font-weight: bold'

        def format_with_plus(val):
            return f"+${val:,.2f}" if val >= 0 else f"-${abs(val):,.2f}"

        styled_df = result_df.style\
            .map(style_negative_red_positive_green, subset=['Amount'])\
            .format({"Amount": format_with_plus, "Checking Balance": "${:,.2f}"})

        st.dataframe(styled_df, use_container_width=True, height=600)
    else:
        st.warning("Add some items to generate a forecast.")

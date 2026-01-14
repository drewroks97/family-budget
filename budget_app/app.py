import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. LOGIC (Math) ---
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

def generate_forecast(seed, start_val, df_monthly, df_weekly):
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

    if not all_transactions:
        return pd.DataFrame()

    df = pd.DataFrame(all_transactions)
    # Sort by real date object first
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    
    # FORMATTING FIX: Convert Date to MM/DD/YYYY string just for display
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    
    return df[['Date', 'Description', 'Category', 'Amount', 'Checking Balance']]

# --- 3. SESSION STATE & DATA LOADING ---

# Initialize default data if fresh load
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

if 'seed' not in st.session_state: st.session_state['seed'] = 3500.0
if 'start_date' not in st.session_state: st.session_state['start_date'] = date(2026, 3, 1)

# --- 4. SIDEBAR (SETTINGS & SAVE/LOAD) ---
st.sidebar.header("⚙️ Setup")
uploaded_file = st.sidebar.file_uploader("📂 Load Saved Budget (JSON)", type=["json"])

if uploaded_file is not None:
    try:
        data = json.load(uploaded_file)
        # Load scalar values
        st.session_state['seed'] = data['seed']
        st.session_state['start_date'] = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        # Load DataFrames
        st.session_state['monthly_data'] = pd.DataFrame(data['monthly'])
        st.session_state['weekly_data'] = pd.DataFrame(data['weekly'])
        st.sidebar.success("Budget Loaded Successfully!")
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

# Inputs linked to Session State
seed = st.sidebar.number_input("Starting Balance ($)", value=st.session_state['seed'], step=100.0, key='seed_input')
start_date = st.sidebar.date_input("Start Date", value=st.session_state['start_date'], key='date_input')

# --- 5. MAIN INTERFACE ---
st.title("💰 Family Cash Flow")

# Monthly Editor
st.subheader("1. Monthly Items (Date Based)")
edited_monthly = st.data_editor(
    st.session_state['monthly_data'],
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Day (1-31)": st.column_config.NumberColumn(min_value=1, max_value=31, step=1, required=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="monthly_editor" # Important for state
)

# Weekly Editor
st.subheader("2. Weekly/Bi-Weekly Items (Day-of-Week Based)")
edited_weekly = st.data_editor(
    st.session_state['weekly_data'],
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Freq": st.column_config.SelectboxColumn(options=["Weekly", "Bi-Weekly"], required=True),
        "Day Name": st.column_config.SelectboxColumn(
            options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], 
            required=True
        ),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="weekly_editor"
)

# --- 6. EXPORT LOGIC ---
# We prepare the JSON string for download
export_data = {
    "seed": seed,
    "start_date": str(start_date),
    "monthly": edited_monthly.to_dict(orient="records"),
    "weekly": edited_weekly.to_dict(orient="records")
}
json_string = json.dumps(export_data, indent=4)

st.sidebar.download_button(
    label="💾 Save Budget to File",
    file_name="family_budget.json",
    mime="application/json",
    data=json_string
)

# --- 7. CALCULATION ---
st.divider()

if st.button("Generate Forecast", type="primary", use_container_width=True):
    result_df = generate_forecast(seed, start_date, edited_monthly, edited_weekly)
    
    if not result_df.empty:
        end_bal = result_df.iloc[-1]['Checking Balance']
        min_bal = result_df['Checking Balance'].min()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("End of Year Balance", f"${end_bal:,.2f}")
        c2.metric("Lowest Point", f"${min_bal:,.2f}", delta_color="inverse")
        
        st.dataframe(
            result_df.style.format({"Amount": "${:,.2f}", "Checking Balance": "${:,.2f}"}),
            use_container_width=True,
            height=600
        )
    else:
        st.warning("Add some items to generate a forecast.")

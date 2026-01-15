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

    # One-Time Items (NEW LOGIC)
    for index, row in df_onetime.iterrows():
        if row['Active'] and row['Date'] is not None:
            # Ensure the date from the editor is converted to a Timestamp for comparison
            item_date = pd.to_datetime(row['Date'])
            
            # Check if date falls within the view range (Start Date -> End of Year)
            if start_date <= item_date <= end_date:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row['Type'] == 'Income' else row['Category']
                all_transactions.append({'Date': item_date, 'Description': row['Name'], 'Category': cat, 'Amount': amt, 'Type': row['Type']})

    if not all_transactions:
        return pd.DataFrame()

    df = pd.DataFrame(all_transactions)
    # Sort by real date object first
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    
    # Format Date
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    
    return df[['Description', 'Category', 'Amount', 'Checking Balance', 'Date']]

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

# NEW: One-Time Data State
if 'onetime_data' not in st.session_state:
    st.session_state['onetime_data'] = pd.DataFrame([
        {"Active": True, "Type": "Bill", "Name": "Car Registration", "Category": "Auto", "Amount": 85.0, "Date": date(2026, 4, 15)},
        {"Active": True, "Type": "Income", "Name": "Tax Refund", "Category": "Gov", "Amount": 500.0, "Date": date(2026, 3, 20)},
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
        
        # NEW: Load One-Time Data and convert string dates back to Objects
        df_ot = pd.DataFrame(data.get('onetime', []))
        if not df_ot.empty and 'Date' in df_ot.columns:
            df_ot['Date'] = pd.to_datetime(df_ot['Date']).dt.date
        st.session_state['onetime_data'] = df_ot
        
        st.sidebar.success("Budget Loaded Successfully!")
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

# Inputs linked to Session State
seed = st.sidebar.number_input("Starting Balance ($)", value=st.session_state['seed'], step=100.0, key='seed_input')
start_date = st.sidebar.date_input("Start Date", value=st.session_state['start_date'], key='date_input')

# --- 5. MAIN INTERFACE ---
st.title("💰 Family Cash Flow")

# Monthly Editor
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

# Weekly Editor
st.subheader("2. Weekly Items (Recurring by Day of Week)")
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

# NEW: One-Time Editor
st.subheader("3. One-Time Items (Specific Dates)")
st.caption("Add single expenses (Car repair, Gifts) or Income (Bonus, Tax Refund).")
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

# --- 6. EXPORT LOGIC ---

# Prepare onetime data for JSON (Convert Date objects to strings)
export_onetime = edited_onetime.copy()
if not export_onetime.empty:
    export_onetime['Date'] = export_onetime['Date'].astype(str)

export_data = {
    "seed": seed,
    "start_date": str(start_date),
    "monthly": edited_monthly.to_dict(orient="records"),
    "weekly": edited_weekly.to_dict(orient="records"),
    "onetime": export_onetime.to_dict(orient="records") # New field
}
json_string = json.dumps(export_data, indent=4)

st.sidebar.download_button(
    label="💾 Save Budget to File",
    file_name="family_budget.json",
    mime="application/json",
    data=json_string
)

# --- 7. CALCULATION & STYLING ---
st.divider()

if st.button("Generate Forecast", type="primary", use_container_width=True):
    # Pass all three dataframes to the calculator
    result_df = generate_forecast(seed, start_date, edited_monthly, edited_weekly, edited_onetime)
    
    if not result_df.empty:
        end_bal = result_df.iloc[-1]['Checking Balance']
        min_bal = result_df['Checking Balance'].min()
        
        # --- METRIC CALCULATION ---
        total_growth = end_bal - seed
        
        months_remaining = 12 - start_date.month + 1
        if months_remaining < 1: months_remaining = 1 
        
        avg_monthly_surplus = total_growth / months_remaining
        
        # --- DISPLAY METRICS ---
        c1, c2, c3 = st.columns(3)
        c1.metric("End of Year Balance", f"${end_bal:,.2f}")
        c2.metric("Lowest Point", f"${min_bal:,.2f}", delta_color="inverse")
        c3.metric("Avg. Monthly Surplus", f"${avg_monthly_surplus:,.2f}", 
                  delta="Positive" if avg_monthly_surplus > 0 else "Negative")
        
        # --- STYLE DEFINITIONS ---
        def style_negative_red_positive_green(val):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}; font-weight: bold'

        def format_with_plus(val):
            if val >= 0:
                return f"+${val:,.2f}"
            return f"-${abs(val):,.2f}"

        # --- APPLY STYLES ---
        styled_df = result_df.style\
            .map(style_negative_red_positive_green, subset=['Amount'])\
            .format({"Amount": format_with_plus, "Checking Balance": "${:,.2f}"})

        st.dataframe(
            styled_df,
            use_container_width=True,
            height=600
        )
    else:
        st.warning("Add some items to generate a forecast.")

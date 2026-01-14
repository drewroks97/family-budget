import streamlit as st
import pandas as pd
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. LOGIC (Exact same math as your script) ---
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
        else: # Bi-Weekly
            cursor += timedelta(days=14)
    return dates

def generate_forecast(seed, start_val, df_monthly, df_weekly):
    start_date = pd.to_datetime(start_val)
    end_date = pd.Timestamp(year=start_date.year, month=12, day=31)
    
    all_transactions = []

    # Add Seed
    all_transactions.append({
        'Date': start_date, 'Description': 'Starting Balance', 'Category': 'Deposit', 'Amount': seed, 'Type': 'Seed'
    })

    # Process Monthly (Date Based)
    for index, row in df_monthly.iterrows():
        if row['Active']:
            dates = get_dates_monthly(start_date, end_date, row['Day (1-31)'])
            for d in dates:
                amt = row['Amount'] if row['Type'] == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row['Type'] == 'Income' else row['Category']
                all_transactions.append({'Date': d, 'Description': row['Name'], 'Category': cat, 'Amount': amt, 'Type': row['Type']})

    # Process Weekly (Day Name Based)
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
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    df['Checking Balance'] = df['Amount'].cumsum()
    return df[['Date', 'Description', 'Category', 'Amount', 'Checking Balance']]

# --- 3. THE WEB APP INTERFACE ---

st.sidebar.header("⚙️ Setup")
seed = st.sidebar.number_input("Starting Balance ($)", value=3500.0, step=100.0)
start_date = st.sidebar.date_input("Start Date", value=date(2026, 3, 1))

st.title("💰 Family Cash Flow")
st.markdown("Use this to project our balance through the end of the year.")

# --- SECTION 1: MONTHLY ITEMS ---
st.subheader("1. Monthly Items (Date Based)")
st.caption("Items that happen on a specific date (e.g., Rent on the 1st, Netflix on the 15th).")

default_monthly = pd.DataFrame([
    {"Active": True, "Type": "Bill", "Name": "Rent (Drew)", "Category": "Housing", "Amount": 1000.0, "Day (1-31)": 1},
    {"Active": True, "Type": "Bill", "Name": "Rent (Alex)", "Category": "Housing", "Amount": 800.0, "Day (1-31)": 1},
])

# Interactive Data Editor for Monthly
edited_monthly = st.data_editor(
    default_monthly,
    num_rows="dynamic",
    column_config={
        "Type": st.column_config.SelectboxColumn(options=["Bill", "Income"], required=True),
        "Day (1-31)": st.column_config.NumberColumn(min_value=1, max_value=31, step=1, required=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f")
    },
    use_container_width=True,
    key="monthly_editor"
)

# --- SECTION 2: WEEKLY ITEMS ---
st.subheader("2. Weekly/Bi-Weekly Items (Day-of-Week Based)")
st.caption("Items that happen on a specific day of the week (e.g., Paychecks on Fridays, Groceries on Mondays).")

default_weekly = pd.DataFrame([
    {"Active": True, "Type": "Income", "Name": "Drew Paycheck", "Category": "Salary", "Amount": 1600.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
    {"Active": True, "Type": "Income", "Name": "Alex Paycheck", "Category": "Salary", "Amount": 1200.0, "Freq": "Bi-Weekly", "Day Name": "Friday"},
    {"Active": True, "Type": "Bill", "Name": "Gas", "Category": "Auto", "Amount": 40.0, "Freq": "Weekly", "Day Name": "Monday"},
])

# Interactive Data Editor for Weekly
edited_weekly = st.data_editor(
    default_weekly,
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

# --- 4. EXECUTION ---
st.divider()

if st.button("Generate Forecast", type="primary", use_container_width=True):
    # Run Calculation
    result_df = generate_forecast(seed, start_date, edited_monthly, edited_weekly)
    
    if not result_df.empty:
        # Metrics
        end_bal = result_df.iloc[-1]['Checking Balance']
        min_bal = result_df['Checking Balance'].min()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("End of Year Balance", f"${end_bal:,.2f}")
        c2.metric("Lowest Point", f"${min_bal:,.2f}", delta_color="inverse")
        
        # Chart
        st.area_chart(result_df, x="Date", y="Checking Balance", color="#85bb65")
        
        # Table
        st.dataframe(
            result_df.style.format({"Amount": "${:,.2f}", "Checking Balance": "${:,.2f}"}),
            use_container_width=True,
            height=600
        )
    else:
        st.warning("Add some items to generate a forecast.")
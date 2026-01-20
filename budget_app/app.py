import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from io import StringIO
import numpy as np

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Family Cash Flow", layout="wide", page_icon="💰")

# --- 2. VALIDATION FUNCTIONS ---
def validate_data(df_monthly, df_weekly, df_onetime):
    """Validate input data before processing"""
    warnings = []
    
    # Check for negative amounts in bills
    for name, df in [("Monthly", df_monthly), ("Weekly", df_weekly), ("One-time", df_onetime)]:
        if not df.empty and 'Type' in df.columns and 'Amount' in df.columns:
            negative_bills = df[(df['Type'] == 'Bill') & (df['Amount'] < 0)]
            if not negative_bills.empty:
                warnings.append(f"⚠️ {name}: Bill amounts should be positive values")
            
            # Check for missing required fields
            for col in ['Active', 'Type', 'Name', 'Amount']:
                if col in df.columns:
                    missing = df[df[col].isna()]
                    if not missing.empty:
                        warnings.append(f"⚠️ {name}: Some rows missing '{col}' values")
    
    # Check date ranges for one-time items
    if not df_onetime.empty and 'Date' in df_onetime.columns:
        try:
            dates = pd.to_datetime(df_onetime['Date'], errors='coerce')
            invalid_dates = df_onetime[dates.isna()]
            if not invalid_dates.empty:
                warnings.append("⚠️ One-time items have invalid dates")
        except:
            pass
    
    return warnings

# --- 3. MATH LOGIC (CACHED) ---
@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=True)
def get_all_transactions(seed, start_val, monthly_json, weekly_json, onetime_json):
    """Generates the raw list of all transactions (cached)."""
    df_monthly = pd.DataFrame(monthly_json)
    df_weekly = pd.DataFrame(weekly_json)
    df_onetime = pd.DataFrame(onetime_json)
    
    start_date = pd.to_datetime(start_val)
    end_date = pd.Timestamp(year=start_date.year, month=12, day=31)
    all_transactions = []
    
    # 1. Seed
    all_transactions.append({
        'Date': start_date, 
        'Description': 'Starting Balance', 
        'Category': 'Deposit', 
        'Amount': seed, 
        'Type': 'Seed'
    })

    # 2. Monthly
    for _, row in df_monthly.iterrows():
        if row.get('Active', False):
            day_of_month = int(row.get('Day (1-31)', 1))
            dates = get_dates_monthly(start_date, end_date, day_of_month)
            for d in dates:
                amt = row['Amount'] if row.get('Type') == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row.get('Type') == 'Income' else row.get('Category', 'Uncategorized')
                all_transactions.append({
                    'Date': d, 
                    'Description': row.get('Name', 'Unnamed'), 
                    'Category': cat, 
                    'Amount': amt, 
                    'Type': row.get('Type', 'Bill')
                })

    # 3. Weekly
    for _, row in df_weekly.iterrows():
        if row.get('Active', False):
            freq = row.get('Freq', 'Weekly')
            day_str = row.get('Day Name', 'Monday')
            dates = get_dates_weekly(start_date, end_date, freq, day_str)
            for d in dates:
                amt = row['Amount'] if row.get('Type') == 'Income' else -abs(row['Amount'])
                cat = 'Income' if row.get('Type') == 'Income' else row.get('Category', 'Uncategorized')
                all_transactions.append({
                    'Date': d, 
                    'Description': row.get('Name', 'Unnamed'), 
                    'Category': cat, 
                    'Amount': amt, 
                    'Type': row.get('Type', 'Bill')
                })

    # 4. One-Time
    for _, row in df_onetime.iterrows():
        if row.get('Active', False) and pd.notna(row.get('Date')):
            try:
                item_date = pd.to_datetime(row['Date'])
                if start_date <= item_date <= end_date:
                    amt = row['Amount'] if row.get('Type') == 'Income' else -abs(row['Amount'])
                    cat = 'Income' if row.get('Type') == 'Income' else row.get('Category', 'Uncategorized')
                    all_transactions.append({
                        'Date': item_date, 
                        'Description': row.get('Name', 'Unnamed'), 
                        'Category': cat, 
                        'Amount': amt, 
                        'Type': row.get('Type', 'Bill')
                    })
            except:
                continue

    if not all_transactions: 
        return pd.DataFrame()
    
    df = pd.DataFrame(all_transactions)
    df.sort_values(by=['Date', 'Amount'], ascending=[True, False], inplace=True)
    return df

@st.cache_data(ttl=300, show_spinner=False)
def generate_forecast(seed, start_val, monthly_json, weekly_json, onetime_json):
    """Uses the transaction list to build the running balance forecast."""
    df = get_all_transactions(seed, start_val, monthly_json, weekly_json, onetime_json)
    if df.empty: 
        return pd.DataFrame()
    
    df['Checking Balance'] = df['Amount'].cumsum()
    df['Date'] = df['Date'].dt.strftime('%m/%d/%Y')
    return df[['Description', 'Category', 'Amount', 'Checking Balance', 'Date']]

# --- 4. SESSION STATE INITIALIZATION ---
def initialize_session_state():
    """Initialize or reset session state with proper structure."""
    if 'monthly_data' not in st.session_state:
        st.session_state.monthly_data = pd.DataFrame({
            "Active": [True, True],
            "Type": ["Bill", "Income"],
            "Name": ["Rent/Mortgage", "Salary"],
            "Category": ["Housing", "Employment"],
            "Amount": [2000.00, 5000.00],
            "Day (1-31)": [1, 15]
        })
    
    if 'weekly_data' not in st.session_state:
        st.session_state.weekly_data = pd.DataFrame({
            "Active": [True, True],
            "Type": ["Bill", "Bill"],
            "Name": ["Groceries", "Allowance"],
            "Category": ["Food", "Personal"],
            "Amount": [200.00, 50.00],
            "Freq": ["Weekly", "Weekly"],
            "Day Name": ["Saturday", "Friday"]
        })
    
    if 'onetime_data' not in st.session_state:
        st.session_state.onetime_data = pd.DataFrame({
            "Active": [True, True],
            "Type": ["Income", "Bill"],
            "Name": ["Tax Refund", "Vacation"],
            "Category": ["Bonus", "Travel"],
            "Amount": [1500.00, 2000.00],
            "Date": [date.today() + timedelta(days=60), date.today() + timedelta(days=90)]
        })
    
    if 'seed' not in st.session_state:
        st.session_state.seed = 10000.00
    
    if 'start_date' not in st.session_state:
        st.session_state.start_date = date.today()
    
    if 'last_saved' not in st.session_state:
        st.session_state.last_saved = None
    
    # Track if data has been edited
    if 'monthly_edited' not in st.session_state:
        st.session_state.monthly_edited = False
    if 'weekly_edited' not in st.session_state:
        st.session_state.weekly_edited = False
    if 'onetime_edited' not in st.session_state:
        st.session_state.onetime_edited = False

# Initialize the app
initialize_session_state()

# --- 5. SYNC SESSION STATE WITH EDITORS ---
def sync_data_editors():
    """Sync data from editors to session state to fix the double-entry issue."""
    # Use the keys from the data editors to get the current state
    if "monthly_editor" in st.session_state:
        # Get the data from the editor's widget state
        monthly_data = st.session_state.monthly_editor.get("edited_rows", {})
        added_rows = st.session_state.monthly_editor.get("added_rows", [])
        deleted_rows = st.session_state.monthly_editor.get("deleted_rows", [])
        
        # Only update if there are changes
        if monthly_data or added_rows or deleted_rows:
            st.session_state.monthly_edited = True
            # For now, we'll rely on the returned dataframe approach below
            # because the widget state is complex to parse
    
    # Same for weekly
    if "weekly_editor" in st.session_state:
        if (st.session_state.weekly_editor.get("edited_rows", {}) or 
            st.session_state.weekly_editor.get("added_rows", []) or 
            st.session_state.weekly_editor.get("deleted_rows", [])):
            st.session_state.weekly_edited = True
    
    # Same for onetime
    if "onetime_editor" in st.session_state:
        if (st.session_state.onetime_editor.get("edited_rows", {}) or 
            st.session_state.onetime_editor.get("added_rows", []) or 
            st.session_state.onetime_editor.get("deleted_rows", [])):
            st.session_state.onetime_edited = True

# --- 6. SIDEBAR (MASTER CONTROLS) ---
st.sidebar.header("⚙️ Master Controls")

# Load example button
if st.sidebar.button("📋 Load Example Data", use_container_width=True, type="secondary"):
    initialize_session_state()
    st.sidebar.success("Example data loaded!")
    st.rerun()

# Reset button
if st.sidebar.button("🔄 Reset All Data", use_container_width=True, type="secondary"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    initialize_session_state()
    st.sidebar.success("All data reset!")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("**Load Budget File**")
uploaded_file = st.sidebar.file_uploader("📂 Load Full Budget", type=["json"], label_visibility="collapsed")

if uploaded_file is not None:
    try:
        data = json.load(uploaded_file)
        st.session_state['seed'] = float(data.get('seed', 0.0))
        
        start_date_str = data.get('start_date', str(date.today()))
        st.session_state['start_date'] = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        
        st.session_state['monthly_data'] = pd.DataFrame(data.get('monthly', []))
        st.session_state['weekly_data'] = pd.DataFrame(data.get('weekly', []))
        
        # Handle one-time dates properly
        df_ot = pd.DataFrame(data.get('onetime', []))
        if not df_ot.empty and 'Date' in df_ot.columns:
            df_ot['Date'] = pd.to_datetime(df_ot['Date']).dt.date
        
        st.session_state['onetime_data'] = df_ot
        st.session_state.last_saved = uploaded_file.name
        st.sidebar.success(f"Loaded: {uploaded_file.name}")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")

st.sidebar.markdown("---")

# Inputs (Syncing UI to State)
current_seed = st.sidebar.number_input(
    "💰 Starting Balance ($)", 
    value=float(st.session_state['seed']), 
    step=100.0, 
    key='seed_input',
    help="Your initial checking account balance"
)

current_start_date = st.sidebar.date_input(
    "📅 Start Date", 
    value=st.session_state['start_date'], 
    key='date_input',
    help="Start date for the cash flow forecast"
)

st.session_state['seed'] = current_seed
st.session_state['start_date'] = current_start_date

# Export button
st.sidebar.markdown("---")
st.sidebar.caption("**Export Budget**")

# Prepare data for export
export_monthly = st.session_state.monthly_data.copy()
export_weekly = st.session_state.weekly_data.copy()
export_onetime = st.session_state.onetime_data.copy()

# Convert dates to strings for JSON export
if not export_onetime.empty and 'Date' in export_onetime.columns:
    export_onetime['Date'] = export_onetime['Date'].astype(str)

full_budget_data = {
    "seed": current_seed,
    "start_date": str(current_start_date),
    "monthly": export_monthly.to_dict(orient="records"),
    "weekly": export_weekly.to_dict(orient="records"),
    "onetime": export_onetime.to_dict(orient="records")
}

# Convert to JSON string
json_str = json.dumps(full_budget_data, indent=4)

# Download button
st.sidebar.download_button(
    label="💾 Save Budget As...",
    data=json_str,
    file_name="family_budget.json",
    mime="application/json",
    use_container_width=True,
    help="Download your budget configuration as a JSON file"
)

# Show last loaded file
if st.session_state.last_saved:
    st.sidebar.caption(f"Last loaded: *{st.session_state.last_saved}*")

# --- 7. MAIN INTERFACE ---
st.title("💰 Family Cash Flow Forecast")
st.caption("Plan your family's cash flow for the rest of the year")

# Help section
with st.expander("❓ How to use this app"):
    st.markdown("""
    ### Quick Start Guide:
    
    1. **Set Starting Point**: Enter your current balance and start date in the sidebar
    2. **Add Transactions**:
       - **Monthly**: Regular bills/income (rent, salary)
       - **Weekly**: Recurring weekly/bi-weekly items (groceries, allowance)
       - **One-time**: Special expenses/income (vacations, bonuses)
    3. **Check MTM Solvency**: See your monthly income vs expenses
    4. **Generate Forecast**: View detailed day-by-day cash flow
    
    ### Tips:
    - Click outside the cell or press Tab to save your entry
    - Use **Active** checkbox to temporarily disable items
    - **Load Example** to see a working setup
    - **Save/Load** your budget using the sidebar controls
    """)

# Call sync function
sync_data_editors()

# Validation warnings
warnings = validate_data(
    st.session_state.monthly_data, 
    st.session_state.weekly_data, 
    st.session_state.onetime_data
)

if warnings:
    with st.container(border=True):
        st.warning("Data Validation Issues:")
        for warning in warnings:
            st.markdown(f"- {warning}")

# --- 8. TRANSACTION EDITORS (FIXED FOR SINGLE ENTRY) ---
# We'll use a different approach: track changes and update session state immediately

tab1, tab2, tab3 = st.tabs(["📅 Monthly Items", "📆 Weekly Items", "🎯 One-time Items"])

with tab1:
    st.caption("Regular monthly bills and income (e.g., rent on the 1st, salary on the 15th)")
    
    # Create editor and get the returned dataframe
    edited_monthly_df = st.data_editor(
        st.session_state.monthly_data,
        num_rows="dynamic",
        column_config={
            "Active": st.column_config.CheckboxColumn(required=True),
            "Type": st.column_config.SelectboxColumn(
                options=["Bill", "Income"], 
                required=True,
                help="Income adds money, Bills subtract money"
            ), 
            "Name": st.column_config.TextColumn(required=True),
            "Category": st.column_config.TextColumn(
                help="Category for grouping (e.g., Housing, Utilities)"
            ),
            "Amount": st.column_config.NumberColumn(
                format="$%.2f",
                required=True,
                min_value=0.0,
                step=1.0
            ), 
            "Day (1-31)": st.column_config.NumberColumn(
                min_value=1, 
                max_value=31,
                required=True,
                help="Day of month (will adjust for shorter months)"
            )
        },
        use_container_width=True,
        key="monthly_editor",
        hide_index=True
    )
    
    # Update session state immediately with the returned dataframe
    # This fixes the double-entry issue
    if not edited_monthly_df.equals(st.session_state.monthly_data):
        st.session_state.monthly_data = edited_monthly_df
        # Force a rerun to show changes immediately
        if st.session_state.monthly_edited:
            st.rerun()

with tab2:
    st.caption("Weekly or bi-weekly recurring items (e.g., groceries every Saturday)")
    
    edited_weekly_df = st.data_editor(
        st.session_state.weekly_data,
        num_rows="dynamic",
        column_config={
            "Active": st.column_config.CheckboxColumn(required=True),
            "Type": st.column_config.SelectboxColumn(
                options=["Bill", "Income"], 
                required=True
            ), 
            "Name": st.column_config.TextColumn(required=True),
            "Category": st.column_config.TextColumn(),
            "Amount": st.column_config.NumberColumn(
                format="$%.2f",
                required=True,
                min_value=0.0,
                step=1.0
            ), 
            "Freq": st.column_config.SelectboxColumn(
                options=["Weekly", "Bi-Weekly"], 
                required=True,
                help="Weekly = every 7 days, Bi-Weekly = every 14 days"
            ), 
            "Day Name": st.column_config.SelectboxColumn(
                options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                required=True
            )
        },
        use_container_width=True,
        key="weekly_editor",
        hide_index=True
    )
    
    if not edited_weekly_df.equals(st.session_state.weekly_data):
        st.session_state.weekly_data = edited_weekly_df
        if st.session_state.weekly_edited:
            st.rerun()

with tab3:
    st.caption("One-time or irregular items (e.g., vacation, tax refund, annual fees)")
    
    edited_onetime_df = st.data_editor(
        st.session_state.onetime_data,
        num_rows="dynamic",
        column_config={
            "Active": st.column_config.CheckboxColumn(required=True),
            "Type": st.column_config.SelectboxColumn(
                options=["Bill", "Income"], 
                required=True
            ), 
            "Name": st.column_config.TextColumn(required=True),
            "Category": st.column_config.TextColumn(),
            "Amount": st.column_config.NumberColumn(
                format="$%.2f",
                required=True,
                min_value=0.0,
                step=1.0
            ), 
            "Date": st.column_config.DateColumn(
                "Date",
                format="MM/DD/YYYY",
                required=True,
                help="Specific date for this transaction"
            )
        },
        use_container_width=True,
        key="onetime_editor",
        hide_index=True
    )
    
    if not edited_onetime_df.equals(st.session_state.onetime_data):
        st.session_state.onetime_data = edited_onetime_df
        if st.session_state.onetime_edited:
            st.rerun()

# --- 9. MONTHLY SOLVENCY CHECK ---
st.divider()
st.subheader("📊 Monthly Solvency Analysis")

if st.button("Calculate MTM Solvency", use_container_width=True, type="secondary"):
    # A. ESTIMATED AVERAGES (Quick View)
    total_income_est = 0.0
    total_bills_est = 0.0
    
    with st.spinner("Calculating monthly averages..."):
        # Monthly Table
        for _, row in st.session_state.mon

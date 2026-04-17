import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objs as go
import plotly.express as px
from scripts.data_fetcher import fetch_financial_data, extract_key_metrics
from scripts.dcf_model import calculate_wacc, project_financials, compute_intrinsic_value
from scripts.sensitivity import generate_sensitivity_matrix, compare_multiples

# --- Page Config ---
st.set_page_config(page_title="Blanco DCF Framework", layout="wide", page_icon="💹")

st.markdown("""
<style>
    /* Metric Card Styling */
    .huge-summary {
        font-size: 26px !important;
        font-weight: 700 !important;
        line-height: 1.6;
        color: #E2E8F0;
        margin-top: 20px;
    }
    .highlight-green {
        color: #00FFAA !important;
        font-size: 28px !important;
        font-weight: 900 !important;
    }
    .highlight-blue {
        color: #3388FF !important;
        font-size: 28px !important;
        font-weight: 900 !important;
    }
    .highlight-red {
        color: #FF4444 !important;
        font-size: 28px !important;
        font-weight: 900 !important;
    }
    .metric-card {
        background-color: #1E293B;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 14px;
        border: 1px solid #334155;
        box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    }
    .metric-label {
        font-size: 16px;
        color: #94A3B8;
        margin-bottom: 6px;
        font-weight: 600;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 800;
        color: #F8FAFC;
    }
    /* Sidebars and standard text */
    html, body, p, div, span, label {
        font-size: 18px;
    }
    div[data-testid="stSidebar"] label {
        font-size: 18px !important;
        font-weight: 600 !important;
        padding-bottom: 6px;
    }
    div[data-testid="stSidebar"] h2, div[data-testid="stSidebar"] h3 {
        font-size: 24px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Cache Data Fetching ---
@st.cache_resource(show_spinner="Connecting to Yahoo Finance...")
def get_data(ticker):
    data_dict = fetch_financial_data(ticker)
    df_metrics, current_metrics = extract_key_metrics(data_dict)
    return data_dict, df_metrics, current_metrics

# --- Header ---
st.markdown("<h1 style='font-size: 46px; font-weight: 900; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 30px; color: #F8FAFC;'>Blanco DCF & Valuation Dashboard</h1>", unsafe_allow_html=True)

# --- Sidebar Controls ---
st.sidebar.header("Model Parameters")
ticker = st.sidebar.text_input("Stock Ticker", value="MSFT").upper()

try:
    data_dict, df_metrics, current_metrics = get_data(ticker)
    
    st.sidebar.markdown("---")
    
    # 2. Metric to use in calculations (Dropdown)
    metric_map = {
        'EV/EBITDA': 'Historical EV/EBITDA',
        'P/E': 'Historical P/E',
        'Price/FCF': 'Historical P/FCF',
        'EV/Rev': 'Historical EV/Rev',
        'Price/OCF': 'Historical P/OCF'
    }
    target_metric = st.sidebar.selectbox("Metric to use in calculations", options=list(metric_map.keys()))
    
    # 3. Number of years to project
    years_to_project = st.sidebar.number_input("Number of years to project", min_value=1, max_value=20, value=5, step=1)
    
    # 4. How fast will the metric grow
    rev_growth_override = st.sidebar.slider("How fast will the metric grow (%)", min_value=-20.0, max_value=100.0, value=15.0, step=1.0) / 100.0
    
    # 5. Growth decay rate
    growth_decay_rate = st.sidebar.slider("Growth decay rate (/yr %)", min_value=0.0, max_value=20.0, value=2.0, step=0.1) / 100.0
    
    # 6. Metric ratio
    historical_avg_multiple = current_metrics.get(metric_map[target_metric], 15.0)
    multiple_override = st.sidebar.number_input(f"Metric ratio (5Y Avg = {historical_avg_multiple:.2f}x)", value=float(historical_avg_multiple), step=0.5)
    
    # 7. What rate of return do you want
    base_wacc_default = calculate_wacc(current_metrics)
    wacc_pct = st.sidebar.slider("What rate of return do you want (%)", min_value=1.0, max_value=30.0, value=float(base_wacc_default*100), step=0.1) / 100.0
    
    # 8. How fast will dividends grow
    dividend_growth_rate = st.sidebar.slider("How fast will dividends grow (%)", min_value=0.0, max_value=50.0, value=5.0, step=1.0) / 100.0
    
    tgr = 0.02 # Fixed reference for sensitivity matrix bounds
    
    # --- Backend Mathematics ---
    proj_df = project_financials(
        df_metrics, 
        projection_years=years_to_project, 
        rev_growth_override=rev_growth_override, 
        ebit_margin_override=None,
        growth_decay_rate=growth_decay_rate
    )
    
    intrinsic = compute_intrinsic_value(
        proj_df, current_metrics, wacc_pct, 
        terminal_growth_rate=tgr,
        target_multiple_type=target_metric,
        target_multiple_value=multiple_override,
        years_to_project=years_to_project,
        dividend_growth_rate=dividend_growth_rate
    )
    
    comps = compare_multiples(intrinsic, current_metrics, df_metrics)
    matrix = generate_sensitivity_matrix(
        proj_df, current_metrics, wacc_pct, target_metric, multiple_override, 
        years_to_project, dividend_growth_rate
    )
    
    # --- Tear Sheet (Top of Main Page) ---
    col1, col2 = st.columns([1.8, 1])
    
    current_price = current_metrics.get('Current Price', 0)
    fair_value = intrinsic['Implied Price']
    cagr = intrinsic['CAGR'] * 100
    upside_pct = ((fair_value / current_price) - 1) * 100 if current_price > 0 else 0
    status = "undervalued" if upside_pct > 0 else "overvalued"
    
    # Determine Status Color
    status_class = "highlight-green" if upside_pct > 0 else "highlight-red"
    cagr_class = "highlight-green" if cagr > 0 else "highlight-red"
    
    with col1:
        st.markdown(f'''
        <div class="huge-summary">
            Based on your inputs, <span class="highlight-green">{ticker}</span> is 
            <span class="{status_class}">{abs(upside_pct):.1f}% {status}</span> and would produce a CAGR of 
            <span class="{cagr_class}">{cagr:.1f}%</span> from today's share price.<br><br>
            You would need to buy at <span class="highlight-blue">${fair_value:,.2f}</span> to achieve your desired return of {wacc_pct*100:.1f}%.
        </div>
        ''', unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Today's Stock Price</div>
            <div class="metric-value">${current_price:,.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Future Stock Price</div>
            <div class="metric-value">${intrinsic['Future Stock Price']:,.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Total Dividends Paid</div>
            <div class="metric-value">${intrinsic['Total Dividends Paid']:,.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">DCF Fair Value</div>
            <div class="metric-value" style="color: #3388FF;">${fair_value:,.2f}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Expected CAGR</div>
            <div class="metric-value" style="color: {'#00FFAA' if cagr > 0 else '#FF4444'};">{cagr:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)
        
    # --- Main Dashboard Chart ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    hist_prices = data_dict.get('historical_prices', pd.DataFrame())
    if not hist_prices.empty:
        fig_line = go.Figure()
        
        # Historical Trace (Stock Price)
        fig_line.add_trace(go.Scatter(
            x=hist_prices.index, 
            y=hist_prices['Close'],
            mode='lines',
            name='Stock Price Historical',
            line=dict(color='white', width=2),
            showlegend=False
        ))
        
        # Calculate Future Projections
        last_date = hist_prices.index[-1]
        future_date = last_date + pd.DateOffset(years=years_to_project)
        
        # 1. DCF Fair Value Path (Compounding at WACC)
        dcf_dates = [last_date]
        dcf_values = [fair_value]
        for i in range(1, years_to_project + 1):
            dcf_dates.append(last_date + pd.DateOffset(years=i))
            dcf_values.append(fair_value * ((1 + wacc_pct) ** i))
            
        fig_line.add_trace(go.Scatter(
            x=dcf_dates, 
            y=dcf_values,
            mode='lines+markers',
            name='DCF Fair Value Price',
            line=dict(color='#3388FF', width=3)
        ))
        
        # 2. Stock Price (Projecting to match terminal DCF value as a dotted white line)
        fig_line.add_trace(go.Scatter(
            x=[last_date, future_date], 
            y=[current_price, dcf_values[-1]],
            mode='lines',
            name='Stock Price',
            line=dict(color='white', dash='dash', width=2)
        ))
        

        fig_line.update_layout(
            title=dict(text=f"Historical Price & Value Projection", font=dict(size=26)),
            xaxis=dict(title=dict(text="Date", font=dict(size=18)), tickfont=dict(size=14)),
            yaxis=dict(title=dict(text="Stock Price ($)", font=dict(size=18)), tickfont=dict(size=14)),
            legend=dict(
                font=dict(size=16), 
                orientation="h", 
                yanchor="bottom", 
                y=1.02, 
                xanchor="right", 
                x=1
            ),
            plot_bgcolor='#121212',
            paper_bgcolor='#121212',
            height=650,
            template="plotly_dark",
            hovermode="x unified",
            margin=dict(l=40, r=40, t=60, b=40)
        )
        
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.warning("Historical price data could not be parsed.")
    
    st.markdown("---")
    
    # --- Tabbed Navigation ---
    tab_dashboard, tab_financials = st.tabs([
        "📊 Projection Deep Dive", 
        "📝 Financial Statements", 
    ])
    
    with tab_dashboard:
        st.subheader("Model Projections & Sensitivity")
        
        col_bar, col_heat = st.columns([1, 1])
        
        with col_bar:
            st.markdown(f"**Projected Cash Flows**")
            fcf_data = proj_df[['FCF']].copy()
            fcf_data.index.name = 'Year'
            fig_bar = px.bar(
                fcf_data, 
                x=fcf_data.index, 
                y='FCF',
                text_auto='.2s',
                color_discrete_sequence=['#1E293B'],
            )
            fig_bar.update_layout(
                xaxis_title="Projection Year", 
                yaxis_title="Free Cash Flow ($)",
                plot_bgcolor='#0E1117',
                paper_bgcolor='#0E1117',
            )
            fig_bar.update_traces(marker_color='#00FFAA')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_heat:
            st.markdown(f"**Sensitivity Analysis: WACC vs. Target Multiple**")
            st.image('sensitivity_heatmap.png', use_container_width=True)
            
        st.markdown(f"**Detailed Projections**")
        st.dataframe(proj_df.style.format("{:,.2f}"), use_container_width=True)
            
    with tab_financials:
        st.subheader("Reported Financial Statements")
        st.markdown("*Data sourced from Yahoo Finance.*")
        
        st.markdown("### Income Statement")
        st.dataframe(data_dict['income_stmt'].style.format("{:,.0f}"), use_container_width=True)
        
        st.markdown("### Balance Sheet")
        st.dataframe(data_dict['balance_sheet'].style.format("{:,.0f}"), use_container_width=True)
        
        st.markdown("### Cash Flow Statement")
        st.dataframe(data_dict['cash_flow'].style.format("{:,.0f}"), use_container_width=True)

except Exception as e:
    st.error(f"Waiting for valid Ticker or Error occurred: {e}")

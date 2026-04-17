import pandas as pd
import numpy as np

def calculate_wacc(current_metrics, wacc_override=None):
    if wacc_override is not None:
        return wacc_override
        
    beta = current_metrics['Beta']
    rf_rate = current_metrics['Risk Free Rate']
    rm_rate = current_metrics['Market Return']
    mkt_cap = current_metrics['Market Cap']
    total_debt = current_metrics['Total Debt']
    cost_of_debt = current_metrics['Cost of Debt']
    tax_rate = 0.21 # Approximate corporate tax rate
    
    cost_of_equity = rf_rate + beta * (rm_rate - rf_rate)
    
    total_capital = mkt_cap + total_debt
    if total_capital == 0:
        return cost_of_equity
        
    weight_equity = mkt_cap / total_capital
    weight_debt = total_debt / total_capital
    
    wacc = (weight_equity * cost_of_equity) + (weight_debt * cost_of_debt * (1 - tax_rate))
    return wacc

def project_financials(hist_df, projection_years=5, rev_growth_override=None, ebit_margin_override=None, growth_decay_rate=0.0):
    """
    Project free cash flows based on historical averages or overrides.
    Returns a DataFrame with projected metrics and Free Cash Flow.
    """
    # YoY revenues
    if rev_growth_override is not None:
        avg_rev_growth = rev_growth_override
    else:
        rev_pct = hist_df['Revenue'].astype(float).pct_change().dropna()
        avg_rev_growth = rev_pct.mean() if not rev_pct.empty else 0.05
        avg_rev_growth = min(max(avg_rev_growth, 0.0), 0.25)
    
    # Replace inf and safely calculate margins
    def safe_div(a, b):
        with np.errstate(divide='ignore', invalid='ignore'):
            c = a / b
            if isinstance(c, np.ndarray):
                c = np.nan_to_num(c, posinf=0, neginf=0)
            return pd.Series(c).fillna(0)

    # Margins
    if ebit_margin_override is not None:
        avg_ebit_margin = ebit_margin_override
    else:
        ebit_margin = safe_div(hist_df['EBIT'], hist_df['Revenue'])
        avg_ebit_margin = ebit_margin.mean()
    
    tax_rate_avg = hist_df['Tax Rate'].mean()
    
    da_margin = safe_div(hist_df['D&A'], hist_df['Revenue'])
    avg_da_margin = da_margin.mean()
    
    capex_margin = safe_div(hist_df['CapEx'].astype(float).abs(), hist_df['Revenue'])
    avg_capex_margin = capex_margin.mean()
    
    nwc_margin = safe_div(hist_df['NWC'], hist_df['Revenue'])
    avg_nwc_margin = nwc_margin.mean()
    
    last_rev = float(hist_df['Revenue'].iloc[-1])
    
    projected_years = [f"Year {i}" for i in range(1, projection_years + 1)]
    proj = pd.DataFrame(index=projected_years, columns=['Revenue', 'EBIT', 'Taxes', 'NOPAT', 'D&A', 'CapEx', 'Change in NWC', 'FCF'])
    
    prev_rev = last_rev
    prev_nwc = float(hist_df['NWC'].iloc[-1])
    
    for i, year in enumerate(projected_years):
        # Step down growth rate by the decay rate (floor at 0.02)
        current_growth = max(avg_rev_growth - (i * growth_decay_rate), 0.02)
        
        rev = prev_rev * (1 + current_growth)
        ebit = rev * avg_ebit_margin
        taxes = ebit * tax_rate_avg
        nopat = ebit - taxes
        
        da = rev * avg_da_margin
        capex = rev * avg_capex_margin
        
        target_nwc = rev * avg_nwc_margin
        dnwc = target_nwc - prev_nwc
        
        fcf = nopat + da - capex - dnwc
        
        proj.loc[year] = {
            'Revenue': rev,
            'EBIT': ebit,
            'Taxes': taxes,
            'NOPAT': nopat,
            'D&A': da,
            'CapEx': capex,
            'Change in NWC': dnwc,
            'FCF': fcf
        }
        
        prev_rev = rev
        prev_nwc = target_nwc
        
    return proj

def compute_intrinsic_value(proj_df, current_metrics, wacc, terminal_growth_rate=0.02, target_multiple_type=None, target_multiple_value=None, years_to_project=5, dividend_growth_rate=0.0):
    """
    Computes Intrinsic Equity Value, Future Stock Price, Total Dividends, and CAGR.
    """
    fcf = proj_df['FCF'].astype(float).values
    
    discount_factors = np.array([1 / ((1 + wacc) ** i) for i in range(1, len(fcf) + 1)])
    pv_fcf = np.sum(fcf * discount_factors)
    
    terminal_fcf = fcf[-1] * (1 + terminal_growth_rate)
    
    # TV Calculations and Future Stock Price
    future_equity_value = 0
    if target_multiple_type and target_multiple_value:
        year_n_nopat = float(proj_df['NOPAT'].iloc[-1])
        year_n_ebitda = float(proj_df['EBIT'].iloc[-1]) + float(proj_df['D&A'].iloc[-1])
        year_n_fcf = float(proj_df['FCF'].iloc[-1])
        year_n_rev = float(proj_df['Revenue'].iloc[-1])
        year_n_ocf = year_n_nopat + float(proj_df['D&A'].iloc[-1]) # Approx OCF
        
        if target_multiple_type == 'EV/EBITDA':
            terminal_value = target_multiple_value * year_n_ebitda
            future_equity_value = terminal_value - current_metrics['Total Debt'] + current_metrics['Cash']
        elif target_multiple_type == 'EV/Rev':
            terminal_value = target_multiple_value * year_n_rev
            future_equity_value = terminal_value - current_metrics['Total Debt'] + current_metrics['Cash']
        elif target_multiple_type in ['P/E', 'Price/FCF', 'Price/OCF']:
            if target_multiple_type == 'P/E': terminal_equity = target_multiple_value * year_n_nopat
            elif target_multiple_type == 'Price/FCF': terminal_equity = target_multiple_value * year_n_fcf
            elif target_multiple_type == 'Price/OCF': terminal_equity = target_multiple_value * year_n_ocf
            terminal_value = terminal_equity + current_metrics['Total Debt'] - current_metrics['Cash']
            future_equity_value = terminal_equity
        else:
            terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
            future_equity_value = terminal_value - current_metrics['Total Debt'] + current_metrics['Cash']
    else:
        if wacc <= terminal_growth_rate:
            wacc = terminal_growth_rate + 0.01
        terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
        future_equity_value = terminal_value - current_metrics['Total Debt'] + current_metrics['Cash']
        
    pv_tv = terminal_value * discount_factors[-1]
    
    enterprise_value = pv_fcf + pv_tv
    equity_value = enterprise_value + current_metrics['Cash'] - current_metrics['Total Debt']
    
    shares_out = current_metrics['Shares Outstanding']
    implied_share_price = equity_value / shares_out if shares_out > 0 else 0
    future_stock_price = future_equity_value / shares_out if shares_out > 0 else 0
    
    # DIVIDENDS & CAGR
    current_div = current_metrics.get('Dividend Per Share', 0)
    total_dividends_paid = 0
    current_div_acc = current_div
    for _ in range(years_to_project):
        if current_div_acc > 0: # Only grow if it pays a dividend
            current_div_acc *= (1 + dividend_growth_rate)
            total_dividends_paid += current_div_acc
        
    current_price = current_metrics.get('Current Price', 0)
    if current_price > 0:
        total_future_value = future_stock_price + total_dividends_paid
        cagr = (total_future_value / current_price) ** (1 / years_to_project) - 1
    else:
        cagr = 0
        
    return {
        'PV of FCF': pv_fcf,
        'Terminal Value': terminal_value,
        'PV of TV': pv_tv,
        'Enterprise Value': enterprise_value,
        'Equity Value': equity_value,
        'Implied Price': implied_share_price,
        'WACC': wacc,
        'Terminal Growth': terminal_growth_rate,
        'Future Stock Price': future_stock_price,
        'Total Dividends Paid': total_dividends_paid,
        'CAGR': cagr
    }

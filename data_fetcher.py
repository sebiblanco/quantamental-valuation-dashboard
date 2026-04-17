import yfinance as yf
import pandas as pd
import numpy as np

def fetch_financial_data(ticker_symbol: str):
    """
    Fetches historical financial data for a given ticker using Yahoo Finance.
    Returns a dictionary of Income Statement, Balance Sheet, and Cash Flow statement data.
    """
    print(f"Fetching data for {ticker_symbol} from Yahoo Finance...")
    ticker = yf.Ticker(ticker_symbol)
    
    income_stmt = ticker.financials
    balance_sheet = ticker.balance_sheet
    cash_flow = ticker.cashflow
    
    if income_stmt.empty or balance_sheet.empty or cash_flow.empty:
        raise ValueError(f"Could not retrieve complete financial data for {ticker_symbol}. Check if the ticker is valid.")
        
    info = ticker.info
    
    # Sort columns so oldest is first, newest is last
    income_stmt = income_stmt[sorted(income_stmt.columns)]
    balance_sheet = balance_sheet[sorted(balance_sheet.columns)]
    cash_flow = cash_flow[sorted(cash_flow.columns)]

    # Fetch 5 years of monthly historical prices
    historical_prices = ticker.history(period="5y", interval="1mo")

    return {
        "income_stmt": income_stmt,
        "balance_sheet": balance_sheet,
        "cash_flow": cash_flow,
        "info": info,
        "ticker_obj": ticker,
        "historical_prices": historical_prices
    }

def extract_key_metrics(data_dict):
    """
    Extracts essential metrics needed for a basic DCF calculation from yfinance DataFrames.
    """
    inc = data_dict['income_stmt']
    bs = data_dict['balance_sheet']
    cf = data_dict['cash_flow']
    
    years = inc.columns
    
    def get_row(df, row_name):
        if row_name in df.index:
            return df.loc[row_name].fillna(0)
        return pd.Series([0.0]*len(years), index=years)

    # Income Statement
    revenue = get_row(inc, 'Total Revenue')
    ebit = get_row(inc, 'EBIT')
    if ebit.sum() == 0 and 'Operating Income' in inc.index:
        ebit = get_row(inc, 'Operating Income')
        
    pretax_income = get_row(inc, 'Pretax Income')
    tax_provision = get_row(inc, 'Tax Provision')
    
    # Handle division by zero for tax rate and cap between 0 and 1
    with np.errstate(divide='ignore', invalid='ignore'):
        tax_rate = np.where(pretax_income > 0, tax_provision / pretax_income, 0.25)
    tax_rate = pd.Series(tax_rate, index=years)
    tax_rate = tax_rate.clip(lower=0, upper=1).fillna(0.25)
    
    # Balance Sheet
    current_assets = get_row(bs, 'Current Assets')
    if current_assets.sum() == 0: current_assets = get_row(bs, 'Total Current Assets')
        
    current_liabilities = get_row(bs, 'Current Liabilities')
    if current_liabilities.sum() == 0: current_liabilities = get_row(bs, 'Total Current Liabilities')
        
    nwc = current_assets - current_liabilities
    
    total_debt = get_row(bs, 'Total Debt')
    cash = get_row(bs, 'Cash And Cash Equivalents')
    if cash.sum() == 0: cash = get_row(bs, 'Cash')
    
    # Cash Flow
    da = get_row(cf, 'Depreciation And Amortization')
    if da.sum() == 0: da = get_row(cf, 'Depreciation')
        
    capex = get_row(cf, 'Capital Expenditure')
    # Yahoo finance usually returns CapEx as a negative number
    
    net_income = get_row(inc, 'Net Income')
    operating_cf = get_row(cf, 'Operating Cash Flow')
    if operating_cf.sum() == 0: operating_cf = get_row(cf, 'Total Cash From Operating Activities')
    
    df_metrics = pd.DataFrame({
        'Revenue': revenue,
        'EBIT': ebit,
        'Tax Rate': tax_rate,
        'D&A': da,
        'CapEx': capex,
        'NWC': nwc
    })
    
    info = data_dict.get('info', {})
    
    shares = info.get('sharesOutstanding', 1e7)
    
    current_dividend = info.get('dividendRate', info.get('trailingAnnualDividendRate', 0))
    if current_dividend is None:
        current_dividend = 0
    
    # Calculate historical multiples
    hist_prices = data_dict.get('historical_prices', pd.DataFrame())
    pe_arr, ev_ebitda_arr, p_fcf_arr, ev_rev_arr, p_ocf_arr = [], [], [], [], []
    
    for i, year_col in enumerate(years):
        try:
            year_val = year_col.year
            prices_that_year = hist_prices[hist_prices.index.year == year_val]['Close']
            if not prices_that_year.empty:
                avg_price = prices_that_year.mean()
            else:
                avg_price = info.get('currentPrice', info.get('regularMarketPrice', 1))
        except:
            avg_price = info.get('currentPrice', info.get('regularMarketPrice', 1))
            
        mkt_cap = avg_price * shares
        debt_yr = total_debt.iloc[i] if not total_debt.empty else 0
        cash_yr = cash.iloc[i] if not cash.empty else 0
        ev_yr = mkt_cap + debt_yr - cash_yr
        
        ni_yr = net_income.iloc[i]
        ebitda_yr = ebit.iloc[i] + da.iloc[i]
        cap_val = abs(capex.iloc[i]) if capex.iloc[i] != 0 else 0
        fcf_yr = operating_cf.iloc[i] - cap_val
        rev_yr = revenue.iloc[i]
        ocf_yr = operating_cf.iloc[i]
        
        # Calculate multiples avoiding division by zero
        pe_arr.append(mkt_cap / ni_yr if ni_yr > 0 else np.nan)
        ev_ebitda_arr.append(ev_yr / ebitda_yr if ebitda_yr > 0 else np.nan)
        p_fcf_arr.append(mkt_cap / fcf_yr if fcf_yr > 0 else np.nan)
        ev_rev_arr.append(ev_yr / rev_yr if rev_yr > 0 else np.nan)
        p_ocf_arr.append(mkt_cap / ocf_yr if ocf_yr > 0 else np.nan)
        
    avg_pe = np.nanmean(pe_arr) if not np.isnan(pe_arr).all() else 0
    avg_ev_ebitda = np.nanmean(ev_ebitda_arr) if not np.isnan(ev_ebitda_arr).all() else 0
    avg_p_fcf = np.nanmean(p_fcf_arr) if not np.isnan(p_fcf_arr).all() else 0
    avg_ev_rev = np.nanmean(ev_rev_arr) if not np.isnan(ev_rev_arr).all() else 0
    avg_p_ocf = np.nanmean(p_ocf_arr) if not np.isnan(p_ocf_arr).all() else 0
    
    # Fetch current risk free rate using 10 Year Treasury Yield (^TNX)
    try:
        tnx = yf.Ticker("^TNX")
        rf_rate = tnx.history(period="1d")['Close'].iloc[-1] / 100.0
    except:
        rf_rate = 0.042
        
    current_metrics = {
        'Beta': info.get('beta', 1.1),
        'Market Cap': info.get('marketCap', shares * info.get('currentPrice', 10)),
        'Total Debt': total_debt.iloc[-1] if not total_debt.empty else 0,
        'Cash': cash.iloc[-1] if not cash.empty else 0,
        'Shares Outstanding': shares,
        'Cost of Debt': 0.05, # Simplification
        'Risk Free Rate': rf_rate,
        'Market Return': 0.10,
        'Current Price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
        'Dividend Per Share': current_dividend,
        'Historical P/E': avg_pe,
        'Historical EV/EBITDA': avg_ev_ebitda,
        'Historical P/FCF': avg_p_fcf,
        'Historical EV/Rev': avg_ev_rev,
        'Historical P/OCF': avg_p_ocf
    }
    
    return df_metrics, current_metrics

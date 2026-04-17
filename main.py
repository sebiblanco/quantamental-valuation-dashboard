import sys
import pandas as pd
from tabulate import tabulate
from scripts.data_fetcher import fetch_financial_data, extract_key_metrics
from scripts.dcf_model import calculate_wacc, project_financials, compute_intrinsic_value
from scripts.sensitivity import generate_wacc_tgr_matrix, compare_multiples

def main():
    print("Welcome to the Automated Valuation & DCF Framework.\n")
    ticker = "AAPL"
    if len(sys.argv) > 1:
        ticker = sys.argv[1].strip().upper()
        
    print(f"--- 1. Fetching Data for {ticker} ---")
    try:
        data_dict = fetch_financial_data(ticker)
        df_metrics, current_metrics = extract_key_metrics(data_dict)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return
        
    print("\n--- 5-Year Historical Averages ---")
    print(f"P/E: {current_metrics.get('Historical P/E', 0):.2f}x")
    print(f"EV/EBITDA: {current_metrics.get('Historical EV/EBITDA', 0):.2f}x")
    print(f"Price/FCF: {current_metrics.get('Historical P/FCF', 0):.2f}x")
    print(f"EV/Revenue: {current_metrics.get('Historical EV/Rev', 0):.2f}x")
    print(f"Price/OCF: {current_metrics.get('Historical P/OCF', 0):.2f}x")
        
    print("\n--- 2. Projecting Cash Flows ---")
    # For forward-looking tech stocks, we can override historical averages
    # e.g., 15% Revenue Growth, 40% Operating Margin, 2% growth decay per year
    proj_df = project_financials(
        df_metrics, 
        projection_years=5, 
        rev_growth_override=0.15, 
        ebit_margin_override=0.40,
        growth_decay_rate=0.02
    )
    print(tabulate(proj_df, headers='keys', tablefmt='psql', floatfmt=".2f"))
    
    print("\n--- 3. Running DCF Valuation ---")
    wacc = calculate_wacc(current_metrics, wacc_override=0.09)
    # Using the new EV/EBITDA Multiple Method
    target_mult = current_metrics.get('Historical EV/EBITDA', 15.0)
    intrinsic = compute_intrinsic_value(
        proj_df, current_metrics, wacc, 
        terminal_growth_rate=0.02,
        target_multiple_type='EV/EBITDA',
        target_multiple_value=target_mult
    )
    
    print(f"Calculated WACC (Override): {wacc*100:.2f}%")
    print(f"Terminal Method: EV/EBITDA Multiple ({target_mult:.2f}x)")
    print(f"Implied Share Price: ${intrinsic['Implied Price']:.2f}")
    
    print("\n--- 4. Sensitivity Analysis ---")
    matrix = generate_wacc_tgr_matrix(proj_df, current_metrics, wacc, 0.02)
    print("Sensitivity Matrix: Implied Share Price vs WACC and TGR")
    print(tabulate(matrix, headers='keys', tablefmt='psql', floatfmt=".2f"))
    
    print("\n--- 5. Market Multiples Comparison ---")
    comps = compare_multiples(intrinsic, current_metrics, df_metrics)
    comp_df = pd.DataFrame([comps]).T
    comp_df.columns = ['Value']
    print(tabulate(comp_df, headers='keys', tablefmt='psql'))

if __name__ == "__main__":
    pd.set_option('display.float_format', lambda x: '%.2f' % x)
    main()

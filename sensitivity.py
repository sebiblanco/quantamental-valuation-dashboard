import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

def generate_sensitivity_matrix(proj_df, current_metrics, base_wacc, target_metric, base_multiple, years_to_project=5, dividend_growth_rate=0.0):
    """
    Generates a sensitivity table for Intrinsic Share Price based on varying WACC and Target Multiple.
    Saves a heatmap visualization to the root folder.
    """
    from dcf_model import compute_intrinsic_value
    
    multipliers = [0.8, 0.9, 1.0, 1.1, 1.2]
    wacc_range = [base_wacc * m for m in multipliers]
    multiple_range = [base_multiple * m for m in multipliers]
    
    matrix = pd.DataFrame(
        index=[f"WACC: {w*100:.1f}%" for w in wacc_range], 
        columns=[f"{target_metric}: {m:.1f}x" for m in multiple_range]
    )
    
    for i, w in enumerate(wacc_range):
        for j, m_val in enumerate(multiple_range):
            res = compute_intrinsic_value(
                proj_df, 
                current_metrics, 
                w, 
                terminal_growth_rate=0.02, # default baseline
                target_multiple_type=target_metric,
                target_multiple_value=m_val,
                years_to_project=years_to_project,
                dividend_growth_rate=dividend_growth_rate
            )
            matrix.iloc[i, j] = res['Implied Price']
            
    # Convert matrix to float for plotting
    matrix_float = matrix.astype(float)
    
    # Generate Heatmap
    plt.figure(figsize=(10, 8))
    current_price = current_metrics.get('Current Price', matrix_float.values.mean())
    
    # Force symmetrical coloring around current market price
    max_dev = max(abs(matrix_float.values.max() - current_price), abs(matrix_float.values.min() - current_price))
    vmin = current_price - max_dev
    vmax = current_price + max_dev
    
    sns.heatmap(matrix_float, annot=True, annot_kws={"size": 14}, fmt=".2f", cmap="RdYlGn", center=current_price, vmin=vmin, vmax=vmax)
    plt.title(f"Sensitivity Analysis: Intrinsic Value vs. WACC & {target_metric}", fontsize=18, pad=20)
    plt.tight_layout()
    plt.savefig('sensitivity_heatmap.png')
    plt.close()
            
    return matrix

def compare_multiples(intrinsic_results, current_metrics, hist_df):
    """
    Compares DCF implied metrics against current market observations.
    """
    current_price = current_metrics.get('Current Price', 0)
    implied_price = intrinsic_results['Implied Price']
    
    last_ebit = float(hist_df['EBIT'].iloc[-1])
    
    current_market_cap = current_price * current_metrics['Shares Outstanding']
    current_ev = current_market_cap + current_metrics['Total Debt'] - current_metrics['Cash']
    
    current_ev_ebit = current_ev / last_ebit if last_ebit > 0 else 0
    implied_ev_ebit = intrinsic_results['Enterprise Value'] / last_ebit if last_ebit > 0 else 0
    
    return {
        'Current Share Price ($)': current_price,
        'DCF Implied Price ($)': implied_price,
        'Upside / (Downside)': f"{(implied_price / current_price - 1)*100:.1f}%" if current_price > 0 else "N/A",
        'Current EV / EBIT': current_ev_ebit,
        'Implied EV / EBIT': implied_ev_ebit
    }

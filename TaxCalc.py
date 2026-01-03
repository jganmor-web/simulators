import streamlit as st
import pandas as pd
import requests

# --- יישור לימין (RTL) באמצעות CSS ---
st.markdown("""
    <style>
    .reportview-container .main .block-container, .main, .stApp {
        direction: RTL;
        text-align: right;
    }
    div[data-testid="stMetricValue"] {
        direction: RTL;
    }
    div[data-testid="stMarkdownContainer"] {
        text-align: right;
    }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציית משיכת שערי חליפין ---
def get_exchange_rates():
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/ILS")
        data = response.json()
        rates = data['rates']
        return {"ILS": 1.0, "USD": 1 / rates['USD'], "EUR": 1 / rates['EUR'], "AUD": 1 / rates['AUD'], "CAD": 1 / rates['CAD']}
    except:
        return {"ILS": 1.0, "USD": 3.7, "EUR": 4.0, "AUD": 2.4, "CAD": 2.7}

# --- קבועי מס 2026 ---
VALUE_PER_POINT = 242 #
SS_LOW_LIMIT = 7522   #
SS_MAX_CAP = 49030    #

def calc_detailed_taxes_ils(annual_taxable_ils, points, is_resident):
    """חישוב מפורט של מיסים - מעוגל לשקלים שלמים"""
    # 1. מס הכנסה
    it_brackets = [
        (0, 84120, 0.10), (84120, 120720, 0.14), (120720, 174360, 0.20),
        (174360, 242400, 0.31), (242400, 504360, 0.35), (504360, 721560, 0.47),
        (721560, float('inf'), 0.50)
    ]
    it_total, it_table = 0, []
    for start, end, rate in it_brackets:
        if annual_taxable_ils > start:
            taxable = min(annual_taxable_ils, end) - start
            tax = taxable * rate
            it_total += tax
            it_table.append({
                "מדרגה": f"{int(rate*100)}%", 
                "סכום חודשי": int(round(taxable/12, 0)), 
                "מס חודשי": int(round(tax/12, 0))
            })
    it_after_credits = max(0, it_total - (points * VALUE_PER_POINT * 12))
    
    # 2. ביטוח לאומי ומס בריאות
    bl_total, hb_total, bl_table = 0, 0, []
    if is_resident:
        low_ann = SS_LOW_LIMIT * 12
        income_ss = min(annual_taxable_ils, SS_MAX_CAP * 12)
        
        p_low = min(income_ss, low_ann)
        bl_l, hb_l = p_low * 0.0287, p_low * 0.0310
        
        p_high = max(0, income_ss - low_ann)
        bl_h, hb_h = p_high * 0.1283, p_high * 0.05
        
        bl_table.append({
            "טווח": f"עד {SS_LOW_LIMIT}₪", "ב\"ל": int(round(bl_l/12, 0)),
            "בריאות": int(round(hb_l/12, 0)), "סה\"כ חודשי": int(round((bl_l+hb_l)/12, 0))
        })
        bl_table.append({
            "טווח": f"מעל {SS_LOW_LIMIT}₪", "ב\"ל": int(round(bl_h/12, 0)),
            "בריאות": int(round(hb_h/12, 0)), "סה\"כ חודשי": int(round((bl_h+hb_h)/12, 0))
        })
        bl_total, hb_total = bl_l + bl_h, hb_l + hb_h
    else:
        # אתחול טבלה ריקה למניעת NameError
        bl_table = [{"טווח": "ניתוק תושבות", "ב\"ל": 0, "בריאות": 0, "סה\"כ חודשי": 0}]
            
    return it_after_credits, bl_total, hb_total, it_table, bl_table

# --- ממשק משתמש ---
rates = get_exchange_rates()
st.title("⚖️ מחשבון הכנסה ומיסוי לקליניקה (2026)")

with st.sidebar:
    st.header("⚙️ הגדרות עסק")
    in_curr = st.selectbox("מטבע הזנה:", ["ILS", "USD", "EUR", "AUD", "CAD"])
    vat_val = st.selectbox("שיעור מע\"מ:", [0.0, 0.18], format_func=lambda x: f"{int(x*100)}%")
    resident = st.checkbox("תושב ישראל (ב\"ל ומס בריאות)", value=True)
    has_exempt = st.checkbox("יש הכנסה פטורה ממס? (שכירות)", value=False)
    
    st.header("💰 הכנסות")
    h_rate = st.number_input(f"תעריף שעה ({in_curr})", value=450.0, step=50.0 if in_curr=="ILS" else 10.0)
    h_week = st.number_input("מטופלים בשבוע", value=20, step=1)
    w_year = st.slider("שבועות עבודה בשנה", 1, 52, 44)
    
    st.header("📉 הוצאות מוכרות")
    rent_m = st.radio("שכירות קליניקה:", ["חודשי", "לפי שעה"])
    rent_v = st.number_input(f"עלות שכירות ({in_curr})", value=2000.0, step=100.0)
    other = st.number_input(f"שוטפות (הדרכה, ביטוח) ({in_curr})", value=1000.0, step=100.0)
    furn = st.number_input(f"ריהוט (פחת 10 שנים) ({in_curr})", value=0.0, step=500.0)
    
    st.header("🎁 זיכויים")
    pts = st.number_input("נקודות זיכוי", value=2.25, step=0.25)
    rent_p = 0.0
    if has_exempt:
        rent_p = st.number_input(f"שכירות פטורה ({in_curr})", value=0.0, step=500.0)

# --- לוגיקה ---
r_ils = rates[in_curr]
annual_work_gross_ils = (h_rate * r_ils) * h_week * w_year
monthly_rental_ils = rent_p * r_ils
total_monthly_gross_ils = (annual_work_gross_ils / 12) + monthly_rental_ils

rev_no_vat_ils = (h_rate * r_ils / (1 + vat_val)) * h_week * w_year
ann_rent_ils = (rent_v * r_ils / (1 + vat_val)) * (12 if rent_m == "חודשי" else h_week * w_year)
total_exp_ils = ann_rent_ils + (other * r_ils / (1 + vat_val) * 12) + (furn * r_ils / (1 + vat_val) * 0.10)
taxable_ils = max(0, rev_no_vat_ils - total_exp_ils)

it_ils, bl_ils, hb_ils, it_tab, bl_tab = calc_detailed_taxes_ils(taxable_ils, pts, resident)
m_tax_ils = (it_ils + bl_ils + hb_ils) / 12
m_net_ils = (taxable_ils / 12) - m_tax_ils + monthly_rental_ils

# אחוזי מס
eff_taxable = (m_tax_ils / (taxable_ils/12) * 100) if taxable_ils > 0 else 0
eff_total = (m_tax_ils / total_monthly_gross_ils * 100) if total_monthly_gross_ils > 0 else 0

# --- תצוגה ---
st.divider()

# תיבת נטו מובלטת
st.markdown(f"""
    <div style='border: 2px solid #4CAF50; border-radius: 10px; padding: 20px; background-color: #f1f8e9; text-align: center;'>
        <h1 style='color: #2e7d32; margin: 0;'>נטו חודשי ממוצע: ₪{int(round(m_net_ils, 0)):,}</h1>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# שורה 1: הכנסות ורווח
st.subheader("📈 הכנסות ורווח (לפני מס)")
r1_c = st.columns(3 if has_exempt else 2)
r1_c[0].metric("ברוטו חודשי (סה\"כ)", f"₪{int(round(total_monthly_gross_ils, 0)):,}")
r1_c[1].metric("רווח לפני מס (מעבודה)", f"₪{int(round(taxable_ils/12, 0)):,}")
if has_exempt:
    r1_c[2].metric("שכירות פטורה", f"₪{int(round(monthly_rental_ils, 0)):,}")

st.markdown("<br>", unsafe_allow_html=True)

# שורה 2: מיסים
st.subheader("📉 תשלומי חובה ומיסוי")
r2_c = st.columns(4 if has_exempt else 3)
r2_c[0].metric("מס הכנסה", f"₪{int(round(it_ils/12, 0)):,}")
r2_c[1].metric("ב\"ל ומס בריאות", f"₪{int(round((bl_ils+hb_ils)/12, 0)):,}")
r2_c[2].metric("מס אפקטיבי (מהרווח)", f"{eff_taxable:.1f}%")
if has_exempt:
    r2_c[3].metric("מס אפקטיבי (מהכל)", f"{eff_total:.1f}%")

st.divider()

# פירוט מורחב
c_it, c_bl = st.columns(2)
with c_it:
    with st.expander("📂 פירוט מדרגות מס הכנסה"):
        st.table(pd.DataFrame(it_tab))
with c_bl:
    if resident:
        with st.expander("📂 פירוט ביטוח לאומי ומס בריאות"):
            st.table(pd.DataFrame(bl_tab))
    else:
        st.warning("⚠️ ניתוק תושבות פעיל: אין חבות לביטוח לאומי.")

st.divider()
out_curr = st.selectbox("הצג נטו סופי ב-:", ["ILS", "USD", "EUR", "AUD", "CAD"])
st.info(f"נטו במטבע נבחר: {int(round(m_net_ils * (1/rates[out_curr]), 0)):,} {out_curr}")
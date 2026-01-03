import streamlit as st
import pandas as pd
import requests

# --- הגדרות יישור לימין (RTL) ותצוגה ---
st.set_page_config(page_title="מחשבון קליניקה 2026", layout="wide")

st.markdown("""
    <style>
    /* יישור כללי לימין */
    .reportview-container .main .block-container, .main, .stApp {
        direction: RTL;
        text-align: right;
    }
    /* יישור מספרים במטריקות */
    div[data-testid="stMetricValue"] {
        direction: RTL;
    }
    /* יישור תפריט צד */
    section[data-testid="stSidebar"] {
        direction: RTL;
        text-align: right;
    }
    </style>
    """, unsafe_allow_html=True)

# --- פונקציות עזר ---
def get_exchange_rates():
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/ILS")
        rates = response.json()['rates']
        return {"ILS": 1.0, "USD": 1/rates['USD'], "EUR": 1/rates['EUR'], "AUD": 1/rates['AUD']}
    except:
        return {"ILS": 1.0, "USD": 3.7, "EUR": 4.0, "AUD": 2.4}

# קבועי מס 2026
VALUE_PER_POINT = 242  # שווי נקודה
SS_LOW_LIMIT = 7522    # סף ביטוח לאומי
SS_MAX_CAP = 49030     # תקרה

def calc_detailed_taxes_ils(annual_taxable_ils, points, is_resident):
    """חישוב מפורט של מיסים - מעוגל לשקלים"""
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
            it_table.append({"מדרגה": f"{int(rate*100)}%", "סכום חודשי": int(round(taxable/12, 0)), "מס חודשי": int(round(tax/12, 0))})
    
    it_after_credits = max(0, it_total - (points * VALUE_PER_POINT * 12))
    
    # 2. ביטוח לאומי ומס בריאות
    bl_total, hb_total, bl_table = 0, 0, []
    if is_resident:
        low_ann = SS_LOW_LIMIT * 12
        p_low = min(annual_taxable_ils, low_ann)
        bl_l, hb_l = p_low * 0.0287, p_low * 0.0310
        p_high = max(0, annual_taxable_ils - low_ann)
        bl_h, hb_h = p_high * 0.1283, p_high * 0.05
        
        bl_table.append({"טווח": "עד הסף", "ב\"ל": int(round(bl_l/12, 0)), "בריאות": int(round(hb_l/12, 0)), "סה\"כ חודשי": int(round((bl_l+hb_l)/12, 0))})
        bl_table.append({"טווח": "מעל הסף", "ב\"ל": int(round(bl_h/12, 0)), "בריאות": int(round(hb_h/12, 0)), "סה\"כ חודשי": int(round((bl_h+hb_h)/12, 0))})
        bl_total, hb_total = bl_l + bl_h, hb_l + hb_h
    else:
        bl_table = [{"טווח": "ניתוק תושבות", "ב\"ל": 0, "בריאות": 0, "סה\"כ חודשי": 0}]
        
    return it_after_credits, bl_total, hb_total, it_table, bl_table

# ---Sidebar ---
rates = get_exchange_rates()
st.sidebar.header("⚙️ הגדרות עסק")
curr = st.sidebar.selectbox("מטבע תצוגה:", ["ILS", "USD", "EUR", "AUD"])
is_res = st.sidebar.checkbox("תושב ישראל (ב\"ל ומס בריאות)", value=True)
has_exempt = st.sidebar.checkbox("יש הכנסה פטורה ממס (שכירות)?", value=False)

st.sidebar.header("💰 הכנסות")
h_rate = st.sidebar.number_input(f"תעריף לשעת טיפול ({curr})", value=450.0, step=10.0)
h_week = st.sidebar.number_input("כמות מטופלים בשבוע", value=20, step=1)
# החלפת הסליידר בתיבת טקסט מספרית
w_year = st.sidebar.number_input("שבועות עבודה בשנה", value=44, min_value=1, max_value=52, step=1)

st.sidebar.header("📉 הוצאות מוכרות")
rent_v = st.sidebar.number_input(f"עלות שכירות קליניקה ({curr})", value=2000.0, step=100.0)
other = st.sidebar.number_input(f"הוצאות שוטפות/הדרכה ({curr})", value=1000.0, step=100.0)
pts = st.sidebar.number_input("נקודות זיכוי ממס", value=2.25, step=0.25)

# קלט שכירות רק אם רלוונטי
rent_p_val = 0.0
if has_exempt:
    rent_p_val = st.sidebar.number_input(f"הכנסה משכירות פטורה ({curr})", value=0.0, step=500.0)

# --- לוגיקה פיננסית ---
r_ils = rates[curr]
work_gross_ils = (h_rate * r_ils) * h_week * w_year
monthly_exempt_ils = rent_p_val * r_ils

# ברוטו חודשי כולל הכל
total_monthly_gross_ils = (work_gross_ils / 12) + monthly_exempt_ils

# הכנסה חייבת (רווח מעבודה)
taxable_ils = max(0, work_gross_ils - (rent_v * r_ils * 12) - (other * r_ils * 12))

# חישוב מיסים
it_ils, bl_ils, hb_ils, it_tab, bl_tab = calc_detailed_taxes_ils(taxable_ils, pts, is_res)
m_tax_ils = (it_ils + bl_ils + hb_ils) / 12
m_net_ils = (taxable_ils / 12) - m_tax_ils + monthly_exempt_ils

# אחוזי מס אפקטיביים
eff_taxable = (m_tax_ils / (taxable_ils/12) * 100) if taxable_ils > 0 else 0
eff_total = (m_tax_ils / total_monthly_gross_ils * 100) if total_monthly_gross_ils > 0 else 0

# --- תצוגה מרכזית ---
st.title("⚖️ מחשבון הכנסה ומיסוי לקליניקה (2026)")
st.divider()

# תיבת נטו מובלטת
net_rounded = int(round(m_net_ils, 0))
st.markdown(f"""
    <div style='border: 2px solid #4CAF50; border-radius: 10px; padding: 20px; background-color: #f1f8e9; text-align: center;'>
        <h1 style='color: #2e7d32; margin: 0;'>נטו חודשי ממוצע: ₪{net_rounded:,}</h1>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# שורה 1: הכנסות ורווח
st.subheader("📈 הכנסות ורווח (לפני מס)")
r1_cols = st.columns(3 if has_exempt else 2)
r1_cols[0].metric("ברוטו חודשי (סה\"כ)", f"₪{int(round(total_monthly_gross_ils, 0)):,}")
r1_cols[1].metric("רווח לפני מס (מעבודה)", f"₪{int(round(taxable_ils/12, 0)):,}")
if has_exempt:
    r1_cols[2].metric("שכירות פטורה", f"₪{int(round(monthly_exempt_ils, 0)):,}")

st.markdown("<br>", unsafe_allow_html=True)

# שורה 2: מיסים
st.subheader("📉 תשלומי חובה ומיסוי")
r2_cols = st.columns(4 if has_exempt else 3)
r2_cols[0].metric("מס הכנסה", f"₪{int(round(it_ils/12, 0)):,}")
r2_cols[1].metric("ב\"ל ומס בריאות", f"₪{int(round((bl_ils+hb_ils)/12, 0)):,}")
r2_cols[2].metric("מס אפקטיבי (מהרווח)", f"{eff_taxable:.1f}%")
if has_exempt:
    r2_cols[3].metric("מס אפקטיבי (מהכל)", f"{eff_total:.1f}%")

st.divider()

# פירוט מורחב
c1, c2 = st.columns(2)
with c1:
    with st.expander("📂 פירוט מדרגות מס הכנסה"):
        st.table(pd.DataFrame(it_tab))
with c2:
    if is_res:
        with st.expander("📂 פירוט ביטוח לאומי ומס בריאות"):
            st.table(pd.DataFrame(bl_tab))
    else:
        st.warning("⚠️ ניתוק תושבות פעיל: אין חבות לביטוח לאומי ומס בריאות.")

st.divider()
st.info(f"נטו במטבע {curr}: {int(round(m_net_ils * (1/r_ils), 0)):,} {curr}")

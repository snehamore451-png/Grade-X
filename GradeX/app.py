import streamlit as st
import pandas as pd
import plotly.express as px
import os
from sklearn.cluster import KMeans
import numpy as np
import re

# PDF EXPORT (using FPDF instead of ReportLab)
import plotly.io as pio
from io import BytesIO
from fpdf import FPDF  # ← safe library for Streamlit Cloud


# ----------------- PAGE CONFIG -----------------
st.set_page_config(page_title="GradeX - Automated Academic Insights Generation Platform", layout="wide")
st.title("📊 GradeX - Automated Academic Insights Generation Platform")


# ----------------- PAGE CONFIG -----------------
st.set_page_config(page_title="GradeX - Automated Academic Insights Generation Platform", layout="wide")
st.title("📊 GradeX - Automated Academic Insights Generation Platform")

# --- DEFINE FILE PATHS ---
SAMPLE_DATA_DIR = "Sample_Data"
ESE_TEMPLATE_PATH = os.path.join(SAMPLE_DATA_DIR, "ESE_Template.xlsx")
CT_TEMPLATE_PATH = os.path.join(SAMPLE_DATA_DIR, "CT_Template.xlsx")
ESE_SAMPLE_PATH = os.path.join(SAMPLE_DATA_DIR, "ESE Filled Reference.xlsx")
CT_SAMPLE_PATH = os.path.join(SAMPLE_DATA_DIR, "CT_Mid Filled Reference.xlsx")

# --- Ensure the Sample_Data directory exists ---
os.makedirs(SAMPLE_DATA_DIR, exist_ok=True)


# This function now only creates files if they are missing from your Sample_Data folder
def generate_missing_files():
    """
    Checks for templates/samples in the Sample_Data folder and creates them ONLY if missing.
    """
    if not os.path.exists(CT_TEMPLATE_PATH):
        print(f"'{CT_TEMPLATE_PATH}' not found. Creating blank template...")
        ct_headers = ["SR.No", "Roll No", "Full Name", "Subject1", "Subject2", "Total", "Percentage"]
        pd.DataFrame(columns=ct_headers).to_excel(CT_TEMPLATE_PATH, index=False, startrow=3)

    if not os.path.exists(ESE_TEMPLATE_PATH):
        print(f"'{ESE_TEMPLATE_PATH}' not found. Creating blank template...")
        ese_headers = pd.MultiIndex.from_tuples([("PRN", ""), ("Student Name", ""), ("Subject1", "ESE (60)"), ("SGPA", "")])
        pd.DataFrame(columns=ese_headers).to_excel(ESE_TEMPLATE_PATH, startrow=4)

# Call the function to ensure necessary files exist for the app to run
generate_missing_files()


# ----------------- DOWNLOADABLE TEMPLATES -----------------
st.sidebar.header("📥 Download Templates")
with open(CT_TEMPLATE_PATH, "rb") as f:
    st.sidebar.download_button("Blank CT/Mid Template", f, file_name=os.path.basename(CT_TEMPLATE_PATH))
with open(ESE_TEMPLATE_PATH, "rb") as f:
    st.sidebar.download_button("Blank End Sem Template", f, file_name=os.path.basename(ESE_TEMPLATE_PATH))

st.sidebar.markdown("---")
st.sidebar.header("📄 Reference Samples")

# Check if your specific sample files exist before creating the download button
if os.path.exists(CT_SAMPLE_PATH):
    with open(CT_SAMPLE_PATH, "rb") as f:
        st.sidebar.download_button("Filled CT/Mid Sample", f, file_name=os.path.basename(CT_SAMPLE_PATH))
else:
    st.sidebar.warning("CT_Mid Filled Reference.xlsx not found.")

if os.path.exists(ESE_SAMPLE_PATH):
    with open(ESE_SAMPLE_PATH, "rb") as f:
        st.sidebar.download_button("Filled End Sem Sample", f, file_name=os.path.basename(ESE_SAMPLE_PATH))
else:
    st.sidebar.warning("ESE Filled Reference.xlsx not found.")


# ----------------- FILE UPLOAD -----------------
exam_type = st.radio("Select Exam Type", ["CT/Mid", "End Sem"])
uploaded_files = st.file_uploader(
    "Upload Excel Files", type=["xlsx"], accept_multiple_files=True
)

# ----------------- LOADER FUNCTIONS -----------------
def clean_dataframe(df: pd.DataFrame):
    # remove Unnamed cols and empty rows
    df = df.loc[:, ~df.columns.str.contains("^Unnamed", na=False)]
    df = df.dropna(how="all")
    # strip column names
    df.columns = [str(c).strip() for c in df.columns]
    return df

def load_ct_mid(file):
    df = pd.read_excel(file, sheet_name="Sheet1", skiprows=3)
    df = clean_dataframe(df)
    df = df.rename(columns={
        "SR.No": "SrNo",
        "Roll No": "RollNo",
        "Full Name": "Name",
        "NLP": "NLP",
        "DE": "DE",
        "AIOPs": "AIOPs",
        "BC": "BC",
        "ACV": "ACV",
        "Total": "Total",
        "Percentage": "Percentage"
    })
    # Ensure all subject columns are numeric, coercing errors
    subject_cols = get_subject_columns(df)
    for col in subject_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def load_ese(file):
    file.seek(0)
    try:
        raw = pd.read_excel(file, sheet_name="Sheet1", header=[4, 5], dtype=str)
        
        # --- ROBUST HEADER PARSING LOGIC ---
        new_cols = []
        last_subject_name = ''
        
        for i, col in enumerate(raw.columns):
            top_header = str(col[0]).strip()
            bottom_header = str(col[1]).strip().replace('\n', ' ')
            
            base_columns = ['Branch Code', 'PRN', 'Student Name', 'Name', 'SGPA', 'LAB', 'MP/PW']
            
            if not top_header.startswith('Unnamed') and top_header not in base_columns:
                last_subject_name = top_header
            
            if top_header in ['LAB', 'MP/PW']:
                final_col_name = f"{top_header}_{bottom_header}"
            elif top_header in base_columns or bottom_header in base_columns:
                final_col_name = top_header if not top_header.startswith('Unnamed:') else bottom_header
            elif last_subject_name:
                final_col_name = f"{last_subject_name}_{bottom_header}"
            else:
                final_col_name = bottom_header
            
            new_cols.append(final_col_name)
        
        # --- START: CRITICAL FIX FOR DUPLICATE COLUMN ERROR ---
        def make_unique(column_names):
            seen = {}
            new_names = []
            for name in column_names:
                if name not in seen:
                    seen[name] = 1
                    new_names.append(name)
                else:
                    count = seen[name]
                    new_name = f"{name}_{count}"
                    while new_name in seen:
                        count += 1
                        new_name = f"{name}_{count}"
                    seen[name] = count + 1
                    seen[new_name] = 1
                    new_names.append(new_name)
            return new_names

        raw.columns = make_unique(new_cols)
        df = raw.copy()

    except Exception as e:
        st.error(f"Error reading ESE file with multi-level header. Ensure it matches the template. Details: {e}")
        return pd.DataFrame()

    df = df.loc[:, ~df.columns.str.contains("^Unnamed", na=False)]
    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    rename_map = {'Student Name': 'Name'}
    subj_codes = get_ese_subject_columns(df)
    
    for sub in subj_codes:
        for col in df.columns:
            if col.startswith(sub):
                if re.search(r'ESE\s?\(60\)', col, re.I):
                    rename_map[col] = f"{sub}_ESE(60)"
                elif re.search(r'CA\s?\(20\)', col, re.I):
                    rename_map[col] = f"{sub}_CA(20)"
                elif re.search(r'MSE\s?\(20\)', col, re.I):
                    rename_map[col] = f"{sub}_MSE(20)"
                elif re.search(r'Total\s?\(With Grace\)', col, re.I):
                    rename_map[col] = f"{sub}_Total_Marks"
                elif re.search(r'Grade', col, re.I) and not col.endswith(('(60)','(20)','_Marks')):
                    rename_map[col] = f"{sub}_Grade"

    df = df.rename(columns=rename_map)

    for col in df.columns:
        if any(x in col for x in ['_ESE(60)', '_CA(20)', '_MSE(20)', '_Total_Marks', 'SGPA']):
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    if "Name" in df.columns:
        df["Name"] = df["Name"].astype(str).str.strip()
        
    return df


# ----------------- HELPER TO GET SUBJECT COLS -----------------
def get_subject_columns(df):
    exclude_cols = ["SrNo", "RollNo", "Name", "Total", "Percentage", "Cluster"]
    return [c for c in df.columns if c not in exclude_cols and not c.endswith("_Grade") and not c.endswith("_ESE(60)") and not c.endswith("_CA(20)") and not c.endswith("_MSE(20)")]

def get_ese_subject_columns(df):
    subs = set()
    for c in df.columns:
        if c.endswith("_Grade") or c.endswith("_Total_Marks"):
            base_name_parts = c.rsplit('_', 1)
            base_name = base_name_parts[0]
            if base_name_parts[1].isdigit():
                base_name = base_name.rsplit('_',1)[0]
            subs.add(base_name)
    return sorted(list(subs))


# ---------------- PART 2 OF 3 ----------------
# ----------------- PDF EXPORT FUNCTIONS -----------------
def save_classwise_report_bytes(exam_name, df, figs_dict, top_students_df=None, low_students_df=None, class_avg=None, highest_score=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.5*inch, rightMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    # --- Title and Top/Bottom Performers ---
    elements.append(Paragraph(f"GradeX - Classwise Analysis Report: {exam_name}", styles['Title']))
    elements.append(Spacer(1, 12))
    if top_students_df is not None and not top_students_df.empty:
        elements.append(Paragraph("🏆 Top 3 Students", styles['Heading2']))
        top_data = [top_students_df.columns.tolist()] + top_students_df.values.tolist()
        top_table = Table(top_data)
        top_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366F1')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),('ALIGN', (0, 0), (-1, -1), 'CENTER'),('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),('BOTTOMPADDING', (0, 0), (-1, 0), 12),('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(top_table)
        elements.append(Spacer(1, 12))
    if low_students_df is not None and not low_students_df.empty:
        elements.append(Paragraph("📉 Lowest 3 Students", styles['Heading2']))
        low_data = [low_students_df.columns.tolist()] + low_students_df.values.tolist()
        low_table = Table(low_data)
        low_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366F1')),('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),('ALIGN', (0, 0), (-1, -1), 'CENTER'),('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),('BOTTOMPADDING', (0, 0), (-1, 0), 12),('BACKGROUND', (0, 1), (-1, -1), colors.lightcoral),('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(low_table)
        elements.append(Spacer(1, 12))

    # --- Main Analysis Charts ---
    verdict_map = {"Class Avg vs Highest Score": "Shows gap between average performance and the topper.", "Average Marks in Each Subject": "Highlights subjects where class performed better or worse.", "Subject-wise Averages of Top 3 Students": "Top students are consistent in strong subjects.", "Subject-wise Averages of Lowest 3 Students": "Bottom students struggle more in certain subjects.", "Subject-wise Lowest and Highest Marks": "Shows range of scores in each subject.", "Student Cluster Analysis": "Groups students into low, medium, and high performers.", "Marks Spread in the Class": "Displays how scores are distributed, including outliers."}
    
    charts_to_process = {k: v for k, v in figs_dict.items() if k != "Pass vs Fail Students"}

    for title, fig in charts_to_process.items():
        if fig is None: continue
        try:
            img_bytes = pio.to_image(fig, format='png', engine="kaleido", width=800, height=500)
            img_buf = BytesIO(img_bytes)
            
            elements_to_keep_together = [
                Paragraph(title, styles['Heading3'], bulletText="•"),
                RLImage(img_buf, width=6*inch, height=3.75*inch)
            ]
            if title in verdict_map:
                elements_to_keep_together.append(Paragraph(f"Verdict: {verdict_map[title]}", styles['Italic']))
            
            elements.append(KeepTogether(elements_to_keep_together))
            elements.append(Spacer(1, 12))
        except Exception as e:
            st.warning(f"Skipping chart '{title}' in PDF due to error: {e}")
            continue

    # --- Helper functions for chart generation in PDF ---
    def create_rl_image_from_fig(fig, width, height):
        try:
            img_bytes = pio.to_image(fig, format='png', engine="kaleido")
            img_buf = BytesIO(img_bytes)
            return RLImage(img_buf, width=width, height=height)
        except Exception:
            return None

    def build_chart_table(chart_list, elements_list):
        table_data = []
        for i in range(0, len(chart_list), 2):
            row = [chart_list[i], chart_list[i+1] if i + 1 < len(chart_list) else Paragraph("", styles['Normal'])]
            table_data.append(row)
        if table_data:
            table = Table(table_data, colWidths=[doc.width/2.0, doc.width/2.0])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12)
            ]))
            elements_list.append(table)

    # --- Generate and Add Pass/Fail Analysis Section for CT/Mid ---
    sub_cols = get_subject_columns(df)
    options_to_chart = ["Overall"] + sub_cols
    pass_fail_charts = []

    for option in options_to_chart:
        if option == "Overall":
            fail_mask = (df[sub_cols] < 8).any(axis=1)
            fail_count = fail_mask.sum()
            pass_count = len(df) - fail_count
            title = "Overall Pass vs. Fail"
        else:
            if option in df.columns:
                fail_count = (df[option] < 8).sum()
                pass_count = len(df) - fail_count
                title = f"Pass vs. Fail: {option}"
            else:
                continue
        
        if (pass_count + fail_count) == 0: continue
        pie_data = pd.DataFrame({'Status': ['Passed', 'Failed'], 'Count': [pass_count, fail_count]})
        fig_pie = px.pie(pie_data, names='Status', values='Count', title=title, color='Status', color_discrete_map={'Passed':'#00CC96', 'Failed':'#EF553B'})
        fig_pie.update_layout(showlegend=False, title_x=0.5, margin=dict(l=10, r=10, t=40, b=10), font=dict(size=10))
        # MODIFIED: Added border to pie chart slices
        fig_pie.update_traces(texttemplate="%{label}: %{value} (%{percent:.1%})", textposition="inside", marker=dict(line=dict(color='black', width=1.5)))
        rl_image = create_rl_image_from_fig(fig_pie, width=3.5*inch, height=2.8*inch)
        if rl_image:
            pass_fail_charts.append(rl_image)
    
    if pass_fail_charts:
        elements.append(PageBreak())
        elements.append(Paragraph("📊 Pass/Fail Analysis", styles['Heading2']))
        elements.append(Spacer(1, 12))
        build_chart_table(pass_fail_charts, elements)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def save_student_report_bytes(student_name, student_row, sub_cols, figs_dict, verdicts=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f"Individual Report: {student_name}", styles['Title']))
    elements.append(Spacer(1, 12))
    total_marks = student_row["Total"].values[0] if "Total" in student_row else (student_row[[c for c in student_row.columns if 'Total_Marks' in c]].sum(axis=1).values[0] if any('Total_Marks' in c for c in student_row.columns) else None)
    percentage = student_row["Percentage"].values[0] if "Percentage" in student_row else None
    student_marks_cols = [c for c in sub_cols if c in student_row.columns]
    student_marks = student_row[student_marks_cols].T.reset_index()
    student_marks.columns = ["Subject", "Marks"]
    if not student_marks.empty:
        try:
            max_sub = student_marks.loc[student_marks["Marks"].idxmax()]
            min_sub = student_marks.loc[student_marks["Marks"].idxmin()]
        except Exception:
            max_sub = {"Subject": "", "Marks": 0}
            min_sub = {"Subject": "", "Marks": 0}
    else:
        max_sub = {"Subject": "", "Marks": 0}
        min_sub = {"Subject": "", "Marks": 0}
    failed_subjects = student_marks[student_marks["Marks"] < 8]["Subject"].tolist() if not student_marks.empty else []
    failed_subjects_text = ", ".join(failed_subjects) if failed_subjects else "Not failed"
    if total_marks is not None:
        elements.append(Paragraph(f"<b>📘 Total Marks:</b> {total_marks}", styles['Normal']))
    if percentage is not None:
        elements.append(Paragraph(f"<b>📊 Percentage:</b> {percentage}%", styles['Normal']))
    elements.append(Paragraph(f"<b>🏆 Highest:</b> {max_sub['Subject']} ({max_sub['Marks']})", styles['Normal']))
    elements.append(Paragraph(f"<b>📉 Lowest:</b> {min_sub['Subject']} ({min_sub['Marks']})", styles['Normal']))
    elements.append(Paragraph(f"<b>❌ Failed Subjects:</b> {failed_subjects_text}", styles['Normal']))
    elements.append(Spacer(1, 12))
    for title, fig in figs_dict.items():
        try:
            img_bytes = pio.to_image(fig, format='png', engine="kaleido")
            img_buf = BytesIO(img_bytes)
            elements.append(Paragraph(title, styles['Heading3']))
            elements.append(RLImage(img_buf, width=450, height=300))
            elements.append(Spacer(1, 12))
        except Exception: continue
    if verdicts:
        elements.append(Paragraph("<b>Verdict / Remarks:</b>", styles['Heading3']))
        for v in verdicts:
            elements.append(Paragraph(v, styles['Normal']))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def save_ese_classwise_report_bytes(exam_name, df, figs_dict, top_students_df=None, low_students_df=None, class_avg=None, highest_sgpa=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.5*inch, rightMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    # --- Title and Top/Bottom Performers ---
    elements.append(Paragraph(f"GradeX - Classwise Analysis Report: {exam_name}", styles['Title']))
    elements.append(Spacer(1, 12))
    if top_students_df is not None and not top_students_df.empty:
        elements.append(Paragraph("🏆 Top 3 Students", styles['Heading2']))
        top_data = [top_students_df.columns.tolist()] + top_students_df.values.tolist()
        top_table = Table(top_data)
        top_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366F1')),('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),('ALIGN', (0, 0), (-1, -1), 'CENTER'),('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),('BOTTOMPADDING', (0, 0), (-1, 0), 12),('BACKGROUND', (0, 1), (-1, -1), colors.lightgreen),('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(top_table)
        elements.append(Spacer(1, 12))
    if low_students_df is not None and not low_students_df.empty:
        elements.append(Paragraph("📉 Lowest 3 Students", styles['Heading2']))
        low_data = [low_students_df.columns.tolist()] + low_students_df.values.tolist()
        low_table = Table(low_data)
        low_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366F1')),('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),('ALIGN', (0, 0), (-1, -1), 'CENTER'),('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),('BOTTOMPADDING', (0, 0), (-1, 0), 12),('BACKGROUND', (0, 1), (-1, -1), colors.lightcoral),('GRID', (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(low_table)
        elements.append(Spacer(1, 12))

    # --- Main Analysis Charts (with KeepTogether) ---
    verdict_map = {
        "Class Performance Snapshot (SGPA)": "Compares the average student SGPA with the top performer's SGPA.",
        "Subject Difficulty Ranking by Failure Rate": "Highlights which subjects are most challenging for students.",
        "Average Mark Composition by Subject": "Breaks down performance to identify weaknesses in CA, MSE, or ESE components."
    }
    for title, fig in figs_dict.items():
        if fig is None: continue
        try:
            img_bytes = pio.to_image(fig, format='png', engine="kaleido", width=800, height=500)
            img_buf = BytesIO(img_bytes)
            
            elements_to_keep_together = [
                Paragraph(title, styles['Heading3'], bulletText="•"),
                RLImage(img_buf, width=6*inch, height=3.75*inch)
            ]
            if title in verdict_map:
                elements_to_keep_together.append(Paragraph(f"Verdict: {verdict_map[title]}", styles['Italic']))
            
            elements.append(KeepTogether(elements_to_keep_together))
            elements.append(Spacer(1, 12))
        except Exception as e:
            st.warning(f"Skipping chart '{title}' in PDF due to error: {e}")
            continue

    # --- Helper to create and add charts to a list ---
    def create_rl_image_from_fig(fig, width, height):
        try:
            img_bytes = pio.to_image(fig, format='png', engine="kaleido")
            img_buf = BytesIO(img_bytes)
            return RLImage(img_buf, width=width, height=height)
        except Exception:
            return None

    sub_cols_ese = get_ese_subject_columns(df)
    pie_chart_subjects = [sub for sub in sub_cols_ese if "total" not in sub.lower()]
    options_to_chart = ["Overall"] + pie_chart_subjects

    # --- Generate Grade Distribution Charts ---
    grade_dist_charts = []
    for option in options_to_chart:
        if option == "Overall":
            all_grades = []
            for sub in pie_chart_subjects:
                grade_col = f"{sub}_Grade"
                if grade_col in df.columns: all_grades.extend(df[grade_col].dropna().str.strip().str.upper())
            title = "Overall Grade Distribution"
        else:
            grade_col = f"{option}_Grade"
            if grade_col in df.columns: all_grades = df[grade_col].dropna().str.strip().str.upper().tolist()
            else: all_grades = []
            title = f"Grade Distribution: {option}"
        if not all_grades: continue
        grade_counts = pd.Series(all_grades).value_counts().reset_index()
        grade_counts.columns = ['Grade', 'Count']
        fig_donut = px.pie(grade_counts, names='Grade', values='Count', title=title, hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
        fig_donut.update_layout(showlegend=False, title_x=0.5, margin=dict(l=10, r=10, t=40, b=10), font=dict(size=10))
        # MODIFIED: Added border to donut chart slices
        fig_donut.update_traces(texttemplate="%{label}: %{value} (%{percent:.1%})", textposition="inside", marker=dict(line=dict(color='black', width=1.5)))
        rl_image = create_rl_image_from_fig(fig_donut, width=3.5*inch, height=2.8*inch)
        if rl_image:
            grade_dist_charts.append(rl_image)

    # --- Generate Pass/Fail Charts ---
    pass_fail_charts = []
    for option in options_to_chart:
        if option == "Overall":
            if 'has_failed' not in df.columns: continue
            fail_count = df['has_failed'].sum()
            pass_count = len(df) - fail_count
            title = "Overall Pass vs. Fail"
        else:
            grade_col = f"{option}_Grade"
            if grade_col not in df.columns: continue
            fail_count = (df[grade_col].str.strip().str.upper() == 'FF').sum()
            pass_count = len(df) - fail_count
            title = f"Pass vs. Fail: {option}"
        if (pass_count + fail_count) == 0: continue
        pie_data = pd.DataFrame({'Status': ['Passed', 'Failed'], 'Count': [pass_count, fail_count]})
        fig_pie = px.pie(pie_data, names='Status', values='Count', title=title, color='Status', color_discrete_map={'Passed':'#00CC96', 'Failed':'#EF553B'})
        fig_pie.update_layout(showlegend=False, title_x=0.5, margin=dict(l=10, r=10, t=40, b=10), font=dict(size=10))
        # MODIFIED: Added border to pie chart slices
        fig_pie.update_traces(texttemplate="%{label}: %{value} (%{percent:.1%})", textposition="inside", marker=dict(line=dict(color='black', width=1.5)))
        rl_image = create_rl_image_from_fig(fig_pie, width=3.5*inch, height=2.8*inch)
        if rl_image:
            pass_fail_charts.append(rl_image)

    # --- Function to build tables with spacing ---
    def build_chart_table(chart_list, elements_list):
        table_data = []
        for i in range(0, len(chart_list), 2):
            row = [chart_list[i], chart_list[i+1] if i + 1 < len(chart_list) else Paragraph("", styles['Normal'])]
            table_data.append(row)
        if table_data:
            table = Table(table_data, colWidths=[doc.width/2.0, doc.width/2.0])
            table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12) # Added spacing between rows
            ]))
            elements_list.append(table)

    # --- Build and add sections to PDF ---
    elements.append(PageBreak())
    elements.append(Paragraph("📜 Grade Distribution Analysis", styles['Heading2']))
    build_chart_table(grade_dist_charts, elements)
    
    elements.append(PageBreak())
    elements.append(Paragraph("📊 Pass/Fail Analysis", styles['Heading2']))
    build_chart_table(pass_fail_charts, elements)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def save_ese_student_report_bytes(student_name, student_row, sub_cols, figs_dict, verdicts=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=0.5*inch, rightMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f"Individual Report: {student_name}", styles['Title']))
    elements.append(Spacer(1, 12))
    
    grade_cols = [f"{sub}_Grade" for sub in sub_cols if f"{sub}_Grade" in student_row.columns]
    has_failed = any(str(student_row[col].iloc[0]).strip().upper() == 'FF' for col in grade_cols)
    
    sgpa_val = student_row['SGPA'].values[0] if 'SGPA' in student_row else None
    sgpa_display = "FAILED" if has_failed else (f"{sgpa_val:.2f}" if pd.notna(sgpa_val) else "N/A")

    failed_subjects_list = [sub for sub in sub_cols if f"{sub}_Grade" in student_row.columns and str(student_row[f"{sub}_Grade"].iloc[0]).strip().upper() == 'FF']
    failed_subjects_text = ", ".join(failed_subjects_list) if failed_subjects_list else "None"
    
    marks_data_list = []
    for sub in sub_cols:
        marks_col = f"{sub}_Total_Marks"
        if marks_col in student_row.columns:
            marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
            if pd.notna(marks): marks_data_list.append({'Subject': sub, 'Marks': marks})
    
    student_marks = pd.DataFrame(marks_data_list)
    max_sub = student_marks.loc[student_marks["Marks"].idxmax()] if not student_marks.empty else {"Subject": "N/A", "Marks": 0}
    min_sub = student_marks.loc[student_marks["Marks"].idxmin()] if not student_marks.empty else {"Subject": "N/A", "Marks": 0}

    elements.append(Paragraph(f"<b>📊 SGPA:</b> {sgpa_display}", styles['Normal']))
    elements.append(Paragraph(f"<b>🏆 Highest:</b> {max_sub['Subject']} ({max_sub['Marks']})", styles['Normal']))
    elements.append(Paragraph(f"<b>📉 Lowest:</b> {min_sub['Subject']} ({min_sub['Marks']})", styles['Normal']))
    elements.append(Paragraph(f"<b>❌ Failed Subjects:</b> {failed_subjects_text}", styles['Normal']))
    elements.append(Spacer(1, 24))
    
    # --- Logic to create a 2-column table for charts ---
    chart_blocks = []
    for title, fig in figs_dict.items():
        try:
            # Adjust image size for a two-column layout
            img_bytes = pio.to_image(fig, format='png', engine="kaleido", width=600, height=375)
            img_buf = BytesIO(img_bytes)
            img = RLImage(img_buf, width=3*inch, height=1.875*inch)
            
            title_para = Paragraph(title, styles['Heading4'])
            chart_blocks.append([title_para, img]) # Create a block of [title, image]
        except Exception:
            continue

    table_data = []
    for i in range(0, len(chart_blocks), 2):
        row = [chart_blocks[i]]
        if (i + 1) < len(chart_blocks):
            row.append(chart_blocks[i+1])
        else:
            row.append(Paragraph("", styles['Normal'])) # Add empty cell if odd number of charts
        table_data.append(row)

    if table_data:
        chart_table = Table(table_data, colWidths=[doc.width/2.0, doc.width/2.0])
        chart_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ]))
        elements.append(chart_table)

    if verdicts:
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("<b>Verdict / Remarks:</b>", styles['Heading3']))
        for v in verdicts:
            elements.append(Paragraph(v, styles['Normal']))
            
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# START: MODIFIED FUNCTION FOR DETAILED BATCH PDF EXPORT
def save_all_student_reports_bytes(exam_type, df, uploaded_files_list=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36)
    styles = getSampleStyleSheet()
    elements = []
    
    is_ese = exam_type == "End Sem"
    sub_cols = get_ese_subject_columns(df) if is_ese else get_subject_columns(df)

    # Helper function to create ESE charts (to avoid repetition)
    def create_ese_bar_chart(student_row, sub_cols, marks_type, title, y_range):
        marks_list = []
        if marks_type == "Overall Internals (CA+MSE)":
            for s in sub_cols:
                ca_col, mse_col = f"{s}_CA(20)", f"{s}_MSE(20)"
                if ca_col in student_row.columns and mse_col in student_row.columns:
                    ca_marks = pd.to_numeric(student_row[ca_col].iloc[0], errors='coerce')
                    mse_marks = pd.to_numeric(student_row[mse_col].iloc[0], errors='coerce')
                    marks_list.append({'Subject': s, 'Marks': (ca_marks if pd.notna(ca_marks) else 0) + (mse_marks if pd.notna(mse_marks) else 0)})
        else:
            for s in sub_cols:
                marks_col = f"{s}_{marks_type}"
                if marks_col in student_row.columns:
                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                    marks_list.append({'Subject': s, 'Marks': marks})
        
        df_marks = pd.DataFrame(marks_list).dropna(subset=['Marks'])
        fig = px.bar(df_marks, x="Subject", y="Marks", text_auto=True, color="Subject", 
                     title=title, color_discrete_sequence=px.colors.qualitative.Bold, 
                     range_y=y_range)
        fig.update_layout(title_font_size=14, title_x=0.5)
        # MODIFIED: Added border to bar charts
        fig.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
        return fig
    
    for index, student_row_series in df.iterrows():
        student_name = student_row_series["Name"]
        student_row = student_row_series.to_frame().T
        
        elements.append(Paragraph(f"<b>Individual Report: {student_name}</b>", styles['Title']))
        elements.append(Spacer(1, 12))
        
        if is_ese:
            # ESE Student Stats
            grade_cols = [f"{sub}_Grade" for sub in sub_cols if f"{sub}_Grade" in student_row.columns]
            has_failed = any(str(student_row_series.get(col)).strip().upper() == 'FF' for col in grade_cols)
            sgpa = student_row_series.get('SGPA')
            sgpa_display = "FAILED" if has_failed else (f"{sgpa:.2f}" if pd.notna(sgpa) else 'N/A')
            failed_subjects_list = [sub for sub in sub_cols if f"{sub}_Grade" in student_row.columns and str(student_row_series.get(f"{sub}_Grade")).strip().upper() == 'FF']
            failed_subjects_text = ", ".join(failed_subjects_list) if failed_subjects_list else "None"
            
            overall_marks_list = []
            for s in sub_cols:
                marks_col = f"{s}_Total_Marks"
                if marks_col in student_row.columns:
                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                    overall_marks_list.append({'Subject': s, 'Marks': marks})
            overall_marks_df = pd.DataFrame(overall_marks_list).dropna(subset=['Marks'])

            max_sub_ese = overall_marks_df.loc[overall_marks_df["Marks"].idxmax()] if not overall_marks_df.empty else {"Subject": "N/A", "Marks": 0}
            min_sub_ese = overall_marks_df.loc[overall_marks_df["Marks"].idxmin()] if not overall_marks_df.empty else {"Subject": "N/A", "Marks": 0}
            
            elements.append(Paragraph(f"<b>📊 SGPA:</b> {sgpa_display}", styles['Normal']))
            elements.append(Paragraph(f"<b>🏆 Highest (Overall):</b> {max_sub_ese['Subject']} ({max_sub_ese['Marks']})", styles['Normal']))
            elements.append(Paragraph(f"<b>📉 Lowest (Overall):</b> {min_sub_ese['Subject']} ({min_sub_ese['Marks']})", styles['Normal']))
            elements.append(Paragraph(f"<b>❌ Failed Subjects:</b> {failed_subjects_text}", styles['Normal']))
            elements.append(Spacer(1, 24))

            # Generate and arrange all 5 charts for the PDF
            figs_dict = {}
            figs_dict[f"Overall Marks (out of 100)"] = create_ese_bar_chart(student_row, sub_cols, "Total_Marks", "", [0, 100])
            figs_dict[f"Overall Internal Marks (out of 40)"] = create_ese_bar_chart(student_row, sub_cols, "Overall Internals (CA+MSE)", "", [0, 40])
            figs_dict[f"CA Marks (out of 20)"] = create_ese_bar_chart(student_row, sub_cols, "CA(20)", "", [0, 20])
            figs_dict[f"MSE Marks (out of 20)"] = create_ese_bar_chart(student_row, sub_cols, "MSE(20)", "", [0, 20])
            figs_dict[f"ESE Marks (out of 60)"] = create_ese_bar_chart(student_row, sub_cols, "ESE(60)", "", [0, 60])

            chart_blocks = []
            for title, fig in figs_dict.items():
                try:
                    img_bytes = pio.to_image(fig, format='png', engine="kaleido", width=600, height=375)
                    img_buf = BytesIO(img_bytes)
                    img = RLImage(img_buf, width=3*inch, height=1.875*inch)
                    title_para = Paragraph(title, styles['Heading4'])
                    chart_blocks.append([title_para, img])
                except Exception:
                    continue

            table_data = []
            for i_chart in range(0, len(chart_blocks), 2):
                row = [chart_blocks[i_chart]]
                if (i_chart + 1) < len(chart_blocks):
                    row.append(chart_blocks[i_chart+1])
                else:
                    row.append(Paragraph("", styles['Normal']))
                table_data.append(row)

            if table_data:
                chart_table = Table(table_data, colWidths=[doc.width/2.0, doc.width/2.0])
                chart_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 5)]))
                elements.append(chart_table)

        else: # CT/Mid
            # CT/Mid Student Stats
            total_marks = student_row_series.get("Total")
            percentage = student_row_series.get("Percentage")
            
            sub_marks_list = []
            for s in sub_cols:
                marks = pd.to_numeric(student_row[s].iloc[0], errors='coerce')
                sub_marks_list.append({'Subject': s, 'Marks': marks})
            sub_marks_df = pd.DataFrame(sub_marks_list).dropna(subset=['Marks'])

            max_sub = sub_marks_df.loc[sub_marks_df["Marks"].idxmax()] if not sub_marks_df.empty else {"Subject": "N/A", "Marks": 0}
            min_sub = sub_marks_df.loc[sub_marks_df["Marks"].idxmin()] if not sub_marks_df.empty else {"Subject": "N/A", "Marks": 0}
            failed_subjects = sub_marks_df[sub_marks_df["Marks"] < 8]["Subject"].tolist()
            failed_subjects_text = ", ".join(failed_subjects) if failed_subjects else "Not failed"
            elements.append(Paragraph(f"<b>📘 Total Marks:</b> {total_marks}", styles['Normal']))
            elements.append(Paragraph(f"<b>📊 Percentage:</b> {percentage}%", styles['Normal']))
            elements.append(Paragraph(f"<b>🏆 Highest:</b> {max_sub['Subject']} ({max_sub['Marks']})", styles['Normal']))
            elements.append(Paragraph(f"<b>📉 Lowest:</b> {min_sub['Subject']} ({min_sub['Marks']})", styles['Normal']))
            elements.append(Paragraph(f"<b>❌ Failed Subjects:</b> {failed_subjects_text}", styles['Normal']))
            elements.append(Spacer(1, 12))
            
            # Generate and add the single chart for CT/Mid
            if not sub_marks_df.empty:
                fig_student = px.bar(sub_marks_df, x="Subject", y="Marks", text_auto=True, color="Subject",
                                     title=f"Individual Subject Marks",
                                     color_discrete_sequence=px.colors.qualitative.Bold,
                                     range_y=[0, 20])
                fig_student.update_layout(title_font_size=14, title_x=0.5, height=400, margin=dict(l=20, r=20, t=50, b=20), showlegend=False, yaxis_title="", xaxis_title="")
                # MODIFIED: Added border to bar chart
                fig_student.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
                try:
                    img_bytes = pio.to_image(fig_student, format='png', engine="kaleido")
                    img_buf = BytesIO(img_bytes)
                    elements.append(RLImage(img_buf, width=450, height=300))
                except Exception:
                    pass
        
        if index < len(df) - 1:
            elements.append(PageBreak())
            
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
# END: MODIFIED FUNCTION

# ----------------- PROCESS UPLOADED FILES -----------------
if uploaded_files:
    exam_data = {}
    for file in uploaded_files:
        file.seek(0)
        exam_name = file.name.split(".")[0]
        try:
            if exam_type == "CT/Mid":
                df = load_ct_mid(file)
            else:
                df = load_ese(file)
            exam_data[exam_name] = df
        except Exception as e:
            st.error(f"Failed to load and process {file.name}: {e}")

    if exam_data:
        tabs = st.tabs(list(exam_data.keys()))

# ---------------- PART 3 OF 3 ----------------

        for i, (exam, df) in enumerate(exam_data.items()):
            with tabs[i]:
                st.subheader(f"📘 {exam} Analysis")
                
                if df.empty:
                    st.warning("Could not process this file. Please check the format.")
                    continue
                
                if exam_type == "CT/Mid":
                    st.write("### Student Data Preview")
                    st.dataframe(df.head())
                    sub_cols = get_subject_columns(df)
                    class_avg = df["Total"].mean()
                    highest_score = df["Total"].max()
                    top_students = df.sort_values(by="Total", ascending=False)[["Name", "Total", "Percentage"]].drop_duplicates(subset="Name").head(3)
                    low_students = df.sort_values(by="Total", ascending=True)[["Name", "Total", "Percentage"]].drop_duplicates(subset="Name").head(3)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("### 🏆 Top 3 Students")
                        st.dataframe(top_students.reset_index(drop=True))
                    with col2:
                        st.markdown("### 📉 Lowest 3 Students")
                        st.dataframe(low_students.reset_index(drop=True))
                    with col3:
                        st.metric("📊 Class Avg", round(class_avg, 2))
                        fig_vs = px.bar(x=["Class Avg", "Highest Score"],y=[class_avg, highest_score],text=[round(class_avg, 2), highest_score],color=["Class Avg", "Highest Score"],color_discrete_sequence=px.colors.qualitative.Vivid,title="Class Avg vs Highest Score",height=180)
                        # MODIFIED: Added border to bar chart
                        fig_vs.update_traces(width=0.4, marker_line_width=1.5, marker_line_color="black")
                        fig_vs.update_layout(yaxis_title="Marks", xaxis_title="", showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
                        st.plotly_chart(fig_vs, use_container_width=True)
                        st.caption("Verdict: Shows the difference between average performance and the topper.")
                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.subheader("📘 Overall Class Analysis")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        avg_scores = df[sub_cols].mean().reset_index()
                        avg_scores.columns = ["Subject", "Average Marks"]
                        fig_avg = px.bar(avg_scores, x="Subject", y="Average Marks",title="Average Marks in Each Subject",text_auto=True, color="Subject",color_discrete_sequence=px.colors.qualitative.Vivid,range_y=[0, 30])
                        # MODIFIED: Added border to bar chart
                        fig_avg.update_traces(width=0.4, marker_line_width=1.5, marker_line_color="black")
                        st.plotly_chart(fig_avg, use_container_width=True)
                        st.caption("Verdict: Highlights subjects where class performed better or worse.")
                    with col_b:
                        fig_top = None
                        if not top_students.empty:
                            top_avg = df[df["Name"].isin(top_students["Name"])][sub_cols].mean().reset_index()
                            top_avg.columns = ["Subject", "Average Marks"]
                            fig_top = px.bar(top_avg, x="Subject", y="Average Marks",title="Subject-wise Averages of Top 3 Students",text_auto=True, color="Subject",color_discrete_sequence=px.colors.qualitative.Bold,range_y=[0, 30])
                            # MODIFIED: Added border to bar chart
                            fig_top.update_traces(width=0.4, marker_line_width=1.5, marker_line_color="black")
                            st.plotly_chart(fig_top, use_container_width=True)
                            st.caption("Verdict: Top students show consistent performance across subjects.")
                    col_c, col_d = st.columns(2)
                    with col_c:
                        fig_low = None
                        if not low_students.empty:
                            low_avg = df[df["Name"].isin(low_students["Name"])][sub_cols].mean().reset_index()
                            low_avg.columns = ["Subject", "Average Marks"]
                            fig_low = px.bar(low_avg, x="Subject", y="Average Marks",title="Subject-wise Averages of Lowest 3 Students",text_auto=True, color="Subject",color_discrete_sequence=px.colors.qualitative.Safe,range_y=[0, 30])
                            # MODIFIED: Added border to bar chart
                            fig_low.update_traces(width=0.4, marker_line_width=1.5, marker_line_color="black")
                            st.plotly_chart(fig_low, use_container_width=True)
                            st.caption("Verdict: Bottom students struggled more in certain subjects.")
                    with col_d:
                        data = []
                        for sub in sub_cols:
                            min_mark = df[sub].min()
                            max_mark = df[sub].max()
                            min_students = ", ".join(df[df[sub] == min_mark]["Name"].tolist())
                            max_students = ", ".join(df[df[sub] == max_mark]["Name"].tolist())
                            data.append({"Subject": sub, "Type": "Lowest", "Marks": min_mark, "Students": min_students})
                            data.append({"Subject": sub, "Type": "Highest", "Marks": max_mark, "Students": max_students})
                        perf_df = pd.DataFrame(data)
                        fig_perf = px.bar(perf_df, x="Subject", y="Marks", color="Type", barmode="group",hover_data=["Students"], title="Subject-wise Lowest and Highest Marks",color_discrete_map={"Lowest": "#EF553B", "Highest": "#00CC96"})
                        # MODIFIED: Added border to bar chart
                        fig_perf.update_traces(marker_line_width=1.5, marker_line_color="black")
                        st.plotly_chart(fig_perf, use_container_width=True)
                        st.caption("Verdict: Shows the range of scores and which students are at the extremes.")
                    st.markdown("#### 📌 Student Cluster Analysis")
                    cluster_data = df[sub_cols].copy()
                    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
                    clusters = kmeans.fit_predict(cluster_data)
                    df["Cluster"] = clusters.astype(str)
                    fig_cluster = px.scatter(df, x="Total", y="Percentage", color="Cluster",hover_data=["Name"], size="Total",title="Student Cluster Analysis based on Total Marks & Percentage",color_discrete_sequence=px.colors.qualitative.Set1)
                    # MODIFIED: Ensured border is on scatter points
                    fig_cluster.update_traces(marker=dict(line=dict(width=1.2, color='DarkSlateGrey')))
                    st.plotly_chart(fig_cluster, use_container_width=True)
                    st.caption("Verdict: Groups students into low, medium, and high performers.")
                    col_e, col_f = st.columns(2)
                    with col_e:
                        fig_box = px.box(df, y="Total", points="all",title="Marks Spread in the Class",color_discrete_sequence=["#EF553B"])
                        # MODIFIED: Added border to box plot
                        fig_box.update_traces(marker=dict(line=dict(color='black', width=1.2)))
                        st.plotly_chart(fig_box, use_container_width=True)
                        st.caption("Verdict: Shows how marks are spread across class including outliers.")
                    with col_f:
                        st.markdown("##### 📊 Pass/Fail Analysis")
                        pf_options = ["Overall"] + sub_cols
                        selected_pf_option = st.selectbox("Select for Pass/Fail details:", options=pf_options, key=f"ct_pf_select_{i}")

                        pass_count, fail_count = 0, 0
                        chart_title = ""

                        if selected_pf_option == "Overall":
                            fail_mask = (df[sub_cols] < 8).any(axis=1)
                            fail_count = fail_mask.sum()
                            pass_count = len(df) - fail_count
                            chart_title = "Overall Pass vs. Fail"
                        else:
                            fail_count = (df[selected_pf_option] < 8).sum()
                            pass_count = len(df) - fail_count
                            chart_title = f"Pass vs. Fail for {selected_pf_option}"
                        
                        pie_data = pd.DataFrame({'Status': ['Passed', 'Failed'], 'Count': [pass_count, fail_count]})
                        fig_pie_ct = px.pie(pie_data, names='Status', values='Count', title=chart_title, color='Status', color_discrete_map={'Passed':'#00CC96', 'Failed':'#EF553B'})
                        # MODIFIED: Ensured border on pie chart
                        fig_pie_ct.update_traces(textposition="outside", textinfo="percent+label", marker=dict(line=dict(color='black', width=1.5)), texttemplate="%{label}: <br>%{value} students (%{percent:.1f}%)")
                        fig_pie_ct.update_layout(showlegend=False, title_x=0.5)
                        st.plotly_chart(fig_pie_ct, use_container_width=True)
                        st.caption("Verdict: Compares students who passed vs failed (pass mark > 7).")

                    st.subheader("📄 Export Classwise Report")
                    if st.button(f"📘 Download Classwise Report ({exam})", key=f"class_pdf_{i}"):
                        class_figs = {"Class Avg vs Highest Score": fig_vs if 'fig_vs' in locals() else None,"Average Marks in Each Subject": fig_avg if 'fig_avg' in locals() else None,"Subject-wise Averages of Top 3 Students": fig_top if 'fig_top' in locals() else None,"Subject-wise Averages of Lowest 3 Students": fig_low if 'fig_low' in locals() else None,"Subject-wise Lowest and Highest Marks": fig_perf if 'fig_perf' in locals() else None,"Student Cluster Analysis": fig_cluster if 'fig_cluster' in locals() else None,"Marks Spread in the Class": fig_box if 'fig_box' in locals() else None,}
                        pdf_bytes = save_classwise_report_bytes(exam, df, class_figs, top_students, low_students, class_avg, highest_score)
                        st.download_button("⬇️ Download Classwise PDF",data=pdf_bytes,file_name=f"{exam}_Classwise_Analysis.pdf",mime="application/pdf",key=f"download_class_pdf_{i}")
                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.subheader("🎯 Download Individual Student Analysis")
                    student_names = df["Name"].dropna().unique()
                    selected_student = st.selectbox("Select a student:", student_names, key=f"student_select_{i}_{exam}")
                    student_row = df[df["Name"] == selected_student]
                    if not student_row.empty:
                        sub_cols_dynamic = get_subject_columns(df)
                        student_marks = student_row[sub_cols_dynamic].T.reset_index()
                        student_marks.columns = ["Subject", "Marks"]
                        total_marks = student_row["Total"].values[0]
                        percentage = student_row["Percentage"].values[0]
                        max_sub = student_marks.loc[student_marks["Marks"].idxmax()]
                        min_sub = student_marks.loc[student_marks["Marks"].idxmin()]
                        failed_subjects = student_marks[student_marks["Marks"] < 8]["Subject"].tolist()
                        failed_subjects_text = ", ".join(failed_subjects) if failed_subjects else "Not failed"
                        fig_student = px.bar(student_marks, x="Subject", y="Marks", text_auto=True, color="Subject",color_discrete_sequence=px.colors.qualitative.Bold, range_y=[0, 20])
                        # MODIFIED: Added border to bar chart
                        fig_student.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
                        st.plotly_chart(fig_student, use_container_width=True)
                        st.caption(f"Shows {selected_student}'s marks across all subjects.")
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1: st.metric("📘 Total Marks", total_marks)
                        with col2: st.metric("📊 Percentage", f"{percentage}%")
                        with col3: st.metric("🏆 Highest", f"{max_sub['Subject']} ({max_sub['Marks']})")
                        with col4: st.metric("📉 Lowest", f"{min_sub['Subject']} ({min_sub['Marks']})")
                        with col5: st.metric("❌ Failed", failed_subjects_text)
                        if st.button("📑 Download Individual Student PDF", key=f"student_pdf_{i}_{selected_student}"):
                            student_figs = {"Individual Student Performance": fig_student}
                            pdf_bytes = save_student_report_bytes(selected_student, student_row, sub_cols_dynamic, student_figs)
                            st.download_button(f"⬇️ Download {selected_student}'s PDF",data=pdf_bytes,file_name=f"{selected_student}_Analysis.pdf",mime="application/pdf",key=f"download_student_pdf_{i}_{selected_student}")
                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.markdown("#### 📥 Export All Individual Reports")
                    if st.button(f"⬇️ Download All Student Reports ({exam})", key=f"all_student_pdf_{i}_moved"):
                        pdf_bytes = save_all_student_reports_bytes(exam_type, df)
                        st.download_button(f"⬇️ Download All Student PDF",data=pdf_bytes,file_name=f"{exam}_All_Individual_Reports.pdf",mime="application/pdf",key=f"download_all_student_pdf_{i}_moved")
                
                # ---------------- START: RESTRUCTURED ESE BLOCK ----------------
                elif exam_type == "End Sem":
                    st.write("### Student Data Preview")
                    st.dataframe(df.head())
                    
                    if 'Name' not in df.columns or 'SGPA' not in df.columns:
                        st.error("Critical columns 'Name' or 'SGPA' not found. Please check the uploaded file format.")
                        continue
                        
                    sub_cols_ese = get_ese_subject_columns(df)
                    
                    grade_cols = [f"{sub}_Grade" for sub in sub_cols_ese if f"{sub}_Grade" in df.columns]
                    if grade_cols:
                        df['has_failed'] = df[grade_cols].apply(lambda row: any(str(grade).strip().upper() == 'FF' for grade in row), axis=1)
                    else:
                        df['has_failed'] = False

                    df_passed = df[~df['has_failed']].copy()
                    
                    top_students_ese = df_passed.sort_values(by="SGPA", ascending=False)[["Name", "SGPA"]].head(3)
                    low_students_ese = df_passed.sort_values(by="SGPA", ascending=True)[["Name", "SGPA"]].head(3)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown("### 🏆 Top 3 Performers (Passed)")
                        st.dataframe(top_students_ese.reset_index(drop=True))
                    with col2:
                        st.markdown("### 📉 Bottom 3 Performers (Passed)")
                        st.dataframe(low_students_ese.reset_index(drop=True))
                    with col3:
                        class_avg_sgpa = df_passed['SGPA'].mean()
                        st.metric("📊 Class Avg SGPA (Passed)", f"{class_avg_sgpa:.2f}" if pd.notna(class_avg_sgpa) else "N/A")
                        highest_sgpa = df_passed['SGPA'].max()
                        st.metric("🚀 Highest SGPA (Passed)", f"{highest_sgpa:.2f}" if pd.notna(highest_sgpa) else "N/A")
                    
                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.subheader("📘 Overall Class Analysis")
                    
                    figs_for_pdf = {}

                    # --- ROW 1: SGPA Comparison & Mark Composition ---
                    r1_col1, r1_col2 = st.columns(2)
                    with r1_col1:
                        sgpa_data = pd.DataFrame({'Category': ['Class Average SGPA', 'Highest SGPA'],'SGPA': [class_avg_sgpa, highest_sgpa]}).dropna()
                        fig_sgpa_comp = px.bar(sgpa_data, x='Category', y='SGPA', text_auto='.2f', title="Class Performance Snapshot (SGPA)", color='Category', color_discrete_map={'Class Average SGPA': '#636EFA', 'Highest SGPA': '#00CC96'})
                        fig_sgpa_comp.update_layout(showlegend=False, yaxis_title="SGPA", xaxis_title="")
                        # MODIFIED: Added border to bar chart
                        fig_sgpa_comp.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
                        st.plotly_chart(fig_sgpa_comp, use_container_width=True)
                        st.caption("Verdict: Compares the average student SGPA with the top performer's SGPA.")
                        figs_for_pdf["Class Performance Snapshot (SGPA)"] = fig_sgpa_comp
                    with r1_col2:
                        avg_marks_data = []
                        for sub in sub_cols_ese:
                            ca_col, mse_col, ese_col = f"{sub}_CA(20)", f"{sub}_MSE(20)", f"{sub}_ESE(60)"
                            if ca_col in df.columns and mse_col in df.columns and ese_col in df.columns:
                                avg_marks_data.append({'Subject': sub, 'Component': 'CA', 'Marks': df[ca_col].mean()})
                                avg_marks_data.append({'Subject': sub, 'Component': 'MSE', 'Marks': df[mse_col].mean()})
                                avg_marks_data.append({'Subject': sub, 'Component': 'ESE', 'Marks': df[ese_col].mean()})
                        if avg_marks_data:
                            avg_df = pd.DataFrame(avg_marks_data)
                            fig_stacked = px.bar(avg_df, x='Subject', y='Marks', color='Component', title="Average Mark Composition by Subject", labels={'Marks': 'Average Marks'}, color_discrete_map={'CA': '#636EFA', 'MSE': '#EF553B', 'ESE': '#00CC96'})
                            # MODIFIED: Added border to bar chart
                            fig_stacked.update_traces(marker_line_color='black', marker_line_width=1.2)
                            st.plotly_chart(fig_stacked, use_container_width=True)
                            st.caption("Verdict: Breaks down performance to identify weaknesses in CA, MSE, or ESE components.")
                            figs_for_pdf["Average Mark Composition by Subject"] = fig_stacked

                    st.markdown("---")

                    # --- ROW 2: Subject Difficulty Ranking (Full Width) ---
                    failure_data = []
                    total_students = len(df)
                    for sub in sub_cols_ese:
                        grade_col = f"{sub}_Grade"
                        if grade_col in df.columns:
                            fail_count = (df[grade_col].str.strip().str.upper() == 'FF').sum()
                            fail_percentage = (fail_count / total_students * 100) if total_students > 0 else 0
                            failure_data.append({"Subject": sub, "Failure Rate (%)": fail_percentage})
                    if failure_data:
                        fail_df = pd.DataFrame(failure_data).sort_values("Failure Rate (%)", ascending=False)
                        fig_difficulty = px.bar(fail_df, x="Failure Rate (%)", y="Subject", orientation='h', title="Subject Difficulty Ranking by Failure Rate", text_auto='.2f', color="Subject", color_discrete_sequence=px.colors.qualitative.Plotly)
                        fig_difficulty.update_layout(yaxis_title="", xaxis_title="Failure Rate (%)", showlegend=False)
                        # MODIFIED: Added border to bar chart
                        fig_difficulty.update_traces(marker_line_color='black', marker_line_width=1.2)
                        st.plotly_chart(fig_difficulty, use_container_width=True)
                        st.caption("Verdict: Highlights which subjects are most challenging for students.")
                        figs_for_pdf["Subject Difficulty Ranking by Failure Rate"] = fig_difficulty

                    st.markdown("---")
                    
                    # --- ROW 3: Grade Distribution & Pass/Fail Analysis ---
                    r3_col1, r3_col2 = st.columns(2)
                    pie_chart_subjects = [sub for sub in sub_cols_ese if "total" not in sub.lower()]
                    dropdown_options = ["Overall"] + pie_chart_subjects
                    
                    with r3_col1:
                        st.markdown("##### 📜 Grade Distribution")
                        selected_grade_option = st.selectbox("Select for Grade Distribution:", options=dropdown_options, key=f"grade_dist_select_{i}")
                        if selected_grade_option == "Overall":
                            all_grades = []
                            for sub in pie_chart_subjects:
                                grade_col = f"{sub}_Grade"
                                if grade_col in df.columns: all_grades.extend(df[grade_col].dropna().str.strip().str.upper())
                            chart_title = "Overall Class Grade Distribution"
                        else:
                            grade_col = f"{selected_grade_option}_Grade"
                            if grade_col in df.columns: all_grades = df[grade_col].dropna().str.strip().str.upper().tolist()
                            else: all_grades = []
                            chart_title = f"Grade Distribution for {selected_grade_option}"
                        if all_grades:
                            grade_counts = pd.Series(all_grades).value_counts().reset_index()
                            grade_counts.columns = ['Grade', 'Count']
                            fig_donut = px.pie(grade_counts, names='Grade', values='Count', hole=0.4, title=chart_title, color_discrete_sequence=px.colors.sequential.RdBu)
                            # MODIFIED: Added border to donut chart
                            fig_donut.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='black', width=1.5)))
                            st.plotly_chart(fig_donut, use_container_width=True)

                    with r3_col2:
                        st.markdown("##### 📊 Pass/Fail Analysis")
                        selected_pf_option = st.selectbox("Select for Pass/Fail details:", options=dropdown_options, key=f"subject_pie_select_{i}")
                        if selected_pf_option == "Overall":
                            fail_count = df['has_failed'].sum()
                            pass_count = len(df) - fail_count
                            chart_title = "Overall Pass vs. Fail Distribution"
                        else:
                            grade_col_pie = f"{selected_pf_option}_Grade"
                            if grade_col_pie in df.columns:
                                fail_count = (df[grade_col_pie].str.strip().str.upper() == 'FF').sum()
                                pass_count = len(df) - fail_count
                                chart_title = f"Pass vs. Fail for {selected_pf_option}"
                            else: fail_count, pass_count, chart_title = 0, 0, "Data not found"
                        pie_data = pd.DataFrame({'Status': ['Passed', 'Failed'], 'Count': [pass_count, fail_count]})
                        fig_pass_fail_pie = px.pie(pie_data, names='Status', values='Count', title=chart_title, color='Status', color_discrete_map={'Passed':'#00CC96', 'Failed':'#EF553B'})
                        # MODIFIED: Ensured border on pie chart
                        fig_pass_fail_pie.update_traces(textposition="outside", textinfo="percent+label", marker=dict(line=dict(color='black', width=1.5)), texttemplate="%{label}: <br>%{value} students (%{percent:.1f}%)")
                        fig_pass_fail_pie.update_layout(showlegend=False, title_x=0.5)
                        st.plotly_chart(fig_pass_fail_pie, use_container_width=True)

                    # --- EXPORT AND INDIVIDUAL ANALYSIS SECTIONS ---
                    st.subheader("📄 Export Classwise Report")
                    if st.button(f"📘 Download Classwise Report ({exam})", key=f"ese_class_pdf_{i}"):
                        try:
                            pdf_bytes = save_ese_classwise_report_bytes(exam, df, figs_for_pdf, top_students_ese, low_students_ese)
                            st.download_button("⬇️ Download ESE Classwise PDF", data=pdf_bytes, file_name=f"{exam}_Classwise_Analysis.pdf", mime="application/pdf", key=f"download_ese_class_pdf_{i}")
                        except Exception as e:
                            st.error(f"Failed to generate ESE PDF: {e}")

                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.subheader("🎯 Download Individual Student Analysis")
                    student_names = df["Name"].dropna().unique()
                    selected_student = st.selectbox("Select a student:", student_names, key=f"ese_student_select_{i}")
                    
                    # START: MODIFIED FOR DYNAMIC ESE STUDENT VIEW
                    if not df[df["Name"] == selected_student].empty:
                        student_row = df[df["Name"] == selected_student]
                        
                        view_options = [
                            "Overall (Total Marks)", 
                            "Overall Internals (CA+MSE)",
                            "CA (Class Assessment)", 
                            "MSE (Mid Sem Exam)", 
                            "ESE (End Sem Exam)"
                        ]
                        selected_view = st.selectbox("Select view:", view_options, key=f"ese_view_select_{i}")

                        sub_marks_list = []
                        chart_title = ""
                        y_range = []

                        if selected_view == "Overall (Total Marks)":
                            chart_title = f"Overall Marks (out of 100) for {selected_student}"
                            y_range = [0, 100]
                            for s in sub_cols_ese:
                                marks_col = f"{s}_Total_Marks"
                                if marks_col in student_row.columns:
                                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                    sub_marks_list.append({'Subject': s, 'Marks': marks})
                        
                        elif selected_view == "Overall Internals (CA+MSE)":
                            chart_title = f"Overall Internal Marks (out of 40) for {selected_student}"
                            y_range = [0, 40]
                            for s in sub_cols_ese:
                                ca_col, mse_col = f"{s}_CA(20)", f"{s}_MSE(20)"
                                if ca_col in student_row.columns and mse_col in student_row.columns:
                                    ca_marks = pd.to_numeric(student_row[ca_col].iloc[0], errors='coerce')
                                    mse_marks = pd.to_numeric(student_row[mse_col].iloc[0], errors='coerce')
                                    total_internal = (ca_marks if pd.notna(ca_marks) else 0) + \
                                                     (mse_marks if pd.notna(mse_marks) else 0)
                                    sub_marks_list.append({'Subject': s, 'Marks': total_internal})

                        elif selected_view == "CA (Class Assessment)":
                            chart_title = f"CA Marks (out of 20) for {selected_student}"
                            y_range = [0, 20]
                            for s in sub_cols_ese:
                                marks_col = f"{s}_CA(20)"
                                if marks_col in student_row.columns:
                                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                    sub_marks_list.append({'Subject': s, 'Marks': marks})

                        elif selected_view == "MSE (Mid Sem Exam)":
                            chart_title = f"MSE Marks (out of 20) for {selected_student}"
                            y_range = [0, 20]
                            for s in sub_cols_ese:
                                marks_col = f"{s}_MSE(20)"
                                if marks_col in student_row.columns:
                                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                    sub_marks_list.append({'Subject': s, 'Marks': marks})

                        elif selected_view == "ESE (End Sem Exam)":
                            chart_title = f"ESE Marks (out of 60) for {selected_student}"
                            y_range = [0, 60]
                            for s in sub_cols_ese:
                                marks_col = f"{s}_ESE(60)"
                                if marks_col in student_row.columns:
                                    marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                    sub_marks_list.append({'Subject': s, 'Marks': marks})
                        
                        sub_marks_df = pd.DataFrame(sub_marks_list).dropna(subset=['Marks'])
                        fig_student_ese_view = px.bar(sub_marks_df, x="Subject", y="Marks", text_auto=True, color="Subject", 
                                                      title=chart_title, color_discrete_sequence=px.colors.qualitative.Bold, 
                                                      range_y=y_range)
                        # MODIFIED: Added border to bar chart
                        fig_student_ese_view.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
                        st.plotly_chart(fig_student_ese_view, use_container_width=True)

                        # Metrics are based on overall performance, so they remain unchanged
                        overall_marks_list = []
                        for s in sub_cols_ese:
                            marks_col = f"{s}_Total_Marks"
                            if marks_col in student_row.columns:
                                marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                overall_marks_list.append({'Subject': s, 'Marks': marks})
                        overall_marks_df = pd.DataFrame(overall_marks_list).dropna(subset=['Marks'])

                        has_failed = student_row['has_failed'].iloc[0]
                        sgpa = student_row['SGPA'].iloc[0]
                        sgpa_display = "FAILED" if has_failed else (f"{sgpa:.2f}" if pd.notna(sgpa) else "N/A")
                        failed_subjects_list = [sub for sub in sub_cols_ese if f"{sub}_Grade" in student_row.columns and str(student_row[f"{sub}_Grade"].iloc[0]).strip().upper() == 'FF']
                        failed_subjects_text = ", ".join(failed_subjects_list) if failed_subjects_list else "None"
                        max_sub = overall_marks_df.loc[overall_marks_df["Marks"].idxmax()] if not overall_marks_df.empty else {"Subject": "N/A", "Marks": 0}
                        min_sub = overall_marks_df.loc[overall_marks_df["Marks"].idxmin()] if not overall_marks_df.empty else {"Subject": "N/A", "Marks": 0}
                        
                        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                        col_m1.metric("📊 SGPA", sgpa_display)
                        col_m2.metric("🏆 Highest (Overall)", f"{max_sub['Subject']} ({max_sub['Marks']})")
                        col_m3.metric("📉 Lowest (Overall)", f"{min_sub['Subject']} ({min_sub['Marks']})")
                        col_m4.metric("❌ Failed Subjects", failed_subjects_text)
                        
                        if st.button("📑 Download Individual Student PDF", key=f"ese_student_pdf_{i}"):
                            # Helper function to create charts for the PDF
                            def create_ese_bar_chart(student_row, sub_cols, marks_type, title, y_range):
                                marks_list = []
                                if marks_type == "Overall Internals (CA+MSE)":
                                    for s in sub_cols:
                                        ca_col, mse_col = f"{s}_CA(20)", f"{s}_MSE(20)"
                                        if ca_col in student_row.columns and mse_col in student_row.columns:
                                            ca_marks = pd.to_numeric(student_row[ca_col].iloc[0], errors='coerce')
                                            mse_marks = pd.to_numeric(student_row[mse_col].iloc[0], errors='coerce')
                                            marks_list.append({'Subject': s, 'Marks': (ca_marks if pd.notna(ca_marks) else 0) + (mse_marks if pd.notna(mse_marks) else 0)})
                                else:
                                    for s in sub_cols:
                                        marks_col = f"{s}_{marks_type}"
                                        if marks_col in student_row.columns:
                                            marks = pd.to_numeric(student_row[marks_col].iloc[0], errors='coerce')
                                            marks_list.append({'Subject': s, 'Marks': marks})
                                
                                df_marks = pd.DataFrame(marks_list).dropna(subset=['Marks'])
                                fig = px.bar(df_marks, x="Subject", y="Marks", text_auto=True, color="Subject", 
                                             title=title, color_discrete_sequence=px.colors.qualitative.Bold, 
                                             range_y=y_range)
                                fig.update_layout(title_font_size=14, title_x=0.5)
                                # MODIFIED: Added border to bar charts
                                fig.update_traces(width=0.4, marker_line_color='black', marker_line_width=1.5)
                                return fig

                            # Generate all 5 charts for the PDF
                            ese_student_figs = {}
                            ese_student_figs[f"Overall Marks (out of 100)"] = create_ese_bar_chart(student_row, sub_cols_ese, "Total_Marks", "", [0, 100])
                            ese_student_figs[f"Overall Internal Marks (out of 40)"] = create_ese_bar_chart(student_row, sub_cols_ese, "Overall Internals (CA+MSE)", "", [0, 40])
                            ese_student_figs[f"CA Marks (out of 20)"] = create_ese_bar_chart(student_row, sub_cols_ese, "CA(20)", "", [0, 20])
                            ese_student_figs[f"MSE Marks (out of 20)"] = create_ese_bar_chart(student_row, sub_cols_ese, "MSE(20)", "", [0, 20])
                            ese_student_figs[f"ESE Marks (out of 60)"] = create_ese_bar_chart(student_row, sub_cols_ese, "ESE(60)", "", [0, 60])
                            
                            pdf_bytes = save_ese_student_report_bytes(selected_student, student_row, sub_cols_ese, ese_student_figs)
                            st.download_button(f"⬇️ Download {selected_student}'s ESE PDF", data=pdf_bytes, file_name=f"{selected_student}_ESE_Analysis.pdf", mime="application/pdf", key=f"download_ese_student_pdf_{i}")
                    # END: MODIFIED FOR DYNAMIC ESE STUDENT VIEW

                    st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
                    st.markdown("#### 📥 Export All Individual Reports")
                    if st.button(f"⬇️ Download All ESE Student Reports ({exam})", key=f"ese_all_student_pdf_{i}"):
                        try:
                            pdf_bytes = save_all_student_reports_bytes(exam_type, df)
                            st.download_button(f"⬇️ Download All ESE Student PDF", data=pdf_bytes, file_name=f"{exam}_All_Individual_ESE_Reports.pdf", mime="application/pdf", key=f"download_ese_all_student_pdf_{i}")
                        except Exception as e:
                            st.error(f"Failed to generate batch ESE PDF: {e}")
                # ---------------- END: RESTRUCTURED ESE BLOCK ----------------

# ----------------- COPYRIGHT FOOTER -----------------
st.markdown("<hr style='border:1px solid #dcdcdc; margin-top: 30px;'>", unsafe_allow_html=True)
st.markdown("""
<div style='text-align:center; padding:10px;'>
    <p style='font-size:14px; color:#888;'>
        &copy; 2025 GradeX. All rights reserved.
        <br>
        Made with ❤️ by Student of SYCET for Academic Excellence.
        <br>
        <span style='color:#6366F1;'>
            <a href="https://streamlit.io" target="_blank" style="color: inherit; text-decoration: none;">
                <span style="display:inline-block; vertical-align:middle;">Powered by Streamlit</span>
            </a>
        </span>
    </p>
</div>
""", unsafe_allow_html=True)
# ---------------- END OF SCRIPT ----------------
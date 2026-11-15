"""
Athena Capital — wealth planning for master's and PhD students.

Run in Positron: open this file and click "Run App", or in a terminal:
    shiny run --reload app.py
Educational project. Not financial, tax, legal or immigration advice.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from shiny import App, reactive, render, req, ui
from shinywidgets import output_widget, render_plotly

from athena import budget as B
from athena import careers as C
from athena import data as D
from athena import events as E
from athena import location as L
from athena import portfolio as PF
from athena import profiles as PR
from athena import report as RP
from athena import travel as T
from athena.budget import money

HERE = Path(__file__).parent
CY = C.CURRENT_YEAR
# Flat palette: black, deep azure and tones of blue. Red is reserved for losses and negative values.
NAVY, GOLD, TEAL, BURG, SAGE, SKY, SLATE = "#0B0E14", "#2F80D1", "#0F4C8A", "#B23B3B", "#1A5FA8", "#D6E6F7", "#7A8799"
WARN = "#5B9BD5"
PALETTE = ["#0B0E14", "#0F4C8A", "#2F80D1", "#8DBBE8", "#0A3363", "#5B9BD5", "#C9DCF2", "#1A5FA8", "#7A8799", "#3C4656"]
DISCLAIMER = ("Athena Capital is an educational class project and does not provide financial, investment, tax, legal or immigration advice. "
              "Figures are estimates built from public data and simplifying assumptions; historical returns do not guarantee future results. "
              "Consult a qualified professional (and your university's international student office, if applicable) before acting.")

METROS = D.metros()
METRO_CHOICES = dict(zip(METROS.id, METROS.name, strict=True))
FIELDS = C.fields()
SECTORS = D.careers()["sectors"]
DEMO: dict[str, Any] = dict(C.DEMO)

INPUTS = {  # id -> type (used for save/load round-trips)
    "name": "text", "age": "int", "residency": "radio", "india_treaty": "check", "treaty_exempt": "num",
    "status": "radio", "prospective_program": "radio", "masters_len": "radio_int", "masters_year": "int", "plan_after_masters": "radio",
    "phd_year": "int", "phd_total": "int", "postdoc_years": "int", "p_tenure": "slider",
    "field": "select", "univ_metro": "select", "target_metro": "select", "target_sector": "select",
    "masters_salary": "num", "phd_salary_override": "num", "salary_growth": "num",
    "stipend": "num", "stipend_type": "radio", "fellowship_share": "slider", "summer_income": "num", "side_income": "num",
    "side_type": "radio", "tuition_covered": "check", "tuition_cost": "num", "student_fica_exempt": "check", "employer_plan": "check",
    "cash": "num", "roth_ira": "num", "pretax_ret": "num", "taxable": "num", "crypto": "num",
    "ug_loan": "num", "ug_rate": "num", "ug_payment": "num", "grad_loan": "num", "grad_rate": "num", "new_borrow": "num",
    "cc_debt": "num", "cc_rate": "num",
    **{k: "num" for k, _, _ in B.EXPENSES},
    "ef_months": "slider", "laptop_amt": "num", "laptop_year": "int", "reloc_amt": "num", "home_down_pct": "slider", "home_year": "int",
    "q1": "radio", "q2": "radio", "q3": "radio", "q4": "radio", "save_rate_after": "slider", "retire_age": "int",
}


# ======================================================================================
# UI helpers
# ======================================================================================
def icon(name: str, size: str = "1.9rem"):
    return ui.tags.i(class_=f"bi bi-{name}", style=f"font-size:{size}")


def head(tag: str, title: str, lede: str, *right):
    return ui.div(ui.div(ui.span(tag, class_="module-tag"), ui.h2(title), ui.p(lede, class_="lede")), ui.div(*right), class_="page-head")


def grid(*kids, col_widths=None, cols=None):
    """Compact form grid (bslib layout_columns adds tall row gaps inside forms)."""
    if cols is None:
        cw = col_widths or (6, 6)
        cols = " ".join(f"{w}fr" for w in cw[: max(1, 12 // cw[0]) if len(set(cw)) == 1 else len(cw)])
    return ui.div(*kids, class_="fgrid", style=f"grid-template-columns:{cols}")


def num(id_, label, value, step=100, **kw):
    return ui.input_numeric(id_, label, value, step=step, **kw)


def vbox(title, out_id, sub_id, ic, cls=""):
    return ui.value_box(title, ui.output_text(out_id), ui.output_text(sub_id), showcase=icon(ic), showcase_layout="top right", class_=cls)


def style(fig: go.Figure, h=340, legend=True, title=None) -> go.Figure:
    x_title = bool(fig.layout.xaxis.title.text)
    fig.update_layout(template="plotly_white", height=h, margin=dict(l=10, r=10, t=40 if title else 18, b=10),
                      font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color="#1A1F29", size=12), colorway=PALETTE,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=legend,
                      legend=dict(orientation="h", yanchor="top", y=-0.3 if x_title else -0.14, x=0, font=dict(size=11)),
                      title=dict(text=title, font=dict(family="Source Serif 4, Georgia, serif", size=16, color=NAVY)) if title else None,
                      hoverlabel=dict(font_family="IBM Plex Sans"))
    fig.update_xaxes(gridcolor="#E8EEF5", zeroline=False, linecolor="#D9E2EC")
    fig.update_yaxes(gridcolor="#E8EEF5", zeroline=False, linecolor="#D9E2EC")
    return fig


def pct(x, d=1):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f}%"


# initial portfolio from the demo profile
_cf0 = B.cash_flow(DEMO)
_paths0 = C.build_paths(DEMO)
_sel0 = C.selected_path(DEMO, _paths0)
_rec0 = C.recommended_equity(C.risk_tolerance(DEMO), C.risk_capacity(DEMO, _cf0["ef_months_have"], C.path_metrics(_sel0, DEMO)["pv"], DEMO["target_sector"]), DEMO, DEMO["target_sector"])
SPEC0 = PF.recommended_spec(_rec0["equity"], _rec0["field_hedge"])

# ======================================================================================
# Persona builder: welcome screen + step-by-step questionnaire
# ======================================================================================
# Client-side visibility rules (mirror careers.phd_track): PhD questions only for PhD-track clients
PHD_JS = ("(input.status === 'phd' || input.status === 'postdoc' || (input.status === 'masters' && input.plan_after_masters === 'phd') || "
          "(input.status === 'prospective' && (input.prospective_program === 'phd' || input.plan_after_masters === 'phd')))")
IN_MASTERS_JS = "(input.status === 'masters' || (input.status === 'prospective' && input.prospective_program !== 'phd'))"
STUDENT_JS = "input.status !== 'postdoc'"
MS_SECTORS = {k: v for k, v in SECTORS.items() if k != "academe"}

# Starting answers for a brand-new client (a typical master's student; every value is editable)
NEW: dict[str, Any] = {
    **DEMO, "name": "", "age": 24, "residency": "us", "status": "masters", "prospective_program": "masters", "masters_len": 2,
    "masters_year": 1, "plan_after_masters": "industry", "field": "Engineering", "univ_metro": "bos", "target_metro": "bos",
    "target_sector": "industry", "masters_salary": 95000, "stipend": 0, "stipend_type": "wages", "summer_income": 0, "side_income": 0,
    "tuition_covered": False, "tuition_cost": 20000, "employer_plan": False, "cash": 5000, "roth_ira": 0, "pretax_ret": 0, "taxable": 0,
    "crypto": 0, "ug_loan": 0, "ug_payment": 0, "grad_loan": 0, "new_borrow": 0, "cc_debt": 0, "laptop_amt": 0, "home_down_pct": 0,
    "q1": "3", "q2": "2", "q3": "2", "q4": "3",
}
V = NEW

RISK_Q = [
    ("q1", "If your investments fell 25% in a month, you would…", {"1": "Sell everything", "2": "Sell some", "3": "Hold and wait", "4": "Buy more"}),
    ("q2", "Which would you choose?", {"1": "$1,000 for certain", "2": "50% chance of $2,500", "3": "25% chance of $6,000", "4": "5% chance of $40,000"}),
    ("q3", "Your investing experience", {"1": "None yet", "2": "A retirement account", "3": "Several years of index funds", "4": "Active, comfortable with swings"}),
    ("q4", "Your main goal for invested money", {"1": "Never lose principal", "2": "Mostly stability", "3": "Balanced growth", "4": "Maximum long-run growth"}),
]

STEPS = [("s_you", "About you", "person"), ("s_degree", "Degree", "mortarboard"), ("s_funding", "Funding & income", "cash-coin"),
         ("s_career", "Career goals", "briefcase"), ("s_money", "Assets & debts", "bank"), ("s_spend", "Monthly spending", "cart3"),
         ("s_goals", "Goals", "flag"), ("s_risk", "Risk profile", "speedometer2"), ("s_review", "Review", "check2-circle")]
STEP_IDS = [s for s, _, _ in STEPS]


def logo(size: int = 30, gid: str = "lg"):
    """Flat deep-azure monogram (gid kept for call compatibility)."""
    return ui.HTML(
        f'<svg class="logo" id="{gid}" width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true">'
        '<rect x=".5" y=".5" width="31" height="31" rx="5" fill="#0F4C8A" stroke="#2F80D1" stroke-opacity=".6"/>'
        '<path d="M9.5 23.5 16 8.5l6.5 15" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M12.4 18.6c2.4-1.9 4.8-1.9 7.2 0" fill="none" stroke="#8DBBE8" stroke-width="2.2" stroke-linecap="round"/></svg>')


def opt(ic: str, title: str, sub: str = ""):
    """Rich label for a choice card."""
    return ui.span(ui.tags.i(class_=f"bi bi-{ic}"), ui.span(ui.tags.b(title), ui.span(sub, class_="opt-sub") if sub else None, class_="opt-text"), class_="opt")


def cards(id_: str, choices: dict, selected, cols: int = 2):
    return ui.div(ui.input_radio_buttons(id_, None, choices, selected=str(selected)), class_=f"choice-cards cols-{cols}")


def when(cond: str, *kids):
    return ui.panel_conditional(cond, *kids)


def section(title: str, *kids):
    return ui.div(ui.div(title, class_="wiz-section"), *kids, class_="wiz-block")


def hint(text: str):
    return ui.p(text, class_="wiz-hint")


def step(sid: str, title: str, lede: str, *body):
    n = STEP_IDS.index(sid) + 1
    return ui.nav_panel(sid, ui.div(ui.div(f"Step {n} of {len(STEPS)}", class_="wiz-kicker"), ui.h2(title), ui.p(lede, class_="wiz-lede"), class_="wiz-head"),
                        *body, value=sid)


STATUS_CHOICES = {
    "prospective": opt("send", "Applying or starting soon", "Planning a master's or a PhD"),
    "masters": opt("journal-bookmark", "Master's student", "In a 1- or 2-year program"),
    "phd": opt("mortarboard", "PhD student", "Any year of a doctoral program"),
    "postdoc": opt("lightbulb", "Postdoc", "Finished the PhD, in a research post"),
}

wiz_steps = [
    ui.nav_panel("welcome", ui.div(), value="welcome"),
    step("s_you", "Let's start with you", "A few basics so we can apply the right tax rules and compare you with the right peers.",
         grid(ui.input_text("name", "Your name", V["name"], placeholder="e.g. Jordan Lee"), num("age", "Age", V["age"], step=1, min=20, max=60), col_widths=(8, 4)),
         section("Tax residency", cards("residency", {"us": opt("flag", "U.S. citizen or resident", "Taxed like any U.S. resident"),
                                                      "intl": opt("globe2", "International student", "F-1 or J-1 visa, nonresident for tax")}, V["residency"])),
         when("input.residency === 'intl'",
              grid(ui.input_checkbox("india_treaty", "I'm a student from India (treaty allows the standard deduction)", V["india_treaty"]),
                   num("treaty_exempt", "Treaty-exempt income ($/yr)", V["treaty_exempt"], step=500, min=0), col_widths=(7, 5)),
              hint("Nonresident students on F-1/J-1 visas generally don't pay Social Security or Medicare tax and can't take the standard deduction unless a treaty allows it."))),
    step("s_degree", "Your degree", "Tell us where you are in school. We only ask about a PhD if you're in one or planning one.",
         section("Where are you now?", cards("status", STATUS_CHOICES, V["status"])),
         when("input.status === 'prospective'",
              section("Which program?", cards("prospective_program", {"masters": opt("journal-bookmark", "A master's degree", "Maybe a PhD afterwards"),
                                                                      "phd": opt("mortarboard", "A PhD", "Going straight into a doctoral program")}, V["prospective_program"]))),
         when(IN_MASTERS_JS,
              section("Your master's",
                      grid(ui.div(ui.input_radio_buttons("masters_len", "Program length", {"1": "1 year", "2": "2 years"}, selected=str(V["masters_len"]), inline=True), class_="seg"),
                           when("input.status === 'masters'", num("masters_year", "Current year of the program", V["masters_year"], step=1, min=1, max=2)), col_widths=(6, 6)),
                      ui.div("After the master's I plan to…", class_="wiz-q"),
                      cards("plan_after_masters", {"industry": opt("briefcase", "Start working", "Industry, government or a nonprofit"),
                                                   "phd": opt("mortarboard", "Continue to a PhD", "We'll ask a few PhD questions")}, V["plan_after_masters"]))),
         when(f"{PHD_JS} && input.status !== 'postdoc'",
              section("Your PhD",
                      grid(when("input.status === 'phd'", num("phd_year", "Current PhD year", V["phd_year"], step=1, min=1, max=9)),
                           num("phd_total", "Expected total length (years)", V["phd_total"], step=1, min=3, max=9), col_widths=(6, 6)))),
         when("input.status === 'postdoc'",
              section("Your postdoc", grid(num("postdoc_left", "Years left in your postdoc", V["postdoc_years"], step=1, min=1, max=6), ui.div(), col_widths=(6, 6)))),
         section("Field & school", grid(ui.input_select("field", "Field of study", FIELDS, selected=V["field"]),
                                        ui.input_select("univ_metro", "Where you study", METRO_CHOICES, selected=V["univ_metro"]), col_widths=(6, 6)))),
    step("s_funding", "Funding & income", "Stipends, assistantships, fellowships and side jobs are taxed differently. This drives your take-home pay and tax plan.",
         grid(num("stipend", "Stipend, assistantship or postdoc pay ($/yr)", V["stipend"], step=1000, min=0),
              num("summer_income", "Summer pay: internship or summer funding ($)", V["summer_income"], step=500, min=0), col_widths=(6, 6)),
         when(IN_MASTERS_JS, hint("Self-funded? Enter 0. A TA/RA job or a scholarship that pays a stipend counts here.")),
         when("input.stipend > 0",
              section("How is it paid?", cards("stipend_type", {"wages": opt("person-badge", "TA / RA wages", "W-2, tax withheld"),
                                                                "fellowship": opt("award", "Fellowship", "No W-2, no withholding"),
                                                                "mixed": opt("intersect", "Mixed", "Part of each")}, V["stipend_type"], cols=3),
                      when("input.stipend_type === 'mixed'", ui.input_slider("fellowship_share", "Fellowship share", 0, 100, V["fellowship_share"], post="%")))),
         section("Other income", grid(num("side_income", "Side income ($/yr)", V["side_income"], step=500, min=0),
                                      ui.div(ui.input_radio_buttons("side_type", "Type", {"w2": "W-2 job", "1099": "Freelance (1099)"}, selected=V["side_type"], inline=True), class_="seg"),
                                      col_widths=(6, 6))),
         when(STUDENT_JS,
              section("Tuition & benefits",
                      ui.input_checkbox("tuition_covered", "My tuition is covered by a waiver or fellowship", V["tuition_covered"]),
                      when("!input.tuition_covered", grid(num("tuition_cost", "Tuition you pay ($/yr)", V["tuition_cost"], step=1000, min=0), ui.div(), col_widths=(6, 6))),
                      when("input.stipend > 0 && input.stipend_type !== 'fellowship'",
                           ui.input_checkbox("student_fica_exempt", "Student FICA exception applies (I work for my own university while enrolled)", V["student_fica_exempt"])))),
         ui.input_checkbox("employer_plan", "My university or employer offers a 403(b) or 457(b) retirement plan", V["employer_plan"])),
    step("s_career", "Career goals", "Where you want to work and live after graduating shapes your earnings, the cities we compare and how much risk your portfolio can take.",
         grid(when(PHD_JS, ui.input_select("target_sector", "Target sector", SECTORS, selected=V["target_sector"])),
              when(f"!{PHD_JS}", ui.input_select("target_sector_ms", "Target sector", MS_SECTORS,
                                                  selected=V["target_sector"] if V["target_sector"] in MS_SECTORS else "industry")),
              ui.input_select("target_metro", "Where you'd like to live after graduating", METRO_CHOICES, selected=V["target_metro"]), col_widths=(6, 6)),
         when(STUDENT_JS,
              grid(num("masters_salary", "Expected salary with a master's ($/yr)", V["masters_salary"], step=5000, min=0), ui.div(), col_widths=(6, 6)),
              when("input.status === 'phd'", hint("Used to compare finishing the PhD with leaving now with a master's.")),
              when(f"!{PHD_JS}", hint("Your best estimate of a first offer: your career center's salary report, Glassdoor or BLS wage data are good sources."))),
         when(PHD_JS,
              section("After the PhD",
                      grid(num("phd_salary_override", "Industry offer after your PhD ($/yr, 0 = national median for your field)", V["phd_salary_override"], step=5000, min=0),
                           ui.div(), col_widths=(6, 6)),
                      grid(when("input.status !== 'postdoc'", num("postdoc_years", "Postdoc years before a faculty job", V["postdoc_years"], step=1, min=0, max=6)),
                           ui.input_slider("p_tenure", "Your chance of a tenure-track job", 0, 100, V["p_tenure"], post="%"), col_widths=(6, 6)),
                      hint("The academic path is an expected value: your tenure-track odds times a faculty salary, otherwise an industry job after the postdoc."))),
         section("Once you're working", grid(num("salary_growth", "Real raise per year (%)", V["salary_growth"], step=0.25),
                                             ui.input_slider("save_rate_after", "Savings rate", 0, 50, V["save_rate_after"], post="%"),
                                             num("retire_age", "Plan to age", V["retire_age"], step=1, min=50, max=75), col_widths=(4, 4, 4)))),
    step("s_money", "What you own and owe", "Today's balances give us your net worth, your peer ranking and a debt plan.",
         section("Savings & investments", grid(num("cash", "Cash & savings", V["cash"]), num("roth_ira", "Roth IRA", V["roth_ira"]),
                                               num("pretax_ret", "403(b) / 401(k) / IRA", V["pretax_ret"]), num("taxable", "Brokerage account", V["taxable"]),
                                               num("crypto", "Crypto", V["crypto"]), col_widths=(4, 4, 4))),
         section("Student loans",
                 grid(num("ug_loan", "Undergraduate loans", V["ug_loan"], step=500), num("ug_rate", "Rate %", V["ug_rate"], step=0.25),
                      num("ug_payment", "Paying $/mo (0 = deferred)", V["ug_payment"], step=25), col_widths=(4, 4, 4)),
                 grid(num("grad_loan", "Graduate loans", V["grad_loan"], step=500), num("grad_rate", "Rate %", V["grad_rate"], step=0.25),
                      when(STUDENT_JS, num("new_borrow", "Borrowing per year ($)", V["new_borrow"], step=1000)), col_widths=(4, 4, 4))),
         section("Credit cards", grid(num("cc_debt", "Balance you carry", V["cc_debt"], step=100), num("cc_rate", "APR %", V["cc_rate"], step=0.5), ui.div(),
                                      col_widths=(4, 4, 4)))),
    step("s_spend", "Monthly spending", "Rough numbers are fine. We sort them into needs and wants and show where to trim.",
         grid(*[num(k, lab, V[k], step=10, min=0) for k, lab, _ in B.EXPENSES], col_widths=(4, 4, 4)), ui.output_ui("wiz_spend")),
    step("s_goals", "Goals", "What you're saving for. Each goal gets a monthly target and an on-track check.",
         ui.input_slider("ef_months", "Emergency fund (months of essential expenses)", 1, 9, V["ef_months"]),
         section("Before & at graduation", grid(num("laptop_amt", "Laptop or equipment ($)", V["laptop_amt"]), num("laptop_year", "Needed by (year)", V["laptop_year"], step=1),
                                                num("reloc_amt", "Moving after graduation ($)", V["reloc_amt"]), col_widths=(4, 4, 4))),
         section("A home", grid(ui.input_slider("home_down_pct", "Down payment (% of price; 0 = not planning to buy)", 0, 25, V["home_down_pct"], post="%"),
                                num("home_year", "Buy by (year)", V["home_year"], step=1), col_widths=(8, 4)))),
    step("s_risk", "Your risk profile", "Risk tolerance is how much ups and downs you can stomach. We compare it with risk capacity: what your finances can actually absorb.",
         *[section(f"{i + 1}. {q}", cards(k, ch, V[k])) for i, (k, q, ch) in enumerate(RISK_Q)],
         ui.output_ui("wiz_risk")),
    step("s_review", "Review your persona", "Check the summary. Click any step on the left to change it; you can also edit everything later from inside the app.",
         ui.output_ui("wiz_review"),
         ui.input_checkbox("wiz_save", "Save this client file on this computer", True)),
]

FEATURES = [
    ("mortarboard", "Life & career paths", "Master's vs. PhD, industry vs. academia: lifetime earnings, break-even ages and your human capital."),
    ("pie-chart", "Portfolio studio", "Mix U.S. and international, large and small, value and growth, any industry, then backtest it from 1 month to 10 years."),
    ("lightning-charge", "Life events", "Layoffs, a child, funding gaps, windfalls, and replays of 2008, 2020 and 2022 against your plan."),
    ("wallet2", "Budget, taxes & goals", "Stipend taxes, FICA rules, Roth IRAs, a savings waterfall and a goals dashboard."),
    ("geo-alt", "Where to live", "Score cities on pay, taxes and housing, then browse homes and rentals on a map."),
    ("newspaper", "News, travel & deals", "Headlines for your field and city, trip planning and a cash-back optimizer."),
]

welcome = ui.div(
    ui.div(ui.div(logo(34, "lgw"), ui.span("Athena Capital", class_="w-brand"), class_="d-flex align-items-center gap-2"),
           when("input.wiz_edit", ui.input_action_button("back_to_app", ui.span(icon("arrow-left", "0.95rem"), " Back to my plan"), class_="btn-sm btn-outline-navy")),
           ui.span("Educational class project · not financial advice", class_="w-tag"), class_="w-top"),
    ui.div(
        ui.span("Wealth planning for master's & PhD students", class_="w-kicker"),
        ui.h1("Welcome to Athena Capital"),
        ui.p("Turn your stipend, degree plan and career goal into a clear money plan: what to save, where to invest, which city fits you, "
             "and what could change along the way.", class_="w-lede"),
        ui.div(ui.input_action_button("wiz_start", ui.span("Start my plan ", icon("arrow-right", "1rem")), class_="btn-primary btn-lg w-cta"),
               ui.span("About 3 minutes · 9 short steps · change anything later", class_="w-time"), class_="w-cta-row"),
        class_="w-hero"),
    ui.div(*[ui.div(ui.tags.i(class_=f"bi bi-{ic}"), ui.h4(t), ui.p(d), class_="w-feat") for ic, t, d in FEATURES], class_="w-feats"),
    ui.div(
        ui.div(ui.h3("Explore a demo client"), ui.p("Jump straight into the app with a ready-made persona.", class_="note"),
               ui.div(*[ui.input_action_button(f"demo_{k}", opt(ic, t, d), class_="persona-card") for k, (_, t, d, ic) in C.DEMOS.items()],
                      class_="persona-grid"), class_="w-panel"),
        ui.div(ui.h3("Open a saved client"), ui.p("Client files are saved on this computer in the profiles folder.", class_="note"),
               ui.input_select("saved_w", None, choices=PR.list_profiles(), width="100%"),
               ui.div(ui.input_action_button("load_w", "Open", class_="btn-primary"),
                      ui.input_action_button("delete_w", "Delete", class_="btn-outline-danger"), class_="d-flex gap-2"),
               class_="w-panel"),
        class_="w-split"),
    ui.div(DISCLAIMER, class_="disclaimer"),
    class_="welcome")

wizard = ui.div(
    ui.div(ui.div(logo(28, "lgz"), ui.span("Athena Capital", class_="w-brand"), class_="d-flex align-items-center gap-2 home-link",
                  title="Back to the welcome screen"),
           ui.output_ui("wiz_progress"), class_="wiz-top"),
    ui.div(
        ui.output_ui("wiz_rail"),
        ui.div(
            ui.navset_hidden(*wiz_steps, id="wiz", selected="welcome"),
            ui.div(
                ui.div(when("input.wiz_edit", ui.input_action_button("wiz_cancel", "Cancel", class_="btn-outline-navy")),
                       when("input.wiz !== 's_you'", ui.input_action_button("wiz_back", ui.span(icon("arrow-left", "1rem"), " Back"), class_="btn-outline-navy")),
                       class_="d-flex gap-2"),
                ui.div(when("input.wiz_edit && input.wiz !== 's_review'", ui.input_action_button("wiz_apply", "Apply changes", class_="btn-outline-navy")),
                       when("input.wiz !== 's_review'", ui.input_action_button("wiz_next", ui.span("Continue ", icon("arrow-right", "1rem")), class_="btn-primary")),
                       when("input.wiz === 's_review'", ui.input_action_button("wiz_finish", ui.span(icon("check2", "1rem"), " Build my plan"), class_="btn-primary")),
                       class_="d-flex gap-2"),
                class_="wiz-foot"),
            class_="wiz-card"),
        class_="wiz-body"),
    class_="wizard")

onboard = ui.div(when("input.wiz === 'welcome'", welcome), when("input.wiz !== 'welcome'", wizard), id="athena-onboard")

persona_strip = ui.div(
    ui.output_ui("persona_chips"),
    ui.div(ui.input_action_button("edit_persona", ui.span(icon("pencil-square", "0.95rem"), " Edit persona"), class_="btn-sm btn-primary"),
           ui.input_action_button("save_btn", ui.span(icon("save", "0.95rem"), " Save"), class_="btn-sm btn-outline-navy"),
           ui.input_action_button("clients_btn", ui.span(icon("people", "0.95rem"), " Clients"), class_="btn-sm btn-outline-navy"), class_="ps-actions"),
    class_="persona-strip")

VIEW_JS = """
document.documentElement.classList.add('onboarding');
document.addEventListener('DOMContentLoaded', function () {
  var ov = function () { return document.getElementById('athena-onboard'); };
  Shiny.addCustomMessageHandler('athena_view', function (m) {
    document.documentElement.classList.toggle('onboarding', !!m.onboarding);
    Shiny.setInputValue('wiz_edit', !!m.edit);
    window.scrollTo(0, 0); if (ov()) { ov().scrollTop = 0; }
    setTimeout(function () { $(".tab-content[data-tabsetid='main']").trigger('shown'); $('#athena-onboard').trigger('shown'); window.dispatchEvent(new Event('resize')); }, 60);
  });
  $(document).on('click', '#wiz_next, #wiz_back, .rail-step', function () { if (ov()) { ov().scrollTop = 0; } });
  $(document).on('click', '.home-link', function (e) { e.preventDefault(); Shiny.setInputValue('go_home', Date.now(), {priority: 'event'}); });
});
"""

# ======================================================================================
# Pages
# ======================================================================================
overview = ui.nav_panel(
    "Overview",
    ui.output_ui("ov_head"),
    ui.layout_columns(
        vbox("Financial health", "vb_health", "vb_health_sub", "clipboard2-pulse"),
        vbox("Net worth vs. peers", "vb_nw", "vb_nw_sub", "people", "vb-gold"),
        vbox("Monthly surplus", "vb_surplus", "vb_surplus_sub", "piggy-bank", "vb-teal"),
        vbox("Career-path value", "vb_path", "vb_path_sub", "mortarboard", "vb-sage"),
        vbox("Stipend purchasing power", "vb_stipend", "vb_stipend_sub", "geo-alt", "vb-burgundy"),
    ),
    ui.layout_columns(
        ui.card(ui.card_header("Your plan at a glance", ui.span("phases of your chosen path", class_="sub")), output_widget("ov_timeline"), full_screen=True),
        ui.card(ui.card_header("Priority actions"), ui.output_ui("ov_actions")),
        col_widths=(7, 5)),
    ui.layout_columns(
        ui.card(ui.card_header("Health score breakdown"), output_widget("ov_health")),
        ui.card(ui.card_header("Net worth outlook", ui.span("median of 1,000 simulations, today's dollars", class_="sub")), output_widget("ov_outlook")),
        col_widths=(5, 7)),
    value="overview")

career = ui.nav_panel(
    "Life & Career",
    head("Module 1 · Client profile", "Life & career planner",
         "Compare degree and career paths on lifetime earnings, see where you stand against peers, and how your future paychecks should shape your investments."),
    ui.layout_columns(
        ui.card(ui.card_header(ui.span("Earnings by path", ui.span("gross, real 2026 dollars", class_="sub")),
                               when(f"!{PHD_JS}", ui.input_switch("cr_compare_phd", "Compare with doing a PhD", False)), class_="d-flex justify-content-between align-items-center"),
                output_widget("cr_paths"), full_screen=True),
        ui.card(ui.card_header("Path comparison"), ui.output_ui("cr_table")),
        col_widths=(7, 5)),
    ui.layout_columns(
        ui.card(ui.card_header("Cumulative earnings", ui.span("where paths cross = break-even", class_="sub")), output_widget("cr_cum")),
        ui.card(ui.card_header("Starting salaries in your field", ui.span(ui.output_text("cr_sed_src", inline=True), class_="sub")), output_widget("cr_sed")),
        col_widths=(7, 5)),
    ui.layout_columns(
        ui.card(ui.card_header("Net worth vs. U.S. households your age", ui.span("Federal Reserve SCF", class_="sub")), output_widget("cr_peer")),
        ui.card(ui.card_header("Stipend purchasing power"), output_widget("cr_stipend"), ui.output_ui("cr_stipend_note")),
        ui.card(ui.card_header("Risk tolerance vs. risk capacity"), output_widget("cr_risk"), ui.output_ui("cr_risk_note")),
        col_widths=(4, 4, 4)),
    ui.card(ui.card_header("Human capital", ui.span("your future earnings as an asset", class_="sub")), ui.output_ui("cr_hc")),
    value="career")

pf_toolbar = ui.div(
    ui.div(ui.div(icon("database", "1.05rem"), class_="tb-ic"), ui.div(ui.div("Market data", class_="tb-label"), ui.output_ui("pf_data_note")), class_="tb-data"),
    ui.input_action_button("pf_refresh", ui.span(icon("cloud-download", "1rem"), " Update market data"), class_="btn-gold tb-btn"),
    ui.div(ui.div("If you had invested…", class_="tb-label"),
           ui.input_radio_buttons("pf_h", None, ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y"], selected="1Y", inline=True), class_="tb-seg"),
    class_="toolbar")

pf_controls = ui.card(
    ui.card_header("Build your portfolio"),
    ui.input_select("pf_preset", "Start from", list(PF.PRESETS), selected="Recommended for my profile"),
    ui.input_action_button("pf_apply_preset", "Load preset", class_="btn-sm btn-outline-navy mb-2"),
    ui.div("Asset classes (%)", class_="sidebar-section-title"),
    grid(
        num("pf_us", "U.S. stocks", SPEC0["us"], step=5, min=0, max=100), num("pf_intl", "Developed intl.", SPEC0["intl"], step=5, min=0, max=100),
        num("pf_em", "Emerging mkts", SPEC0["em"], step=5, min=0, max=100), num("pf_bonds", "Bonds", SPEC0["bonds"], step=5, min=0, max=100),
        num("pf_reit", "Real estate", SPEC0["reit"], step=5, min=0, max=100), num("pf_gold", "Gold", SPEC0["gold"], step=5, min=0, max=100),
        num("pf_cash", "Cash (T-bills)", SPEC0["cash"], step=5, min=0, max=100), ui.output_ui("pf_total"), col_widths=(6,) * 8),
    ui.div("U.S. stock core", class_="sidebar-section-title"),
    ui.div(ui.input_radio_buttons("pf_size", "Company size", ["Total", "Large", "Mid", "Small"], selected=SPEC0["size"], inline=True), class_="seg mb-2"),
    ui.div(ui.input_radio_buttons("pf_style", "Style", ["Blend", "Growth", "Value"], selected=SPEC0["style"], inline=True), class_="seg mb-2"),
    ui.input_switch("pf_esg", "ESG-screened core (ESGU)", False),
    ui.input_select("pf_bond", "Bond fund", PF.BOND_TYPES, selected="BND"),
    ui.div("Industry & theme tilts (% of portfolio, from U.S. stocks)", class_="sidebar-section-title"),
    *[grid(ui.input_select(f"pf_sat{i}", None, {"": "None", **{t: D.etf_label(t) for t in PF.SATELLITES}}, selected=""),
           num(f"pf_sat{i}_w", None, 0, step=1, min=0, max=50), col_widths=(8, 4)) for i in range(3)],
    ui.div("Contributions & costs", class_="sidebar-section-title"),
    grid(num("pf_lump", "Lump sum $", 10000, step=1000, min=0), num("pf_monthly", "Plus $/month", round(_cf0["invest_m"]), step=50, min=0), col_widths=(6, 6)),
    ui.input_action_link("pf_use_budget", "Use my budget's monthly investing amount"),
    grid(ui.input_select("pf_rebal", "Rebalance", ["Monthly", "Quarterly", "Annually", "Never"], selected="Quarterly"),
         ui.input_select("pf_bench", "Benchmark", {"SPY": "S&P 500", "6040": "60/40 VTI/BND", "BIL": "Cash (T-bills)"}), col_widths=(6, 6)),
    num("pf_fee", "Extra annual fee (bps)", 5, step=5, min=0),
)

portfolio = ui.nav_panel(
    "Portfolio Studio",
    head("Module 2 · Portfolio", "Portfolio studio",
         "Design a portfolio from building blocks (U.S. or international, large or small, value or growth, any industry) and see what it would have done over the last month, quarter, year or decade."),
    pf_toolbar,
    ui.layout_columns(
        pf_controls,
        ui.div(
            ui.layout_columns(
                vbox("Value today", "pf_vb_val", "pf_vb_val_sub", "cash-stack"),
                vbox("Return", "pf_vb_ret", "pf_vb_ret_sub", "graph-up-arrow", "vb-gold"),
                vbox("Vs. benchmark", "pf_vb_bench", "pf_vb_bench_sub", "bullseye", "vb-teal"),
                vbox("Worst drop", "pf_vb_dd", "pf_vb_dd_sub", "graph-down-arrow", "vb-burgundy")),
            ui.card(ui.card_header("Growth of your investment"), output_widget("pf_growth"), full_screen=True),
            ui.layout_columns(
                ui.card(ui.card_header("Allocation"), output_widget("pf_donut")),
                ui.card(ui.card_header("Drawdowns"), output_widget("pf_dd")), col_widths=(5, 7)),
            ui.card(ui.card_header("Holdings: trailing returns", ui.span("3Y and 5Y annualized", class_="sub")), ui.output_ui("pf_trailing")),
            ui.layout_columns(
                ui.card(ui.card_header("Diversification: correlations (3 years)"), output_widget("pf_corr")),
                ui.card(ui.card_header("Risk & factor profile"), ui.output_ui("pf_risk")), col_widths=(6, 6)),
            ui.card(ui.card_header("Projection to retirement", ui.span("contributions from your budget & career path; 1,000 simulations of 1928-2026 history", class_="sub")),
                    output_widget("pf_mc"), ui.output_ui("pf_mc_note"), full_screen=True),
        ),
        col_widths=(3, 9)),
    value="portfolio")


def ev_card(sw: str, title: str, *ctl, start_on: bool = False):
    """A life-event toggle whose detail controls appear only when it's switched on."""
    return ui.div(ui.input_switch(sw, title, start_on), ui.panel_conditional(f"input.{sw}", *ctl), class_="mb-2 pb-2 border-bottom")


def yr(id_: str, v: int):
    return ui.input_slider(id_, "Year", CY, CY + 25, v, sep="")


events_page = ui.nav_panel(
    "Life Events",
    head("Module 3 · Life events", "What could change the plan",
         "Layer planned and unplanned events onto your career path and portfolio. Timing matters: replay a real crash at graduation or right before you need the money."),
    ui.layout_columns(
        ui.card(ui.card_header("Scenario builder"),
                when(STUDENT_JS + f" || {PHD_JS}",
                     ui.div("School", class_="sidebar-section-title"),
                     when(STUDENT_JS, ev_card("ev_extra", "Graduation is delayed", ui.input_slider("ev_extra_n", "Extra years", 1, 3, 1))),
                     when(PHD_JS, ev_card("ev_gap", "Funding gap (lose RA/TA or fellowship)", yr("ev_gap_y", CY + 1), ui.input_slider("ev_gap_m", "Months unfunded", 1, 12, 4))),
                     when("input.status === 'phd'", ev_card("ev_quit", "Leave the PhD with a master's", yr("ev_quit_y", CY + 1))),
                     when(STUDENT_JS, ev_card("ev_intern", "Summer industry internship", yr("ev_intern_y", CY + 1), num("ev_intern_amt", "Pay $", 30000, step=1000)))),
                ui.div("Career", class_="sidebar-section-title"),
                ev_card("ev_bonus", "Signing bonus at graduation", num("ev_bonus_amt", "Bonus $", 25000, step=5000)),
                ev_card("ev_layoff", "Layoff", ui.input_slider("ev_layoff_y", "Years after graduating", 0, 15, 3), ui.input_slider("ev_layoff_m", "Months out of work", 1, 12, 6), start_on=True),
                when("input.residency === 'intl'", ev_card("ev_visa", "OPT / visa gap before first job", ui.input_slider("ev_visa_m", "Months", 1, 12, 3))),
                ev_card("ev_random", "Ongoing job-loss risk", ui.input_slider("ev_random_p", "Chance per year", 1, 15, 4, post="%")),
                ui.div("Life", class_="sidebar-section-title"),
                ev_card("ev_child", "Child", yr("ev_child_y", CY + 6), num("ev_child_cost", "Childcare $/yr", 18000, step=1000), ui.input_slider("ev_child_n", "Years", 1, 18, 5)),
                ev_card("ev_med", "Medical emergency", yr("ev_med_y", CY + 2), num("ev_med_cost", "Out of pocket $", 7500, step=500)),
                ev_card("ev_inherit", "Inheritance / windfall", yr("ev_inh_y", CY + 12), num("ev_inh_amt", "Amount $", 50000, step=5000)),
                ui.div("Markets", class_="sidebar-section-title"),
                ev_card("ev_crash", "Replay a real market crash", ui.input_select("ev_crash_name", None, list(PF.CRASHES)),
                        ui.input_slider("ev_crash_off", "Starts in (years from now)", 0, 35, 5), start_on=True)),
        ui.div(
            ui.output_ui("ev_stats"),
            ui.card(ui.card_header("Invested net worth: baseline vs. scenario", ui.span("real dollars; bands = 25th-75th and 10th-90th percentiles", class_="sub")),
                    output_widget("ev_fan"), ui.output_ui("ev_log"), full_screen=True),
            ui.layout_columns(
                ui.card(ui.card_header("Income timeline"), output_widget("ev_income")),
                ui.card(ui.card_header("Sequence-of-returns risk", ui.span("same savings, crash early vs. late", class_="sub")), output_widget("ev_seq"),
                        ui.p("A 2008-style crash in year 1 barely dents a small, growing portfolio; the same crash three years before you need the money hits a much larger balance.", class_="note")),
                col_widths=(6, 6)),
        ),
        col_widths=(3, 9)),
    value="events")

budget_page = ui.nav_panel(
    "Budget & Taxes",
    head("Module 4 · Cash flow, tax & goals", "Budget, taxes & goals",
         "Your real monthly finances: what comes in after student-specific taxes, where it goes, which account each dollar should land in, and whether every goal is on track."),
    ui.layout_columns(
        vbox("Take-home / month", "bg_vb_th", "bg_vb_th_sub", "wallet2"),
        vbox("Spending / month", "bg_vb_sp", "bg_vb_sp_sub", "cart3", "vb-burgundy"),
        vbox("Surplus / month", "bg_vb_sur", "bg_vb_sur_sub", "piggy-bank", "vb-teal"),
        vbox("2026 tax bill", "bg_vb_tax", "bg_vb_tax_sub", "bank", "vb-gold")),
    ui.layout_columns(
        ui.card(ui.card_header("What-ifs"),
                ui.input_slider("trim_wants", "Trim discretionary spending by", 0, 50, 0, post="%"),
                ui.input_slider("extra_cc", "Extra credit-card payment ($/mo)", 0, 500, 0, step=25),
                ui.output_ui("bg_trim_note")),
        ui.card(ui.card_header("Where every dollar goes", ui.span("monthly", class_="sub")), output_widget("bg_sankey"), full_screen=True),
        col_widths=(3, 9)),
    ui.layout_columns(
        ui.card(ui.card_header("Spending mix vs. 50/30/20 guideline"), output_widget("bg_mix")),
        ui.card(ui.card_header("Savings waterfall", ui.span("in priority order", class_="sub")), ui.output_ui("bg_waterfall")),
        ui.card(ui.card_header("Taxes for a graduate student", ui.span("tax year 2026", class_="sub")), ui.output_ui("bg_tax")),
        col_widths=(4, 4, 4)),
    ui.layout_columns(
        ui.card(ui.card_header("Goals dashboard"), ui.output_ui("bg_goals")),
        ui.card(ui.card_header("Student loans & debt"), ui.output_ui("bg_loans")),
        col_widths=(7, 5)),
    ui.card(ui.card_header("Asset location: which account holds what"), ui.output_ui("bg_location")),
    value="budget")

live_page = ui.nav_panel(
    "Where to Live",
    head("Location & housing", "Where to live, and what it costs",
         "Score every metro on cost-adjusted after-tax pay for your field, housing affordability, industry fit and cost of living. "
         "Then pick a city to browse homes and rentals on a map and run rent vs. buy.",
         ui.div(ui.input_radio_buttons("basemap", "Map style", {"carto-positron": "Streets (online)", "white-bg": "Plain (offline)"}, selected="carto-positron", inline=True), class_="seg")),
    ui.layout_columns(
        ui.card(ui.card_header("Your priorities"),
                ui.input_select("loc_sector", "Career sector", SECTORS, selected=DEMO["target_sector"]),
                ui.input_slider("w_income", "Real after-tax pay", 0, 3, 1.5, step=0.25),
                ui.input_slider("w_housing", "Housing affordability", 0, 3, 1, step=0.25),
                ui.input_slider("w_career", "Industry match for your field", 0, 3, 1.5, step=0.25),
                ui.input_slider("w_cost", "Low cost of living", 0, 3, 0.5, step=0.25),
                ui.div("Focus city", class_="sidebar-section-title"),
                ui.input_select("loc_detail", None, METRO_CHOICES, selected=DEMO["target_metro"]),
                ui.p("Drives the city detail, homes & rentals and rent vs. buy sections.", class_="note"),
                ui.input_action_button("loc_set_target", "Make this my target city", class_="btn-sm btn-gold w-100"),
                ui.input_action_button("loc_refresh", "Refresh BLS metro wages", class_="btn-sm btn-outline-navy w-100 mt-2"),
                ui.output_ui("loc_note")),
        ui.div(
            ui.card(ui.card_header("Opportunity map", ui.span("bubble size = cost-adjusted pay; color = overall score", class_="sub")), output_widget("loc_map"), full_screen=True),
            ui.layout_columns(
                ui.card(ui.card_header("Ranking"), ui.output_ui("loc_table")),
                ui.card(ui.card_header("City detail"), ui.output_ui("loc_detail_card"), output_widget("loc_compare")),
                col_widths=(7, 5))),
        col_widths=(3, 9)),
    ui.output_ui("h_section"),
    ui.layout_columns(
        ui.card(ui.card_header("Search homes & rentals"),
                ui.div(ui.input_radio_buttons("h_mode", None, {"rent": "Rent", "buy": "Buy"}, selected="rent", inline=True), class_="seg mb-2"),
                grid(num("h_max", "Max price $", 2500, step=100, min=0), num("h_beds", "Bedrooms", 1, step=1, min=0, max=4), col_widths=(7, 5)),
                ui.input_slider("h_radius", "Within (miles of downtown)", 2, 25, 12),
                ui.div("Live listings (optional)", class_="sidebar-section-title"),
                ui.input_password("h_key", "RentCast API key (never saved)", ""),
                ui.input_action_button("h_fetch", "Add live listings to the map", class_="btn-sm btn-primary w-100"),
                ui.output_ui("h_status"),
                ui.hr(), ui.div("Search the whole city on", class_="sidebar-section-title"), ui.output_ui("h_links")),
        ui.card(ui.card_header("Neighborhood prices & listings", ui.span("each dot is a ZIP code; darker = pricier, faded = over budget", class_="sub")),
                ui.output_ui("h_summary"), output_widget("h_map"), ui.output_ui("h_table"), full_screen=True),
        col_widths=(3, 9)),
    ui.layout_columns(
        ui.card(ui.card_header("Local housing market"), ui.output_ui("h_market"), output_widget("h_trend")),
        ui.card(ui.card_header("Rent vs. buy"),
                grid(num("rvb_price", "Home price", 450000, step=5000), num("rvb_down", "Down %", 10, step=1),
                     num("rvb_rate", "Mortgage rate %", round(D.rules()["housing"]["mortgage_rate_30y"] * 100, 2), step=0.05),
                     num("rvb_years", "Years you'd stay", 7, step=1, min=1, max=30),
                     num("rvb_rent", "Comparable rent $/mo", 2200, step=50), num("rvb_app", "Home price growth %", 3.0, step=0.25),
                     num("rvb_rentg", "Rent growth %", 3.0, step=0.25), num("rvb_ret", "Investment return %", 6.0, step=0.25),
                     num("rvb_tax", "Property tax + ins. %", 1.5, step=0.1), num("rvb_maint", "Maintenance %", 1.0, step=0.1),
                     col_widths=(6,) * 10),
                output_widget("h_rvb"), ui.output_ui("h_rvb_note")),
        col_widths=(5, 7)),
    value="live")

news_page = ui.nav_panel(
    "News",
    head("Briefing", "News for your field, city and money",
         "Headlines matched to your field, target career, target city and the markets you invest in. Live from Google News, cached for offline demos.",
         ui.input_action_button("news_refresh", "Refresh headlines", class_="btn-sm btn-gold", icon=icon("arrow-clockwise", "1rem"))),
    ui.output_ui("news_snapshot"),
    ui.layout_columns(
        ui.card(ui.card_header("Your field & career"), ui.output_ui("news_field")),
        ui.card(ui.card_header("Your target city"), ui.output_ui("news_city")),
        col_widths=(6, 6)),
    ui.layout_columns(
        ui.card(ui.card_header("Markets & your holdings"), ui.output_ui("news_markets")),
        ui.card(ui.card_header("Grad-school money: stipends, loans, funding"), ui.output_ui("news_grad")),
        col_widths=(6, 6)),
    value="news")

PLACE_NAMES = list(T.places())
travel_page = ui.nav_panel(
    "Travel & Deals",
    head("Toolkit", "Travel & deals",
         "Plan a conference trip or a trip home: compare flight, train and driving, open pre-filled searches on the booking sites, budget the trip, and squeeze more cash back out of your spending."),
    ui.layout_columns(
        ui.card(ui.card_header("Trip planner"),
                ui.input_select("tr_from", "From", PLACE_NAMES, selected=METRO_CHOICES[DEMO["univ_metro"]]),
                ui.input_select("tr_to", "To", PLACE_NAMES, selected="New York, NY"),
                grid(ui.input_date("tr_dep", "Depart", value=date.today() + timedelta(days=30)),
                                  ui.input_date("tr_ret", "Return", value=date.today() + timedelta(days=34)), col_widths=(6, 6)),
                num("tr_n", "Travelers", 1, step=1, min=1, max=6),
                ui.input_radio_buttons("tr_purpose", "Purpose", ["Conference", "Visit home", "Vacation", "Interview"], selected="Conference", inline=True),
                ui.div("Budget", class_="sidebar-section-title"),
                grid(num("tr_fare", "Fare $ (round trip, per person)", 320, step=10), num("tr_nights", "Nights", 3, step=1),
                                  num("tr_hotel", "Lodging $/night", 180, step=10), num("tr_meals", "Meals $/day", 50, step=5),
                                  num("tr_reg", "Registration $", 250, step=25), num("tr_reimb", "Reimbursed %", 50, step=5), col_widths=(6,) * 6)),
        ui.div(
            ui.card(ui.card_header("Route & options"), ui.output_ui("tr_summary"), output_widget("tr_map"), ui.output_ui("tr_links"), full_screen=True),
            ui.card(ui.card_header("Trip budget"), ui.output_ui("tr_budget"))),
        col_widths=(4, 8)),
    ui.layout_columns(
        ui.card(ui.card_header("Cash-back optimizer", ui.span("enter your cards' reward rates (%)", class_="sub")),
                *[ui.div(ui.input_text(f"card{i}_name", None, T.DEFAULT_CARDS[i]["name"], placeholder="Card name (optional third card)"),
                         grid(*[num(f"card{i}_{j}", cat, T.DEFAULT_CARDS[i]["rates"][cat], step=0.5, min=0) for j, cat in enumerate(T.REWARD_CATS)],
                              cols="repeat(6, 1fr)"), class_="mb-2") for i in range(3)],
                ui.output_ui("deal_cards")),
        ui.card(ui.card_header("Student perks & savings directory"), ui.output_ui("deal_perks")),
        col_widths=(7, 5)),
    value="travel")

methods_page = ui.nav_panel(
    "Report & Methods",
    head("Under the hood", "Report, data & methods", "Download a client-ready report, check data freshness, and see every source and assumption."),
    ui.layout_columns(
        ui.card(ui.card_header("Client report"), ui.p("A formal, printable summary of every module for the current client."),
                ui.download_button("dl_report", "Download report (HTML → print to PDF)", class_="btn-primary")),
        ui.card(ui.card_header("Refresh live data"), ui.p("Pulls fresh data on your machine and caches it in data/cache/.", class_="note"),
                ui.div(ui.input_action_button("m_refresh_mkt", "Market prices", class_="btn-sm btn-outline-navy"),
                       ui.input_action_button("m_refresh_bls", "BLS metro wages", class_="btn-sm btn-outline-navy"),
                       ui.input_action_button("m_refresh_fred", "FRED housing", class_="btn-sm btn-outline-navy"), class_="d-flex gap-2 flex-wrap")),
        col_widths=(5, 7)),
    ui.card(ui.card_header("Data status"), ui.output_ui("m_status")),
    ui.card(ui.card_header("Methods, sources & limitations"), ui.output_ui("m_methods")),
    value="methods")

app_ui = ui.page_navbar(
    overview, career, portfolio, events_page, budget_page, live_page, news_page, travel_page, methods_page,
    title=ui.span(logo(26, "lgn"), ui.span("Athena Capital"), ui.span("Wealth planning for graduate students", class_="brand-sub"),
                  class_="home-link", title="Back to the welcome screen"),
    id="main", fillable=False, window_title="Athena Capital",
    header=ui.TagList(
        ui.head_content(
            # fonts & icons are bundled in www/vendor so the app looks the same offline
            ui.tags.link(rel="stylesheet", href="vendor/fonts/fonts.css"),
            ui.tags.link(rel="stylesheet", href="vendor/bootstrap-icons/bootstrap-icons.min.css"),
            ui.include_css(HERE / "www" / "styles.css"),
            ui.tags.script(VIEW_JS),
        ),
        onboard,
        persona_strip,
    ),
    footer=ui.div(DISCLAIMER, class_="disclaimer app-footer"),
)


# ======================================================================================
# Server
# ======================================================================================
def server(input, output, session):
    prof = reactive.value(dict(DEMO))
    data_tick = reactive.value(0)
    news_tick = reactive.value(0)
    listings_state = reactive.value(([], "no key"))

    wiz_from_app = reactive.value(False)
    pending_delete = reactive.value("")

    # ---------------- intake: read / push / save / load ----------------
    def read_inputs() -> dict:
        p = {}
        for k, t in INPUTS.items():
            if k == "target_sector":
                continue
            v = input[k]()
            if t in ("num",):
                v = float(v or 0)
            elif t in ("int", "radio_int"):
                v = int(float(v or 0))
            elif t == "slider":
                v = float(v)
            elif t == "check":
                v = bool(v)
            p[k] = v
        p["target_sector"] = input.target_sector() if C.phd_track(p) else input.target_sector_ms()
        if p["status"] == "postdoc":  # postdocs: years left come from the degree step; no tuition, no student FICA exception
            p["postdoc_years"] = int(float(input.postdoc_left() or 1))
            p["tuition_covered"], p["student_fica_exempt"] = True, False
        p["name"] = (p["name"] or "").strip() or "Client"
        p["age"] = int(np.clip(p["age"], 20, 60))
        p["retire_age"] = max(p["retire_age"], p["age"] + 5)
        return p

    def push_inputs(p: dict):
        for k, t in INPUTS.items():
            if k not in p:
                continue
            v = p[k]
            if t == "text":
                ui.update_text(k, value=v)
            elif t in ("num", "int"):
                ui.update_numeric(k, value=v)
            elif t == "select":
                ui.update_select(k, selected=v)
            elif t in ("radio", "radio_int"):
                ui.update_radio_buttons(k, selected=str(v))
            elif t == "slider":
                ui.update_slider(k, value=v)
            elif t == "check":
                ui.update_checkbox(k, value=bool(v))
        ui.update_select("target_sector_ms", selected=p["target_sector"] if p["target_sector"] in MS_SECTORS else "industry")
        ui.update_numeric("postdoc_left", value=p.get("postdoc_years", 2))

    def activate(p: dict, msg: str | None = None):
        prof.set(p)
        on = C.phd_track(p)
        ui.update_select("loc_sector", choices=SECTORS if on else MS_SECTORS,
                         selected=p["target_sector"] if on or p["target_sector"] in MS_SECTORS else "industry")
        ui.update_select("loc_detail", selected=p["target_metro"])
        ui.update_select("tr_from", selected=METRO_CHOICES[p["univ_metro"]])
        if msg:
            ui.notification_show(msg, duration=4)

    # ---------------- views: welcome / persona builder / main app ----------------
    async def show_app():
        await session.send_custom_message("athena_view", {"onboarding": False, "edit": False})

    async def show_builder(step_id: str, from_app: bool):
        wiz_from_app.set(from_app)
        ui.update_navset("wiz", selected=step_id)
        await session.send_custom_message("athena_view", {"onboarding": True, "edit": from_app})

    def refresh_saved(selected: str | None = None):
        ui.update_select("saved_w", choices=PR.list_profiles(), selected=selected)

    def commit(new_client: bool):
        p = read_inputs()
        msg = f"Plan updated for {p['name']}."
        if input.wiz_save():
            slug = PR.save(p)
            refresh_saved(slug)
            msg += " Client file saved."
        activate(p, msg)
        if new_client:
            ui.update_navset("main", selected="overview")

    @reactive.effect
    @reactive.event(input.wiz_start)
    async def _start():
        push_inputs(NEW)
        await show_builder("s_you", from_app=False)

    @reactive.effect
    @reactive.event(input.wiz_next)
    def _next():
        cur = input.wiz()
        if cur in STEP_IDS and cur != STEP_IDS[-1]:
            ui.update_navset("wiz", selected=STEP_IDS[STEP_IDS.index(cur) + 1])

    @reactive.effect
    @reactive.event(input.wiz_back)
    def _back():
        cur = input.wiz()
        if cur in STEP_IDS and cur != STEP_IDS[0]:
            ui.update_navset("wiz", selected=STEP_IDS[STEP_IDS.index(cur) - 1])

    @reactive.effect
    @reactive.event(input.wiz_goto)
    def _goto():
        if input.wiz_goto() in STEP_IDS:
            ui.update_navset("wiz", selected=input.wiz_goto())

    @reactive.effect
    @reactive.event(input.wiz_finish)
    async def _finish():
        commit(new_client=not wiz_from_app())
        await show_app()

    @reactive.effect
    @reactive.event(input.wiz_apply)
    async def _apply():
        commit(new_client=False)
        await show_app()

    @reactive.effect
    @reactive.event(input.wiz_cancel)
    async def _cancel():
        push_inputs(prof())
        await show_app()

    @reactive.effect
    @reactive.event(input.edit_persona)
    async def _edit():
        push_inputs(prof())
        await show_builder("s_you", from_app=True)

    @reactive.effect
    @reactive.event(input.edit_step)
    async def _edit_step():
        push_inputs(prof())
        await show_builder(input.edit_step() if input.edit_step() in STEP_IDS else "s_you", from_app=True)

    def demo_handler(key: str):
        @reactive.effect
        @reactive.event(input[f"demo_{key}"])
        async def _demo():
            p = dict(C.DEMOS[key][0])
            push_inputs(p)
            activate(p, f"Demo persona loaded: {C.DEMOS[key][1]}.")
            ui.update_navset("main", selected="overview")
            await show_app()
        return _demo

    for _k in C.DEMOS:
        demo_handler(_k)

    async def open_client(slug: str | None):
        if not slug:
            ui.notification_show("No saved client selected.", type="warning", duration=3)
            return
        p = {**DEMO, **PR.load(slug)}
        push_inputs(p)
        activate(p, f"Opened {p['name']}.")
        ui.update_navset("main", selected="overview")
        await show_app()

    @reactive.effect
    @reactive.event(input.load_w)
    async def _load_w():
        await open_client(input.saved_w())

    @reactive.effect
    @reactive.event(input.save_btn)
    def _save():
        p = prof()
        slug = PR.save(p)
        refresh_saved(slug)
        ui.notification_show(f"Saved client file for {p['name']}.", duration=3)

    @reactive.effect
    @reactive.event(input.clients_btn)
    def _clients():
        saved = PR.list_profiles()
        ui.modal_show(ui.modal(
            ui.p("Open or delete a saved client file, start a new persona, or go back to the welcome screen.", class_="note"),
            ui.input_select("saved_m", "Saved clients", choices=saved, width="100%") if saved else ui.p("No saved clients yet.", class_="note"),
            ui.div(ui.input_action_button("load_m", "Open", class_="btn-primary"), ui.input_action_button("delete_m", "Delete", class_="btn-outline-danger"),
                   class_="d-flex gap-2 mb-3") if saved else None,
            ui.hr(),
            ui.div(ui.input_action_button("new_client", ui.span(icon("person-plus", "1rem"), " New persona"), class_="btn-outline-navy"),
                   ui.input_action_button("to_welcome", ui.span(icon("house", "1rem"), " Welcome screen"), class_="btn-outline-navy"), class_="d-flex gap-2"),
            title="Client files", easy_close=True, footer=ui.modal_button("Close")))

    @reactive.effect
    @reactive.event(input.load_m)
    async def _load_m():
        ui.modal_remove()
        await open_client(input.saved_m())

    @reactive.effect
    @reactive.event(input.new_client)
    async def _new_client():
        ui.modal_remove()
        push_inputs(NEW)
        await show_builder("s_you", from_app=True)

    @reactive.effect
    @reactive.event(input.go_home)
    async def _go_home():
        push_inputs(prof())  # drop unsaved edits; the current plan stays loaded
        refresh_saved()
        await show_builder("welcome", from_app=True)

    @reactive.effect
    @reactive.event(input.back_to_app)
    async def _back_to_app():
        push_inputs(prof())
        await show_app()

    @reactive.effect
    @reactive.event(input.to_welcome)
    async def _to_welcome():
        ui.modal_remove()
        refresh_saved()
        await show_builder("welcome", from_app=False)

    def confirm_delete(slug: str | None):
        if not slug:
            return
        pending_delete.set(slug)
        ui.modal_show(ui.modal(ui.p(f"Permanently delete the saved client file '{PR.list_profiles().get(slug, slug)}'?"),
                               title="Delete client file", easy_close=True,
                               footer=ui.div(ui.modal_button("Cancel"), ui.input_action_button("delete_yes", "Delete", class_="btn-danger ms-2"))))

    @reactive.effect
    @reactive.event(input.delete_w)
    def _del_w():
        confirm_delete(input.saved_w())

    @reactive.effect
    @reactive.event(input.delete_m)
    def _del_m():
        confirm_delete(input.saved_m())

    @reactive.effect
    @reactive.event(input.delete_yes)
    def _del():
        PR.delete(pending_delete())
        ui.modal_remove()
        refresh_saved()
        ui.notification_show("Client file deleted.", duration=3)

    # ---------------- persona builder live outputs ----------------
    @render.ui
    def wiz_progress():
        cur = input.wiz()
        i = STEP_IDS.index(cur) if cur in STEP_IDS else 0
        return ui.div(ui.span(f"Step {i + 1} of {len(STEPS)}", class_="wiz-count"),
                      ui.div(ui.div(style=f"width:{(i + 1) / len(STEPS) * 100:.0f}%"), class_="wiz-bar"), class_="wiz-prog")

    @render.ui
    def wiz_rail():
        cur = input.wiz()
        i = STEP_IDS.index(cur) if cur in STEP_IDS else 0
        items = []
        for j, (sid, lab, ic) in enumerate(STEPS):
            cls = "rail-step" + (" active" if j == i else " done" if j < i else "")
            items.append(ui.tags.button(ui.span(icon("check2" if j < i else ic, "0.95rem"), class_="rail-ic"), ui.span(lab), type="button", class_=cls,
                                        onclick=f"Shiny.setInputValue('wiz_goto', '{sid}', {{priority: 'event'}})"))
        return ui.div(*items, class_="wiz-rail")

    @render.ui
    def wiz_spend():
        p = read_inputs()
        c = B.cash_flow(p)
        g = c["groups"]
        left = c["take_home"] - c["spend"] - c["loan_pay"] - c["tuition_m"]
        return ui.div(
            ui.div(ui.div("Total spending", class_="k"), ui.div(f"{money(c['spend'])}/mo", class_="v"), class_="stat"),
            *[ui.div(ui.div(k, class_="k"), ui.div(money(v), class_="v"), class_="stat") for k, v in g.items()],
            ui.div(ui.div("Est. take-home pay", class_="k"), ui.div(f"{money(c['take_home'])}/mo", class_="v"), class_="stat"),
            ui.div(ui.div("Left over (after tuition & loan payments)", class_="k"), ui.div(f"{money(left)}/mo", class_="v " + ("pos" if left >= 0 else "neg")), class_="stat"),
            class_="wiz-stats")

    @render.ui
    def wiz_risk():
        tol = C.risk_tolerance({k: input[k]() for k in ("q1", "q2", "q3", "q4")})
        lab = "Conservative" if tol < 3.5 else "Moderate" if tol < 6 else "Growth-oriented" if tol < 8 else "Aggressive"
        return ui.div(ui.div(ui.span("Your risk tolerance", class_="k"), ui.span(f"{tol:.1f} / 10 · {lab}", class_="v"), class_="meter-head"),
                      ui.div(ui.div(style=f"width:{tol * 10:.0f}%"), class_="meter"),
                      ui.p("On the review step we compare this with your risk capacity, which depends on your time horizon, emergency fund, debt and how "
                           "stock-like your future paycheck is.", class_="note mt-2"), class_="wiz-meter")

    @render.ui
    def wiz_review():
        p = read_inputs()
        ps = C.build_paths(p)
        s = C.selected_path(p, ps)
        c = B.cash_flow(p)
        tol = C.risk_tolerance(p)
        hc = C.path_metrics(s, p)["pv"]
        cap = C.risk_capacity(p, c["ef_months_have"], hc, p["target_sector"])
        rec = C.recommended_equity(tol, cap, p, p["target_sector"])
        funding = ("no stipend" if p["stipend"] <= 0 else
                   f"{money(p['stipend'])}/yr " + {"wages": "TA/RA wages", "fellowship": "fellowship", "mixed": "wages + fellowship"}[p["stipend_type"]])

        def row(label, value, sid):
            return ui.tags.tr(ui.tags.td(label), ui.tags.td(value), ui.tags.td(ui.tags.a("Edit", href="#", class_="edit-link",
                                                                                         onclick=f"Shiny.setInputValue('wiz_goto', '{sid}', {{priority: 'event'}}); return false;")))
        rows = [row("Name", f"{p['name']}, {p['age']}", "s_you"),
                row("Tax residency", "International student (F-1/J-1)" if p["residency"] == "intl" else "U.S. citizen / resident", "s_you"),
                row("Where you are", C.status_text(p), "s_degree"), row("Field", p["field"], "s_degree"),
                row("Studying in", METRO_CHOICES[p["univ_metro"]], "s_degree"), row("Funding", funding, "s_funding"),
                row("Career goal", f"{SECTORS[p['target_sector']]} in {METRO_CHOICES[p['target_metro']]}", "s_career"),
                row("Net worth today", money(C.net_worth(p)), "s_money"),
                row("Spending", f"{money(c['spend'])}/mo vs. {money(c['take_home'])}/mo take-home", "s_spend"),
                row("Goals", ", ".join(g["label"].split("(")[0].strip() for g in B.goals(p)) or "Emergency fund", "s_goals")]
        phases = " → ".join(f"{lab} (from {CY + a})" if b_ >= len(s.income) else f"{lab} ({CY + a}–{CY + b_})" for a, b_, lab, _ in s.phases if b_ > a)
        return ui.layout_columns(
            ui.div(ui.h4("Your persona"), ui.tags.table(ui.tags.tbody(*rows), class_="formal review"), class_="wiz-panel"),
            ui.div(ui.h4("Your plan will follow"), ui.p(ui.tags.b(s.label)), ui.p(phases, class_="note"),
                   ui.h4("Risk profile", class_="mt-3"),
                   *[ui.div(ui.div(ui.span(k, class_="k"), ui.span(f"{v:.1f} / 10", class_="v"), class_="meter-head"),
                            ui.div(ui.div(style=f"width:{v * 10:.0f}%"), class_=f"meter {cls}"), class_="mb-2")
                     for k, v, cls in [("Tolerance: what you can stomach", tol, ""), ("Capacity: what you can absorb", cap, "teal"), ("Your plan uses", rec["score"], "ink")]],
                   ui.span(f"Recommended portfolio: about {rec['equity']:.0%} stocks", class_="pill good mt-2"),
                   class_="wiz-panel"),
            col_widths=(7, 5))

    # ---------------- persona bar (top of every page) ----------------
    @render.ui
    def persona_chips():
        p, r = prof(), risk()
        initials = "".join(w[0] for w in p["name"].split()[:2]).upper() or "?"

        def chip(text, sid, ic):
            return ui.tags.button(icon(ic, ".8rem"), ui.span(text), type="button", class_="ps-chip", title="Click to edit",
                                  onclick=f"Shiny.setInputValue('edit_step', '{sid}', {{priority: 'event'}})")
        def city(m):
            return METRO_CHOICES[m].split(",")[0].split("-")[0]
        return ui.div(ui.div(initials, class_="ps-avatar"),
                      ui.div(ui.div(f"{p['name']}, {p['age']}", class_="ps-name"),
                             ui.div(chip(C.status_text(p), "s_degree", "mortarboard"), chip(p["field"], "s_degree", "book"),
                                    chip(f"{city(p['univ_metro'])} → {city(p['target_metro'])}", "s_career", "geo-alt"),
                                    chip(SECTORS[p["target_sector"]], "s_career", "briefcase"),
                                    chip(f"Risk {r['score']:.1f}/10 · {r['equity']:.0%} stocks", "s_risk", "speedometer2"), class_="ps-chips")),
                      class_="ps-left")

    # ---------------- shared calculations (data flows across modules) ----------------
    @reactive.calc
    def paths():
        return C.build_paths(prof())

    @reactive.calc
    def sel():
        return C.selected_path(prof(), paths())

    @reactive.calc
    def compare_phd() -> bool:
        return (not C.phd_track(prof())) and bool(input.cr_compare_phd())

    @reactive.calc
    def paths_view():
        """Paths shown on the Life & Career page (adds PhD what-ifs for master's clients who ask for them)."""
        return C.build_paths(prof(), compare_phd=True) if compare_phd() else paths()

    @reactive.calc
    def cf():
        return B.cash_flow(prof(), input.trim_wants(), input.extra_cc())

    @reactive.calc
    def risk():
        p = prof()
        tol = C.risk_tolerance(p)
        hc = C.path_metrics(sel(), p)["pv"]
        cap = C.risk_capacity(p, cf()["ef_months_have"], hc, p["target_sector"])
        rec = C.recommended_equity(tol, cap, p, p["target_sector"])
        return {"tol": tol, "cap": cap, "hc": hc, **rec}

    @reactive.calc
    def peer():
        p = prof()
        nw = C.net_worth(p)
        pc, row = C.scf_percentile(nw, p["age"])
        return {"nw": nw, "pct": pc, "row": row}

    @reactive.calc
    def stipend():
        return C.stipend_power(prof())

    @reactive.calc
    def health():
        return B.health_score(prof(), cf(), peer()["pct"], stipend()["ratio"] if prof()["stipend"] > 0 else None)

    @reactive.calc
    def spec():
        sats = [(input[f"pf_sat{i}"](), input[f"pf_sat{i}_w"]() or 0) for i in range(3) if input[f"pf_sat{i}"]()]
        return {"us": input.pf_us() or 0, "intl": input.pf_intl() or 0, "em": input.pf_em() or 0, "bonds": input.pf_bonds() or 0,
                "reit": input.pf_reit() or 0, "gold": input.pf_gold() or 0, "cash": input.pf_cash() or 0, "size": input.pf_size(),
                "style": input.pf_style(), "esg": input.pf_esg(), "bond_type": input.pf_bond(), "sat": sats}

    @reactive.calc
    def weights():
        return PF.build_weights(spec())

    @reactive.calc
    def panel():
        data_tick()
        return PF.panel_for(list(weights()))

    @reactive.calc
    def mix():
        return PF.class_mix(weights())

    @reactive.calc
    def volm():
        return PF.vol_multiplier(weights(), panel())

    @reactive.calc
    def start_wealth():
        p = prof()
        return C.assets(p) - p["cc_debt"]

    @reactive.calc
    def baseline_mc():
        p = prof()
        contrib, school_n, _ = E.contribution_schedule(p, sel(), cf(), p["save_rate_after"])
        mc = PF.monte_carlo(mix(), start_wealth(), contrib, vol_mult=volm())
        return mc, school_n

    def set_spec(s: dict):
        for k in ("us", "intl", "em", "bonds", "reit", "gold", "cash"):
            ui.update_numeric(f"pf_{k}", value=s.get(k, 0))
        ui.update_radio_buttons("pf_size", selected=s.get("size", "Total"))
        ui.update_radio_buttons("pf_style", selected=s.get("style", "Blend"))
        ui.update_select("pf_bond", selected=s.get("bond_type", "BND"))
        sats = s.get("sat", [])
        for i in range(3):
            t, w = sats[i] if i < len(sats) else ("", 0)
            ui.update_select(f"pf_sat{i}", selected=t)
            ui.update_numeric(f"pf_sat{i}_w", value=w)

    @reactive.effect
    @reactive.event(input.pf_apply_preset)
    def _preset():
        name = input.pf_preset()
        s = PF.PRESETS[name] or PF.recommended_spec(risk()["equity"], risk()["field_hedge"], input.pf_esg())
        set_spec(s)

    @reactive.effect
    @reactive.event(prof, ignore_init=True)
    def _prof_changed_portfolio():
        if input.pf_preset() == "Recommended for my profile":
            set_spec(PF.recommended_spec(risk()["equity"], risk()["field_hedge"], input.pf_esg()))
        ui.update_numeric("pf_monthly", value=round(cf()["invest_m"]))

    @reactive.effect
    @reactive.event(input.pf_use_budget)
    def _use_budget():
        ui.update_numeric("pf_monthly", value=round(cf()["invest_m"]))

    def refresh(kind: str):
        with ui.Progress(min=0, max=1) as pr:
            pr.set(0.2, message={"mkt": "Downloading ETF prices from Yahoo Finance…", "bls": "Querying the BLS OEWS API…",
                                 "fred": "Downloading metro housing series from FRED…"}[kind])
            ok, msg = {"mkt": D.refresh_etf_prices, "bls": D.refresh_oews_metro, "fred": D.refresh_fred_housing}[kind]()
            pr.set(1)
        if kind == "fred":
            global METROS
            METROS = D.metros()
        data_tick.set(data_tick() + 1)
        ui.notification_show(msg, type="message" if ok else "warning", duration=6)

    @reactive.effect
    @reactive.event(input.pf_refresh, input.m_refresh_mkt)
    def _r1():
        refresh("mkt")

    @reactive.effect
    @reactive.event(input.loc_refresh, input.m_refresh_bls)
    def _r2():
        refresh("bls")

    @reactive.effect
    @reactive.event(input.m_refresh_fred)
    def _r3():
        refresh("fred")

    # ==================================================================================
    # OVERVIEW
    # ==================================================================================
    @render.ui
    def ov_head():
        p = prof()
        status = C.status_text(p)
        grad = CY + B.remaining_school_years(p)
        return ui.div(ui.span("Client overview", class_="module-tag"), ui.h2(f"{p['name']}, {p['age']}"),
                      ui.p(f"{status} in {p['field']}"),
                      ui.div(ui.span(f"Studying in {METRO_CHOICES[p['univ_metro']]}", class_="pill"),
                             ui.span(f"Finishing ~{grad}", class_="pill"),
                             ui.span(f"Goal: {SECTORS[p['target_sector']]}", class_="pill"),
                             ui.span(f"Target city: {METRO_CHOICES[p['target_metro']]}", class_="pill"),
                             ui.span("International student" if p["residency"] == "intl" else "U.S. tax resident", class_="pill"), class_="chips"),
                      class_="hero")

    @render.text
    def vb_health():
        return f"{health()['score']:.0f} / 100"

    @render.text
    def vb_health_sub():
        return f"Grade {health()['grade']}"

    @render.text
    def vb_nw():
        return money(peer()["nw"])

    @render.text
    def vb_nw_sub():
        return f"~{peer()['pct']:.0f}th percentile, households under {'35' if prof()['age'] < 35 else '45'}"

    @render.text
    def vb_surplus():
        return money(cf()["surplus"])

    @render.text
    def vb_surplus_sub():
        return f"{cf()['savings_rate']:.0%} of take-home saved"

    @render.text
    def vb_path():
        return money(C.path_metrics(sel(), prof())["pv"])

    @render.text
    def vb_path_sub():
        return f"PV of earnings: {sel().label}"

    @render.text
    def vb_stipend():
        return f"{stipend()['ratio']:.2f}× GRFP" if prof()["stipend"] > 0 else "Self-funded"

    @render.text
    def vb_stipend_sub():
        s = stipend()
        return f"{money(s['real'])} in U.S.-average dollars" if prof()["stipend"] > 0 else "no stipend: savings, loans or family support"

    @render_plotly
    def ov_timeline():
        p = prof()
        s = sel()
        fig = go.Figure()
        colors = {"school": GOLD, "industry": NAVY, "postdoc": "#A9C9EC", "academe": TEAL, "government": "#0A3363", "nonprofit": "#7A8799"}
        for a, b_, lab, sec in s.phases:
            b_ = min(b_, 20)
            if b_ <= a:
                continue
            fig.add_trace(go.Bar(y=[s.label], x=[b_ - a], base=[CY + a], orientation="h", name=lab, marker_color=colors.get(sec, SLATE),
                                 text=[lab], textposition="inside", insidetextanchor="middle", textfont=dict(color="white"),
                                 hovertemplate=f"{lab}: {CY + a}-{CY + b_}<extra></extra>"))
        gs = B.goals(p)
        if gs:
            fig.add_trace(go.Scatter(x=[g["year"] for g in gs], y=["Goals"] * len(gs), mode="markers+text", marker=dict(symbol="diamond", size=13, color=WARN),
                                     text=[g["label"].split("(")[0].strip() for g in gs], textposition=["top center", "bottom center"] * 3,
                                     textfont=dict(size=10, color=SLATE), hovertemplate="%{text}: %{x}<extra></extra>"))
        fig.update_layout(barmode="stack")
        fig.update_xaxes(range=[CY, CY + 20], dtick=2, title="Year")
        fig.update_yaxes(categoryorder="array", categoryarray=["Goals", s.label], showticklabels=True, tickfont=dict(size=10))
        return style(fig, 260, legend=False)

    @render.ui
    def ov_actions():
        p, c, t = prof(), cf(), cf()["tax"]
        acts = []
        if p["cc_debt"] > 0:
            acts.append(("Pay off the credit card first", f"{money(p['cc_debt'])} at {p['cc_rate']:.0f}% APR costs more than any investment earns."))
        if c["ef_months_have"] < 1:
            acts.append(("Build a one-month cash cushion", f"Essentials cost {money(c['needs_m'])}/month; stipends can arrive late."))
        if p["roth_ira"] + p["pretax_ret"] < 250000:
            if p["stipend"] > 0:
                acts.append(("Fund a Roth IRA from your stipend", f"Your stipend counts as compensation for IRA purposes (SECURE Act). 2026 limit $7,500; you're in the {t['marginal']:.0%} bracket now, likely higher later."))
            elif p["side_income"] + p["summer_income"] > 0:
                acts.append(("Fund a Roth IRA from your earnings", f"Pay from a job or internship lets you contribute up to $7,500 (2026). You're in the {t['marginal']:.0%} bracket now; your first full salary will put you higher."))
        if t["needs_estimates"]:
            acts.append(("Pay quarterly estimated taxes", f"Fellowship income isn't withheld: set aside about {money(t['quarterly'])} per quarter (Form 1040-ES)."))
        if p["stipend_type"] != "fellowship" and not p["student_fica_exempt"]:
            acts.append(("Check the student FICA exception", "TA/RA wages from your own university while enrolled are usually exempt from Social Security & Medicare tax."))
        if p["residency"] == "intl":
            acts.append(("File Form 8843 / 1040-NR", "Nonresident students file even with no income; check your treaty article for exempt amounts."))
        ln = B.loan_projection(p)
        if ln["balance_at_grad"] > 0:
            acts.append(("Plan for your student loans", f"Unsubsidized interest accrues in school: about {money(ln['balance_at_grad'])} at graduation (~{money(ln['payment_10y'])}/mo over 10 yrs)."))
        if risk()["field_hedge"]:
            acts.append(("Don't double up on your own industry", "Your paycheck already depends on tech; the recommended mix tilts to value stocks and skips tech sector bets."))
        gs = [g for g in B.goal_status(p, c) if not g["on_track"]]
        if gs:
            acts.append((f"Close the gap on '{gs[0]['label']}'", f"Needs {money(gs[0]['need_m'])}/mo; your plan provides {money(gs[0]['plan_m'])}/mo. See Budget & Taxes for fixes."))
        return ui.div(*[ui.div(ui.div(str(i + 1), class_="n"), ui.div(ui.tags.b(a), ui.div(b_, class_="note")), class_="action") for i, (a, b_) in enumerate(acts[:7])]) if acts else ui.p("No urgent actions.")

    @render_plotly
    def ov_health():
        h = health()
        parts = h["parts"]
        fig = go.Figure(go.Bar(x=[v * 100 for v in parts.values()], y=list(parts), orientation="h",
                               marker_color=[TEAL if v >= 0.7 else WARN if v >= 0.4 else BURG for v in parts.values()],
                               text=[f"{v * 100:.0f}" for v in parts.values()], textposition="outside"))
        fig.update_xaxes(range=[0, 118], title="Score (0-100)")
        fig.update_yaxes(autorange="reversed")
        return style(fig, 300, legend=False)

    @render_plotly
    def ov_outlook():
        p = prof()
        mc, school_n = baseline_mc()
        ages = p["age"] + mc["years"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ages, y=mc["pct"][90], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=ages, y=mc["pct"][10], fill="tonexty", fillcolor="rgba(47,128,209,0.16)", line=dict(width=0), name="10th-90th pct"))
        fig.add_trace(go.Scatter(x=ages, y=mc["pct"][50], line=dict(color=NAVY, width=3), name="Median"))
        fig.add_vline(x=p["age"] + school_n, line_dash="dot", line_color=GOLD, annotation_text="Graduation")
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Invested net worth")
        fig.update_xaxes(title="Age")
        return style(fig, 300)

    # ==================================================================================
    # MODULE 1: LIFE & CAREER
    # ==================================================================================
    @render_plotly
    def cr_paths():
        p = prof()
        fig = go.Figure()
        for i, x in enumerate(paths_view()):
            sel_ = x.key == sel().key
            fig.add_trace(go.Scatter(x=p["age"] + np.arange(len(x.income)), y=x.income, name=x.label,
                                     line=dict(width=3.5 if sel_ else 1.6, color=PALETTE[i % len(PALETTE)], dash=None if sel_ else "dot")))
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Gross earnings / yr")
        fig.update_xaxes(title="Age")
        return style(fig, 360)

    @render.ui
    def cr_table():
        p = prof()
        ps = paths_view()
        base = next((x for x in ps if x.key in ("ms_out", "ms_industry")), None)
        rows = []
        for x in ps:
            m = C.path_metrics(x, p)
            be = C.breakeven_age(x, base, p["age"]) if base and x is not base else None
            rows.append(ui.tags.tr(
                ui.tags.td(ui.tags.b(x.label) if x.key == sel().key else x.label, ui.div(x.note, class_="note") if x.note else None),
                ui.tags.td(money(m["start_salary"]), class_="num"), ui.tags.td(money(m["pv"]), class_="num"),
                ui.tags.td(str(be) if be else ("–" if not base or x is base else "never"), class_="num"),
                class_="hl" if x.key == sel().key else None))
        return ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("Path"), ui.tags.th("First full salary", class_="num"),
                                                             ui.tags.th("PV of earnings (4%)", class_="num"), ui.tags.th("Break-even age*", class_="num"))),
                                    ui.tags.tbody(*rows), class_="formal"),
                      ui.p(cr_basis(p) + " *Age when cumulative earnings overtake the "
                           + ("'leave with a master's' path" if p["status"] == "phd" else "Master's → Industry path") + ". Highlighted: your chosen path.", class_="note mt-2"))

    def cr_basis(p: dict) -> str:
        src = C.wage_factor(p["target_metro"], p["field"], "industry")[1]
        if C.phd_track(p):
            return f"Salaries: NSF SED 2024 medians for your field and sector, scaled to your target metro ({src})."
        txt = f"Salaries: your expected master's salary (government and nonprofit scaled by NSF SED sector pay ratios), adjusted to your target metro ({src})."
        if compare_phd():
            txt += f" PhD what-ifs use NSF SED 2024 medians and a ${C.TYPICAL_PHD_STIPEND:,.0f} stipend (NSF GRFP)."
        return txt

    @render_plotly
    def cr_cum():
        p = prof()
        fig = go.Figure()
        for i, x in enumerate(paths_view()):
            fig.add_trace(go.Scatter(x=p["age"] + np.arange(len(x.income)), y=np.cumsum(x.income), name=x.label,
                                     line=dict(width=3 if x.key == sel().key else 1.5, color=PALETTE[i % len(PALETTE)])))
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Cumulative earnings")
        fig.update_xaxes(title="Age")
        return style(fig, 320)

    @render.text
    def cr_sed_src():
        return "NSF Survey of Earned Doctorates 2024" if C.phd_track(prof()) or compare_phd() else "your estimate vs. BLS OEWS May 2025"

    @render_plotly
    def cr_sed():
        p = prof()
        f = D.careers()["fields"][p["field"]]
        sed = f["sed"]
        occ = f.get("occ_industry")
        if C.phd_track(p) or compare_phd():
            labs = ["Postdoc", "Academia", "Government", "Nonprofit", "Industry"]
            vals = [sed["postdoc"], sed["academe"], sed["government"], sed["nonprofit"], sed["industry"]]
            colors = ["#D6E6F7", "#5B9BD5", "#1A5FA8", "#0A3363", "#0A3363"]
            if compare_phd():
                labs.append("Your master's estimate")
                vals.append(p["masters_salary"])
                colors.append(WARN)
        else:
            city = METRO_CHOICES[p["target_metro"]].split(",")[0]
            labs = ["Nonprofit (est.)", "Government (est.)", "Your expected salary"]
            vals = [C.expected_salary(p, "nonprofit"), C.expected_salary(p, "government"), p["masters_salary"]]
            colors = ["#D6E6F7", "#5B9BD5", "#0A3363"]
            if occ:
                wf, _ = C.wage_factor(p["target_metro"], p["field"], "industry")
                labs = [f"BLS mean in {city} (est.)", "BLS U.S. mean", *labs]
                vals = [occ[2] * wf, occ[2], *vals]
                colors = ["#A9C9EC", "#7A8799", *colors]
        fig = go.Figure(go.Bar(x=vals, y=labs, orientation="h", marker_color=colors, text=[money(v) for v in vals], textposition="outside"))
        if occ and (C.phd_track(p) or compare_phd()):
            fig.add_vline(x=occ[2], line_dash="dot", line_color=GOLD, annotation_text=f"OEWS mean: {occ[1]}", annotation_position="top")
        elif occ:
            fig.add_annotation(text=f"BLS occupation: {occ[1]}", xref="paper", yref="paper", x=0, y=1.08, showarrow=False, font=dict(size=11, color=SLATE))
        fig.update_xaxes(tickprefix="$", tickformat="~s", range=[0, max(vals) * 1.3])
        return style(fig, 320, legend=False)

    @render_plotly
    def cr_peer():
        pr = peer()
        row = pr["row"]
        labs = ["10th", "25th", "Median", "75th", "90th"]
        vals = [row["p10"], row["p25"], row["p50"], row["p75"], row["p90"]]
        # values sit under the bars (in the axis labels) so nothing collides with the "you" line
        xl = [f"{lab}<br><b>{money(v)}</b>" for lab, v in zip(labs, vals, strict=True)]
        fig = go.Figure(go.Bar(x=xl, y=vals, marker_color=["#A9C9EC", "#5B9BD5", "#1A5FA8", "#0F4C8A", "#0A3363"],
                               hovertemplate="%{x}<extra></extra>"))
        fig.add_hline(y=pr["nw"], line_dash="dash", line_width=2, line_color=NAVY)
        fig.add_annotation(text=f"<b>- - You: {money(pr['nw'])}</b> · about the {pr['pct']:.0f}th percentile", xref="paper", yref="paper",
                           x=0, y=1.1, xanchor="left", showarrow=False, font=dict(size=12, color=NAVY))
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        fig.update_layout(margin=dict(t=40))
        return style(fig, 300, legend=False)

    @render_plotly
    def cr_stipend():
        s = stipend()
        p = prof()
        fig = go.Figure(go.Bar(x=["Your stipend", "Cost-adjusted", "NSF GRFP"], y=[p["stipend"], s["real"], s["grfp"]],
                               marker_color=[SLATE, NAVY, GOLD], text=[money(v) for v in (p["stipend"], s["real"], s["grfp"])], textposition="outside"))
        fig.update_yaxes(tickprefix="$", tickformat="~s", range=[0, max(p["stipend"], s["real"], s["grfp"]) * 1.25])
        return style(fig, 250, legend=False)

    @render.ui
    def cr_stipend_note():
        s = stipend()
        return ui.p(f"{s['metro']} prices are {s['rpp']:.1f}% of the U.S. average (BEA RPP 2024), so your stipend buys what "
                    f"{money(s['real'])} buys nationally: {s['ratio']:.2f}× the NSF GRFP fellowship.", class_="note")

    @render_plotly
    def cr_risk():
        r = risk()
        fig = go.Figure()
        for lab, v, col in [("Tolerance (what you can stomach)", r["tol"], GOLD), ("Capacity (what you can absorb)", r["cap"], TEAL), ("Plan uses", r["score"], NAVY)]:
            fig.add_trace(go.Bar(y=[lab], x=[v], orientation="h", marker_color=col, text=[f"{v:.1f}"], textposition="inside"))
        fig.update_xaxes(range=[0, 10])
        fig.update_yaxes(autorange="reversed")
        return style(fig, 220, legend=False)

    @render.ui
    def cr_risk_note():
        r = risk()
        gap = r["tol"] - r["cap"]
        msg = ("Your appetite exceeds what your finances can absorb, so the plan is capped near capacity." if gap > 1 else
               "You could afford more risk than you're comfortable with. Long horizon and strong earning power favor stocks." if gap < -1 else
               "Your stated tolerance and your capacity line up.")
        return ui.div(ui.p(msg, class_="note"), ui.span(f"Recommended stocks: {r['equity']:.0%}", class_="pill good"))

    @render.ui
    def cr_hc():
        p, r = prof(), risk()
        sec = p["target_sector"]
        el = C.EQUITY_LIKENESS[sec]
        share = r["hc"] / (r["hc"] + max(C.assets(p), 1))
        kind = "stock-like" if el >= 0.4 else "bond-like" if el <= 0.2 else "balanced"
        hedge = (" Because your earnings are tied to the tech economy, the recommended portfolio avoids tech-sector tilts and leans toward value stocks." if r["field_hedge"] else "")
        return ui.layout_columns(
            ui.div(ui.h3(money(r["hc"])), ui.p("present value of your future earnings on your chosen path", class_="note")),
            ui.div(ui.h3(f"{share:.1%}"), ui.p("of your total wealth is human capital", class_="note")),
            ui.div(ui.h3(kind.title()), ui.p(f"{SECTORS[sec]} earnings move with markets ~{el:.0%}", class_="note")),
            ui.div(ui.p(f"A tenured professor's salary behaves like a bond, so they can hold more stocks. An industry researcher's pay and bonus "
                        f"fall in recessions, like a stock.{hedge}", class_="callout")),
            col_widths=(2, 2, 2, 6))

    # ==================================================================================
    # MODULE 2: PORTFOLIO
    # ==================================================================================
    @render.ui
    def pf_total():
        s = spec()
        tot = sum(s[k] for k in ("us", "intl", "em", "bonds", "reit", "gold", "cash"))
        return ui.div(ui.span(f"Total {tot:.0f}%", class_="pill " + ("good" if abs(tot - 100) < 0.5 else "warn")),
                      ui.div("auto-scaled to 100%" if abs(tot - 100) >= 0.5 else "", class_="note"), class_="mt-4")

    @render.ui
    def pf_data_note():
        return ui.div(panel().note, class_="tb-note")

    @reactive.calc
    def sim():
        return PF.simulate(weights(), panel(), input.pf_h(), input.pf_lump() or 0, input.pf_monthly() or 0, input.pf_rebal(), input.pf_fee() or 0)

    @reactive.calc
    def bench():
        b = input.pf_bench()
        w = {"SPY": {"SPY": 1.0}, "6040": {"VTI": 0.6, "BND": 0.4}, "BIL": {"BIL": 1.0}}[b]
        return PF.simulate(w, panel(), input.pf_h(), input.pf_lump() or 0, input.pf_monthly() or 0, "Quarterly", 0)

    @render.text
    def pf_vb_val():
        s = sim()
        req(s)
        return money(s["end_value"])

    @render.text
    def pf_vb_val_sub():
        s = sim()
        req(s)
        return f"from {money(s['contributed'])} invested ({money(s['gain'], True)})"

    @render.text
    def pf_vb_ret():
        s = sim()
        req(s)
        return pct(s["twr"])

    @render.text
    def pf_vb_ret_sub():
        s = sim()
        req(s)
        return f"{s['start']:%b %d, %Y} - {s['end']:%b %d, %Y}" + (f" · {pct(s['ann'])}/yr" if s["ann"] is not None else "")

    @render.text
    def pf_vb_bench():
        s, b = sim(), bench()
        req(s and b)
        return f"{(s['twr'] - b['twr']) * 100:+.1f} pts"

    @render.text
    def pf_vb_bench_sub():
        b = bench()
        req(b)
        return f"benchmark returned {pct(b['twr'])}"

    @render.text
    def pf_vb_dd():
        s = sim()
        req(s)
        return pct(s["max_dd"])

    @render.text
    def pf_vb_dd_sub():
        s = sim()
        req(s)
        return f"volatility {pct(s['vol'])} · Sharpe {s['sharpe']:.2f}"

    @render_plotly
    def pf_growth():
        s, b = sim(), bench()
        req(s)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=s["value"].index, y=s["value"], name="Your portfolio", line=dict(color=NAVY, width=2.5)))
        if b:
            fig.add_trace(go.Scatter(x=b["value"].index, y=b["value"], name={"SPY": "S&P 500", "6040": "60/40", "BIL": "Cash"}[input.pf_bench()],
                                     line=dict(color=GOLD, width=1.6, dash="dot")))
        contrib = (input.pf_lump() or 0) + (s["value"].index.to_period("M").astype(str).factorize()[0]) * (input.pf_monthly() or 0)
        fig.add_trace(go.Scatter(x=s["value"].index, y=contrib, name="Amount contributed", line=dict(color=SLATE, width=1, dash="dash")))
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        return style(fig, 340)

    @render_plotly
    def pf_donut():
        w = weights()
        fig = go.Figure(go.Pie(labels=[D.etf_label(t) for t in w], values=list(w.values()), hole=0.6, sort=False, marker=dict(colors=PALETTE), textinfo="percent"))
        mx = mix()
        fig.update_layout(annotations=[dict(text=f"<b>{mx['stock']:.0%}</b><br>stocks", showarrow=False, font=dict(size=16, family="Source Serif 4"))])
        return style(fig, 300)

    @render_plotly
    def pf_dd():
        s, b = sim(), bench()
        req(s)
        fig = go.Figure()
        g = s["growth"]
        fig.add_trace(go.Scatter(x=g.index, y=g / g.cummax() - 1, fill="tozeroy", name="Your portfolio", line=dict(color=BURG, width=1)))
        if b:
            gb = b["growth"]
            fig.add_trace(go.Scatter(x=gb.index, y=gb / gb.cummax() - 1, name="Benchmark", line=dict(color=SLATE, width=1, dash="dot")))
        fig.update_yaxes(tickformat=".0%")
        return style(fig, 300)

    @render.ui
    def pf_trailing():
        w = weights()
        tbl = PF.trailing_table(list(w) + ["SPY"], panel())
        cols = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"]

        def cell(v):
            if pd.isna(v):
                return ui.tags.td("–", class_="num")
            return ui.tags.td(f"{v * 100:+.1f}%", class_="num " + ("pos" if v >= 0 else "neg"))
        rows = [ui.tags.tr(ui.tags.td(ui.tags.b(r.Ticker)), ui.tags.td(r.Fund), ui.tags.td(f"{w.get(r.Ticker, 0):.0%}" if r.Ticker in w else "bench", class_="num"),
                           *[cell(r[c]) for c in cols], class_="hl" if r.Ticker == "SPY" else None) for _, r in tbl.iterrows()]
        note = " Proxy mode: holdings map to asset-class history; refresh market data for real ETF returns." if panel().proxy else ""
        return ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("Ticker"), ui.tags.th("Fund"), ui.tags.th("Weight", class_="num"),
                                                             *[ui.tags.th(c, class_="num") for c in cols])), ui.tags.tbody(*rows), class_="formal"),
                      ui.p("Total returns from adjusted prices." + note, class_="note mt-1"))

    @render_plotly
    def pf_corr():
        c = PF.correlation(weights(), panel())
        fig = go.Figure(go.Heatmap(z=c.values, x=list(c.columns), y=list(c.index), zmin=-1, zmax=1,
                                   colorscale=[[0, "#2F80D1"], [0.5, "#F6F9FC"], [1, BURG]], text=np.round(c.values, 2), texttemplate="%{text}"))
        return style(fig, 320, legend=False)

    @render.ui
    def pf_risk():
        s = sim()
        req(s)
        fe = PF.factor_exposure(s, panel())
        rows = [("Annualized volatility", pct(s["vol"])), ("Max drawdown", pct(s["max_dd"])), ("Sharpe ratio (vs T-bills)", f"{s['sharpe']:.2f}"),
                ("Best period", pct(s["best"])), ("Worst period", pct(s["worst"])),
                ("Equity volatility vs S&P 500", f"{volm():.2f}×"), ("Long-run expected real return", pct(PF.expected_real_return(mix())))]
        if fe:
            for k, v in fe["betas"].items():
                rows.append((f"{fe['model']}: {k} beta", f"{v:.2f}"))
            if fe.get("alpha_ann") is not None:
                rows.append(("Alpha (annualized)", pct(fe["alpha_ann"])))
            rows.append(("R²", f"{fe['r2']:.2f}"))
        contrib = sorted(s["contrib"].items(), key=lambda kv: -abs(kv[1]))[:4]
        return ui.div(ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(b_, class_="num")) for a, b_ in rows], class_="formal"),
                      ui.div("Biggest contributors", class_="sidebar-section-title mt-2"),
                      *[ui.span(f"{t}: {v * 100:+.1f} pts", class_="pill " + ("good" if v >= 0 else "bad")) for t, v in contrib],
                      ui.p("Fama-French betas appear once WRDS factors are cached (scripts/fetch_wrds_data.py).", class_="note") if D.load_ff_factors() is None else None)

    @render_plotly
    def pf_mc():
        p = prof()
        mc, school_n = baseline_mc()
        ages = p["age"] + mc["years"]
        fig = go.Figure()
        for lo, hi, a in [(10, 90, 0.10), (25, 75, 0.20)]:
            fig.add_trace(go.Scatter(x=ages, y=mc["pct"][hi], line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=ages, y=mc["pct"][lo], fill="tonexty", fillcolor=f"rgba(22,96,176,{a + 0.05})", line=dict(width=0), name=f"{lo}th-{hi}th percentile"))
        fig.add_trace(go.Scatter(x=ages, y=mc["pct"][50], line=dict(color=NAVY, width=3), name="Median", hovertemplate="Age %{x}: %{y:$,.0f}<extra></extra>"))
        fig.add_vline(x=p["age"] + school_n, line_dash="dot", line_color=GOLD, annotation_text="Graduation")
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Invested net worth (today's $)")
        fig.update_xaxes(title="Age")
        return style(fig, 380)

    @render.ui
    def pf_mc_note():
        p = prof()
        mc, _ = baseline_mc()
        i35 = min(len(mc["years"]) - 1, max(0, 35 - p["age"]))
        p_m = (mc["paths"][:, -1] >= 1_000_000).mean()
        return ui.div(ui.span(f"Median at 35: {money(mc['pct'][50][i35])}", class_="pill"),
                      ui.span(f"Median at {p['retire_age']}: {money(mc['pct'][50][-1])}", class_="pill"),
                      ui.span(f"Chance of $1M+ (today's $) by {p['retire_age']}: {p_m:.0%}", class_="pill good"))

    # ==================================================================================
    # MODULE 3: LIFE EVENTS
    # ==================================================================================
    @reactive.calc
    def ev_spec():
        p = prof()
        student, on_phd = p["status"] != "postdoc", C.phd_track(p)
        ev = {}
        if student and input.ev_extra():
            ev["extra_year"] = {"years": input.ev_extra_n()}
        if on_phd and input.ev_gap():
            ev["funding_gap"] = {"year": input.ev_gap_y(), "months": input.ev_gap_m()}
        if p["status"] == "phd" and input.ev_quit():
            ev["quit"] = {"year": input.ev_quit_y()}
        if student and input.ev_intern():
            ev["internship"] = {"year": input.ev_intern_y(), "amount": input.ev_intern_amt() or 0}
        if input.ev_bonus():
            ev["bonus"] = {"amount": input.ev_bonus_amt() or 0}
        if input.ev_layoff():
            ev["layoff"] = {"years_after": input.ev_layoff_y(), "months": input.ev_layoff_m()}
        if p["residency"] == "intl" and input.ev_visa():
            ev["visa_gap"] = {"months": input.ev_visa_m()}
        if input.ev_random():
            ev["random_layoffs"] = {"prob": input.ev_random_p()}
        if input.ev_child():
            ev["child"] = {"year": input.ev_child_y(), "cost": input.ev_child_cost() or 0, "years": input.ev_child_n()}
        if input.ev_med():
            ev["medical"] = {"year": input.ev_med_y(), "cost": input.ev_med_cost() or 0}
        if input.ev_inherit():
            ev["inherit"] = {"year": input.ev_inh_y(), "amount": input.ev_inh_amt() or 0}
        if input.ev_crash():
            ev["crash"] = {"name": input.ev_crash_name(), "offset": input.ev_crash_off()}
        return ev

    @reactive.calc
    def ev_run():
        return E.run(prof(), sel(), cf(), mix(), ev_spec(), start_wealth(), vol_mult=volm())

    @render.ui
    def ev_stats():
        p = prof()
        r = ev_run()
        b, s = r["base"], r["scen"]
        i35 = min(len(b["years"]) - 1, max(0, 35 - p["age"]))
        i45 = min(len(b["years"]) - 1, max(0, 45 - p["age"]))
        pb = (b["paths"][:, i45] >= 250_000).mean()
        ps = (s["paths"][:, i45] >= 250_000).mean()
        return ui.layout_columns(
            ui.value_box("Median at 35", money(s["pct"][50][i35]), f"baseline {money(b['pct'][50][i35])}", showcase=icon("hourglass-split"), showcase_layout="top right"),
            ui.value_box("Median at 45", money(s["pct"][50][i45]), f"baseline {money(b['pct'][50][i45])}", showcase=icon("calendar3"), showcase_layout="top right", class_="vb-gold"),
            ui.value_box(f"Retirement median ({p['retire_age']})", money(s["pct"][50][-1]), f"baseline {money(b['pct'][50][-1])}", showcase=icon("flag"), showcase_layout="top right", class_="vb-teal"),
            ui.value_box("Chance of $250K by 45", f"{ps:.0%}", f"baseline {pb:.0%} ({(ps - pb) * 100:+.0f} pts)", showcase=icon("speedometer2"), showcase_layout="top right",
                         class_="vb-burgundy" if ps < pb else "vb-sage"))

    @render_plotly
    def ev_fan():
        p = prof()
        r = ev_run()
        fig = go.Figure()
        ages = p["age"] + r["scen"]["years"]
        for lo, hi, a in [(10, 90, 0.10), (25, 75, 0.20)]:
            fig.add_trace(go.Scatter(x=ages, y=r["scen"]["pct"][hi], line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=ages, y=r["scen"]["pct"][lo], fill="tonexty", fillcolor=f"rgba(178,59,59,{a})", line=dict(width=0), name=f"Scenario {lo}-{hi}th"))
        fig.add_trace(go.Scatter(x=ages, y=r["scen"]["pct"][50], name="Scenario median", line=dict(color=BURG, width=3)))
        fig.add_trace(go.Scatter(x=p["age"] + r["base"]["years"], y=r["base"]["pct"][50], name="Baseline median", line=dict(color=NAVY, width=2, dash="dash")))
        fig.add_vline(x=p["age"] + r["ev_school_n"], line_dash="dot", line_color=GOLD, annotation_text="Graduation")
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Invested net worth (today's $)")
        fig.update_xaxes(title="Age")
        return style(fig, 400)

    @render.ui
    def ev_log():
        log = ev_run()["log"]
        return ui.div(*[ui.span(x, class_="pill") for x in log], class_="mt-2") if log else ui.p("No events selected.", class_="note")

    @render_plotly
    def ev_income():
        p = prof()
        r = ev_run()
        ages = p["age"] + np.arange(len(r["income"]))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ages, y=r["income"], name="Baseline", line=dict(color=NAVY, width=2)))
        fig.add_trace(go.Scatter(x=ages, y=r["ev_income"], name="Scenario", line=dict(color=BURG, width=2, dash="dot")))
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        fig.update_xaxes(title="Age", range=[p["age"], p["age"] + 25])
        return style(fig, 300)

    @render_plotly
    def ev_seq():
        d = E.sequence_demo(mix(), prof())
        fig = go.Figure()
        for k, col, lab in [("early", TEAL, "Crash in year 1"), ("late", BURG, "Crash 3 years before goal")]:
            fig.add_trace(go.Scatter(x=d[k]["years"], y=d[k]["pct"][50], name=lab, line=dict(color=col, width=2.5)))
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        fig.update_xaxes(title="Years of saving $1,500/month")
        return style(fig, 300)

    # ==================================================================================
    # MODULE 4: BUDGET, TAX & GOALS
    # ==================================================================================
    @render.text
    def bg_vb_th():
        return money(cf()["take_home"])

    @render.text
    def bg_vb_th_sub():
        return f"from {money(cf()['tax']['gross'] / 12)} gross"

    @render.text
    def bg_vb_sp():
        return money(cf()["spend"] + cf()["loan_pay"])

    @render.text
    def bg_vb_sp_sub():
        return f"{cf()['spend'] / max(cf()['take_home'], 1):.0%} of take-home"

    @render.text
    def bg_vb_sur():
        return money(cf()["surplus"])

    @render.text
    def bg_vb_sur_sub():
        return f"savings rate {cf()['savings_rate']:.0%}"

    @render.text
    def bg_vb_tax():
        return money(cf()["tax"]["total"])

    @render.text
    def bg_vb_tax_sub():
        t = cf()["tax"]
        return f"{t['effective']:.1%} effective" + (f" · {money(t['quarterly'])}/quarter est." if t["needs_estimates"] else "")

    @render.ui
    def bg_trim_note():
        base = B.cash_flow(prof())
        d = cf()["surplus"] - base["surplus"]
        return ui.p(f"These changes free up {money(d)}/month ({money(d * 12)}/year).", class_="note") if abs(d) > 1 else ui.p("Move the sliders to test changes.", class_="note")

    @render_plotly
    def bg_sankey():
        p, c = prof(), cf()
        t = c["tax"]
        inc = [("Stipend (fellowship)", t["fellowship"] / 12), ("Stipend / TA-RA wages", (t["wages"] - p.get("summer_income", 0)) / 12),
               ("Summer funding", p.get("summer_income", 0) / 12), ("Side income", t["side"] / 12), ("New loans", c["borrow_m"])]
        inc = [(k, v) for k, v in inc if v > 1]
        taxes = [("Federal income tax", t["federal"] / 12), (f"State tax ({t['state_code']})", t["state"] / 12), ("FICA / SE tax", (t["fica"] + t["se_tax"]) / 12)]
        spend = [(lab, c["exp"][k]) for k, lab, _ in B.EXPENSES if c["exp"][k] > 1] + ([("Loan payments", c["loan_pay"])] if c["loan_pay"] else []) + \
                ([("Tuition", c["tuition_m"])] if c["tuition_m"] else [])
        saves = [(s["step"], s["monthly"]) for s in c["steps"] if s["monthly"] > 1]
        nodes = [k for k, _ in inc] + ["Income", "Taxes", "Living costs", "Saving & debt payoff"] + [k for k, v in taxes if v > 1] + [k for k, _ in spend] + [k for k, _ in saves]
        nodes = list(dict.fromkeys(nodes))
        ix = {n: i for i, n in enumerate(nodes)}
        src, tgt, val = [], [], []

        def link(a, b_, v):
            if v > 1:
                src.append(ix[a])
                tgt.append(ix[b_])
                val.append(v)
        for k, v in inc:
            link(k, "Income", v)
        link("Income", "Taxes", t["total"] / 12)
        link("Income", "Living costs", sum(v for _, v in spend))
        link("Income", "Saving & debt payoff", max(0, c["surplus"]))
        for k, v in taxes:
            link("Taxes", k, v)
        for k, v in spend:
            link("Living costs", k, v)
        for k, v in saves:
            link("Saving & debt payoff", k, v)
        col = {"Income": NAVY, "Taxes": SLATE, "Living costs": "#5B9BD5", "Saving & debt payoff": TEAL}
        fig = go.Figure(go.Sankey(node=dict(label=nodes, pad=12, thickness=14, line=dict(width=0),
                                            color=[col.get(n, "#A9C9EC") for n in nodes]),
                                  link=dict(source=src, target=tgt, value=val, color="rgba(47,128,209,0.22)",
                                            hovertemplate="%{source.label} → %{target.label}: $%{value:,.0f}/mo<extra></extra>"),
                                  valueformat="$,.0f"))
        return style(fig, 440, legend=False)

    @render_plotly
    def bg_mix():
        c = cf()
        th = c["take_home"]
        g = c["groups"]
        actual = [g.get("Needs", 0) + c["loan_pay"], g.get("Wants", 0), max(0, c["surplus"]) + g.get("Career", 0)]
        target = [0.5 * th, 0.3 * th, 0.2 * th]
        labs = ["Needs", "Wants", "Saving & career"]
        fig = go.Figure([go.Bar(name="You", x=labs, y=actual, marker_color=NAVY, text=[money(v) for v in actual], textposition="outside"),
                         go.Bar(name="50/30/20 guide", x=labs, y=target, marker_color=GOLD, opacity=0.6)])
        fig.update_layout(barmode="group")
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        return style(fig, 320)

    @render.ui
    def bg_waterfall():
        c = cf()
        rows = [ui.div(ui.div(ui.tags.b(s["step"]), ui.div(s["note"], class_="note")), ui.div(money(s["monthly"]) + "/mo", class_="amt"), class_="wf")
                for s in c["steps"] if s["monthly"] > 1 or s["account"] in ("roth",)]
        if c["surplus"] < 0:
            rows.insert(0, ui.div(f"Monthly shortfall of {money(-c['surplus'])}: trim spending or add income before saving.", class_="callout"))
        return ui.div(*rows)

    @render.ui
    def bg_tax():
        t = cf()["tax"]
        rows = [("Fellowship income", t["fellowship"]), ("Wages (TA/RA + summer)", t["wages"]), ("Side income", t["side"]),
                ("Standard deduction", -t["std"]), ("Federal income tax", t["federal"]), (f"State income tax ({t['state_code']})", t["state"]),
                ("FICA / self-employment", t["fica"] + t["se_tax"]), ("Total tax", t["total"])]
        flags = [ui.span(f"Federal bracket {t['marginal']:.0%}", class_="pill"), ui.span(f"Effective {t['effective']:.1%}", class_="pill")]
        if t["needs_estimates"]:
            flags.append(ui.span(f"Quarterly estimates ≈ {money(t['quarterly'])}", class_="pill warn"))
        if t["nra"]:
            flags.append(ui.span("Nonresident alien rules applied", class_="pill warn"))
        rules = D.rules()["student_rules"]
        return ui.div(ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(money(b_), class_="num"), class_="hl" if a == "Total tax" else None) for a, b_ in rows if b_ or a == "Total tax"], class_="formal"),
                      ui.div(*flags, class_="mt-2"),
                      ui.accordion(*[ui.accordion_panel(r["rule"], ui.p(r["detail"], class_="note")) for r in rules], open=False, class_="mt-2"))

    @render.ui
    def bg_goals():
        p, c = prof(), cf()
        out = []
        for g in B.goal_status(p, c):
            fixes = []
            if not g["on_track"]:
                fixes.append(f"save {money(g['gap_m'])}/mo more")
                if math.isfinite(g["months_late"]):
                    fixes.append(f"or move the date ~{math.ceil(g['months_late'])} months later")
                if p["dining"] + p["subscriptions"] > 0:
                    fixes.append(f"or trim discretionary spending {min(100, g['gap_m'] / max(c['groups'].get('Wants', 1), 1) * 100):.0f}%")
            out.append(ui.div(
                ui.div(ui.tags.b(g["label"]), ui.span("On track" if g["on_track"] else "Behind", class_="pill float-end " + ("good" if g["on_track"] else "warn"))),
                ui.div(ui.div(style=f"width:{g['pct'] * 100:.0f}%"), class_="bar" + ("" if g["on_track"] else " behind")),
                ui.div(f"{money(g['projected'])} of {money(g['amount'])} by {g['year']} ({g['pct']:.0%}) · needs {money(g['need_m'])}/mo, plan gives {money(g['plan_m'])}/mo", class_="note"),
                ui.div("To close the gap: " + ", ".join(fixes), class_="note") if fixes else None, class_="goal"))
        ef = c["ef_months_have"]
        out.insert(0, ui.div(ui.div(ui.tags.b("Emergency fund"), ui.span(f"{ef:.1f} of {p['ef_months']} months", class_="pill float-end " + ("good" if ef >= p["ef_months"] else "warn"))),
                             ui.div(ui.div(style=f"width:{min(100, ef / p['ef_months'] * 100):.0f}%"), class_="bar" + ("" if ef >= p["ef_months"] else " behind")), class_="goal"))
        return ui.div(*out)

    @render.ui
    def bg_loans():
        p = prof()
        ln = B.loan_projection(p)
        R = D.rules()["loans"]
        m0, i0 = B.debt_payoff(p["cc_debt"], p["cc_rate"], max(25, p["cc_debt"] * 0.03))
        m1, i1 = B.debt_payoff(p["cc_debt"], p["cc_rate"], max(25, p["cc_debt"] * 0.03) + p["cc_debt"] / 6 + input.extra_cc())
        rows = [("Balance at graduation (est.)", money(ln["balance_at_grad"])), ("Interest accrued while in school", money(ln["interest_accrued"])),
                ("Payment over 10 years (~7%)", money(ln["payment_10y"]) + "/mo"),
                ("2026-27 grad unsubsidized rate", f"{R['grad_unsub_rate_2026_27'] * 100:.2f}% + {R['origination_fee'] * 100:.3f}% fee"),
                ("Federal grad loan limits", f"{money(R['annual_limit_grad'])}/yr · {money(R['aggregate_limit_grad'])} lifetime")]
        items = [ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(b_, class_="num")) for a, b_ in rows], class_="formal"),
                 ui.div(f"Grad PLUS: {R['grad_plus']}", class_="callout")]
        if p["cc_debt"] > 0:
            items.append(ui.p(f"Credit card: minimum payments take {m0} months ({money(i0)} interest); the plan clears it in {m1} months ({money(i1)}).", class_="note"))
        if ln["cap_warning"]:
            items.append(ui.span("Planned borrowing exceeds the $100,000 graduate cap", class_="pill bad"))
        return ui.div(*items)

    @render.ui
    def bg_location():
        rows = [("Roth IRA", "Highest-growth holdings (small/value, international, your tilts). Growth is tax-free and you're in a low bracket now."),
                ("403(b) / 457(b) (if offered)", "Bonds and bond funds: their interest would be taxed yearly in a brokerage account. 457(b) money can be withdrawn without penalty after you leave the job."),
                ("Taxable brokerage", "Broad, tax-efficient stock index ETFs (VTI/VOO/VEA). Hold over a year for long-term capital-gains rates."),
                ("High-yield savings / T-bills", "Emergency fund and goal money due within ~3 years (laptop, moving costs)."),
                ("Avoid", "Holding taxable bonds in a brokerage while you have open Roth space; withdrawing Roth earnings before 59½.")]
        return ui.tags.table(*[ui.tags.tr(ui.tags.td(ui.tags.b(a)), ui.tags.td(b_)) for a, b_ in rows], class_="formal")

    # ==================================================================================
    # WHERE TO LIVE
    # ==================================================================================
    @reactive.calc
    def loc_df():
        data_tick()
        w = {"income": input.w_income(), "housing": input.w_housing(), "career": input.w_career(), "cost": input.w_cost()}
        return L.score_metros(prof(), input.loc_sector(), w)

    @render.ui
    def loc_note():
        src = C.wage_factor(prof()["target_metro"], prof()["field"], input.loc_sector())[1]
        basis = "NSF SED starting salary for new PhDs" if C.phd_track(prof()) else "your expected master's salary"
        return ui.p(f"Pay basis: {basis} × metro factor ({'BLS OEWS metro wages' if 'BLS' in src else 'BEA price level until you refresh BLS wages'}). "
                    "Taxes: federal + state (local taxes excluded). Housing: median list price, 10% down at the current Freddie Mac rate.", class_="note mt-2")

    @render_plotly
    def loc_map():
        df = loc_df()
        p = prof()
        fig = go.Figure(go.Scattermap(
            lat=df.lat, lon=df.lon, mode="markers",
            marker=dict(size=(df["Real after-tax"] / df["Real after-tax"].max()) ** 2 * 34 + 6, color=df.Score,
                        colorscale=[[0, "#DCE8F6"], [0.5, "#5B9BD5"], [1, "#0A3363"]], cmin=0, cmax=100, colorbar=dict(title="Score"), opacity=0.85),
            text=df.Metro, customdata=np.stack([df.Salary, df["Real after-tax"], df["Median list price"].fillna(0), df.Score], axis=1),
            hovertemplate="<b>%{text}</b><br>Est. salary %{customdata[0]:$,.0f}<br>Real after-tax %{customdata[1]:$,.0f}<br>"
                          "Median list %{customdata[2]:$,.0f}<br>Score %{customdata[3]:.0f}<extra></extra>"))
        for mid, col, lab in [(p["univ_metro"], TEAL, "University"), (p["target_metro"], BURG, "Target")]:
            r = METROS.set_index("id").loc[mid]
            fig.add_trace(go.Scattermap(lat=[r.lat], lon=[r.lon], mode="markers", marker=dict(size=13, color=col), text=[f"{lab}: {r['name']}"],
                                        hovertemplate="%{text}<extra></extra>", showlegend=False))
        fig.update_layout(map=dict(style=input.basemap(), center=dict(lat=38.5, lon=-96), zoom=2.9), margin=dict(l=0, r=0, t=0, b=0), height=460, showlegend=False)
        return fig

    @render.ui
    def loc_table():
        df = loc_df().head(15)
        tgt = prof()["target_metro"]
        rows = [ui.tags.tr(ui.tags.td(f"{i + 1}"), ui.tags.td(ui.tags.b(r.Metro) if r.id == tgt else r.Metro), ui.tags.td(money(r.Salary), class_="num"),
                           ui.tags.td(money(r["Real after-tax"]), class_="num"), ui.tags.td(money(r["Median list price"]) if pd.notna(r["Median list price"]) else "–", class_="num"),
                           ui.tags.td(pct(r["Housing burden"], 0) if pd.notna(r["Housing burden"]) else "–", class_="num"), ui.tags.td(f"{r.Score:.0f}", class_="num"),
                           class_="hl" if r.id == tgt else None) for i, (_, r) in enumerate(df.iterrows())]
        return ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("#"), ui.tags.th("Metro"), ui.tags.th("Est. salary", class_="num"), ui.tags.th("Real after-tax", class_="num"),
                                                      ui.tags.th("Median list", class_="num"), ui.tags.th("Mortgage / pay", class_="num"), ui.tags.th("Score", class_="num"))),
                             ui.tags.tbody(*rows), class_="formal")

    @render.ui
    def loc_detail_card():
        df = loc_df().set_index("id")
        r = df.loc[input.loc_detail()]
        return ui.div(ui.h4(r.Metro), ui.p(ui.tags.b("Key industries: "), r.Hubs), ui.p(ui.tags.b("Universities: "), r.Universities, class_="note"),
                      ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(b_, class_="num")) for a, b_ in [
                          ("Estimated starting salary", money(r.Salary)), ("State income tax", money(r["State tax"])),
                          ("After-tax pay", money(r["After tax"])), ("Price level (U.S. = 100)", f"{r.RPP:.1f}"),
                          ("Cost-adjusted after-tax pay", money(r["Real after-tax"])),
                          ("Median list price (Sep 2026)", money(r["Median list price"]) if pd.notna(r["Median list price"]) else "run FRED refresh"),
                          ("List price, year over year", f"{r['List YoY %']:+.1f}%" if pd.notna(r["List YoY %"]) else "–"),
                          ("Field match", f"{int(r['Hub match'])} keyword(s)")]], class_="formal"),
                      ui.p(r.wage_source, class_="note mt-1"))

    @render_plotly
    def loc_compare():
        df = loc_df().set_index("id")
        p = prof()
        ids = list(dict.fromkeys([p["univ_metro"], p["target_metro"], input.loc_detail()]))
        fig = go.Figure()
        for k, col in [("Salary", SLATE), ("After tax", NAVY), ("Real after-tax", GOLD)]:
            fig.add_trace(go.Bar(name=k, x=[df.loc[i, "Metro"].split(",")[0] for i in ids], y=[df.loc[i, k] for i in ids], marker_color=col))
        fig.update_yaxes(tickprefix="$", tickformat="~s")
        return style(fig, 260)

    @reactive.effect
    @reactive.event(input.loc_set_target)
    def _set_target():
        ui.update_select("target_metro", selected=input.loc_detail())
        p = dict(prof())
        p["target_metro"] = input.loc_detail()
        p["target_sector"] = input.loc_sector() if C.phd_track(p) or input.loc_sector() in MS_SECTORS else p["target_sector"]
        ui.update_select("target_sector", selected=p["target_sector"])
        ui.update_select("target_sector_ms", selected=p["target_sector"] if p["target_sector"] in MS_SECTORS else "industry")
        activate(p, f"Target city set to {METRO_CHOICES[input.loc_detail()]}. Career paths, goals and housing updated.")

    # ==================================================================================
    # HOMES & RENTALS (same page as Where to Live; follows the focus city)
    # ==================================================================================
    @render.ui
    def h_section():
        r = METROS.set_index("id").loc[input.loc_detail()]
        return ui.div(ui.span("Homes & rentals", class_="module-tag"), ui.h3(f"Living in {r['name']}"),
                      ui.p("Typical rents and prices for every neighborhood (no key needed), optional live listings, the local market and rent vs. buy. "
                           "Change the focus city under Your priorities.", class_="lede"),
                      class_="section-head")

    def focus_metro():
        return METROS.set_index("id").loc[input.loc_detail()]

    @reactive.calc
    def hood():
        """ZIP-code neighborhoods around the focus city with a comparable price (works with no API key)."""
        r = focus_metro()
        return L.neighborhoods(r.lat, r.lon, input.h_mode(), int(input.h_beds() or 0), input.h_max() or None, float(input.h_radius()))

    @reactive.effect
    @reactive.event(input.loc_detail, input.h_mode)
    def _h_defaults():
        r = focus_metro()
        with reactive.isolate():
            z = L.neighborhoods(r.lat, r.lon, input.h_mode(), int(input.h_beds() or 0), None, float(input.h_radius()))
        if pd.notna(r.list_price):
            ui.update_numeric("rvb_price", value=int(round(r.list_price, -3)))
        if input.h_mode() == "buy":
            ui.update_numeric("h_max", value=int(round(r.list_price * 1.1, -4)) if pd.notna(r.list_price) else 500000)
        else:  # start at the city's median neighborhood rent, so the map shows a mix of in- and over-budget areas
            ui.update_numeric("h_max", value=int(round(z.price.median(), -1)) if len(z) else int(round(2200 * r.rpp / 100, -1)))
        zori = z.zori.dropna()
        ui.update_numeric("rvb_rent", value=int(round(zori.median(), -1)) if len(zori) else int(round(2200 * r.rpp / 100, -1)))
        # show listings saved from an earlier RentCast search for this city, if any (no API call)
        city = r["name"].split(",")[0].split("-")[0].strip()
        listings_state.set(D.get_listings(city, r.state, input.h_mode(), None, None, None))

    @reactive.effect
    @reactive.event(input.h_fetch)
    def _h_fetch():
        r = focus_metro()
        key = D.rentcast_key(input.h_key())
        if not key:
            listings_state.set(([], "no key"))
            ui.notification_show("Add a free RentCast API key (app.rentcast.io) to see individual listings. The neighborhood prices on the map need no key.",
                                 type="warning", duration=7)
            return
        city = r["name"].split(",")[0].split("-")[0].strip()
        with ui.Progress(min=0, max=1) as pr:
            pr.set(0.3, message=f"Fetching live {'rentals' if input.h_mode() == 'rent' else 'homes for sale'} in {city} from RentCast…")
            listings_state.set(D.get_listings(city, r.state, input.h_mode(), key, None, None, force=True))
            pr.set(1)

    def live_items() -> list[dict]:
        items, _ = listings_state()
        return D._filter_listings(items, input.h_max() or None, int(input.h_beds() or 0) or None)

    @render.ui
    def h_status():
        items, msg = listings_state()
        if msg == "no key":
            return ui.p("The map already shows typical prices by neighborhood (no key needed). To add individual homes for rent or sale, paste a free "
                        "RentCast key from app.rentcast.io, or set RENTCAST_API_KEY before starting the app.", class_="note mt-2")
        if not items:
            return ui.p(f"No live listings: {msg}. The neighborhood prices on the map still work.", class_="note mt-2")
        shown = live_items()
        return ui.p(f"{len(shown)} of {len(items)} live listings match your filters ({msg}).", class_="note mt-2")

    @render.ui
    def h_links():
        r = focus_metro()
        return ui.div(*[ui.tags.a(n, href=u, target="_blank", class_="link-btn") for n, u in L.listing_links(r["name"], r.state, input.h_mode(), input.h_max())],
                      ui.tags.a("Google Maps", href=f"https://www.google.com/maps/search/{r['name'].replace(' ', '+')}", target="_blank", class_="link-btn"))

    def price_label() -> str:
        b = int(min(max(input.h_beds() or 0, 0), 4))
        return ("typical list price" if input.h_mode() == "buy" else f"typical {'studio' if b == 0 else f'{b}-bed'} rent")

    @render.ui
    def h_summary():
        z = hood()
        if not len(z):
            return ui.p("No neighborhood data within this distance; widen the search.", class_="note")
        n_in = int(z.in_budget.sum())
        cheapest = z.loc[z.price.idxmin()]
        return ui.div(
            ui.span(f"{n_in} of {len(z)} neighborhoods", class_="pill good" if n_in else "pill warn"),
            ui.span(f"within {input.h_radius()} miles have a {price_label()} at or under {money(input.h_max() or 0)}", class_="note"),
            ui.span(f"Lowest: {money(cheapest.price)} in {cheapest.zip} ({cheapest.city}, {cheapest.miles:.1f} mi)", class_="pill ms-2"),
            class_="d-flex flex-wrap align-items-center gap-1 mb-2")

    @render_plotly
    def h_map():
        r = focus_metro()
        z = hood()
        items = live_items()
        fig = go.Figure()
        if len(z):
            ins, outs = z[z.in_budget], z[~z.in_budget]
            hover = ("<b>%{customdata[0]} · %{customdata[1]}</b><br>%{customdata[2]}: $%{customdata[3]:,.0f}<br>"
                     "Zillow typical rent: %{customdata[4]}<br>Zillow typical home value: %{customdata[5]}<br>"
                     "Active listings: %{customdata[6]} · median list %{customdata[7]}<br>%{customdata[8]:.1f} mi from downtown<extra></extra>")

            def fmt(v):
                return "–" if pd.isna(v) else f"${v:,.0f}"

            def cd(df):
                return np.stack([df.zip, df.city, df.price_src, df.price, df.zori.map(fmt), df.zhvi.map(fmt),
                                 df.rdc_active_listings.map(lambda v: "–" if pd.isna(v) else f"{v:.0f}"), df.rdc_median_list.map(fmt), df.miles], axis=1)
            if len(outs):
                fig.add_trace(go.Scattermap(lat=outs.lat, lon=outs.lon, mode="markers", name="Over budget",
                                            marker=dict(size=11, color="#C8D2DD", opacity=0.55), customdata=cd(outs), hovertemplate=hover))
            if len(ins):
                size = 10 + 14 * np.sqrt(ins.rdc_active_listings.fillna(0) / max(z.rdc_active_listings.max(), 1))
                fig.add_trace(go.Scattermap(lat=ins.lat, lon=ins.lon, mode="markers", name="Within budget",
                                            marker=dict(size=size, color=ins.price, colorscale=[[0, "#D6E6F7"], [0.5, "#1A5FA8"], [1, "#0A3363"]],
                                                        cmin=float(z.price.min()), cmax=float(z.price.max()), opacity=0.9,
                                                        colorbar=dict(title=dict(text=price_label().replace("typical ", "").capitalize(), side="right"),
                                                                      tickprefix="$", tickformat="~s", len=0.7, thickness=12)),
                                            customdata=cd(ins), hovertemplate=hover))
        if items:
            df = pd.DataFrame(items)
            fig.add_trace(go.Scattermap(lat=df.lat, lon=df.lon, mode="markers", name="Live listing (RentCast)", marker=dict(size=9, color=BURG),
                                        text=df.address, customdata=np.stack([df.price, df.beds.fillna(0), df.sqft.fillna(0)], axis=1),
                                        hovertemplate="<b>%{text}</b><br>$%{customdata[0]:,.0f} · %{customdata[1]:.0f} bd · %{customdata[2]:,.0f} sqft<extra>Live listing</extra>"))
        fig.add_trace(go.Scattermap(lat=[r.lat], lon=[r.lon], mode="markers", name="Downtown", marker=dict(size=15, color=NAVY, symbol="circle"),
                                    text=[r["name"] + " (downtown)"], hovertemplate="%{text}<extra></extra>"))
        zoom = 11.2 - np.log2(max(float(input.h_radius()), 2) / 3)
        fig.update_layout(map=dict(style=input.basemap(), center=dict(lat=r.lat, lon=r.lon), zoom=zoom), margin=dict(l=0, r=0, t=0, b=0), height=470,
                          showlegend=True, legend=dict(orientation="h", y=0.01, x=0.01, bgcolor="rgba(255,255,255,0.85)", font=dict(size=11)))
        return fig

    @render.ui
    def h_table():
        z = hood()
        mode = input.h_mode()
        out = []
        items = live_items()
        if items:
            df = pd.DataFrame(items).sort_values("price").head(12)
            rows = [ui.tags.tr(ui.tags.td(ui.tags.a(x.address, href=f"https://www.google.com/search?q={x.address.replace(' ', '+')}", target="_blank")),
                               ui.tags.td(money(x.price), class_="num"), ui.tags.td(f"{x.beds or '–'}", class_="num"), ui.tags.td(f"{x.baths or '–'}", class_="num"),
                               ui.tags.td(f"{x.sqft:,.0f}" if x.sqft == x.sqft and x.sqft else "–", class_="num"), ui.tags.td(x.type or "")) for x in df.itertuples()]
            out += [ui.h5("Live listings (RentCast)", class_="mt-3"),
                    ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h, class_="num" if h in ("Price", "Beds", "Baths", "Sq ft") else None)
                                                             for h in ["Address", "Price", "Beds", "Baths", "Sq ft", "Type"]])),
                                  ui.tags.tbody(*rows), class_="formal")]
        if len(z):
            pick = z[z.in_budget].head(15)
            title = "Neighborhoods in your budget, closest first"
            if not len(pick):
                pick, title = z.sort_values("price").head(10), "Nothing under your budget here. The most affordable neighborhoods:"
            zillow_col = "Zillow value" if mode == "buy" else "Zillow rent"

            def fmt(v):
                return "–" if pd.isna(v) else money(v)
            rows = [ui.tags.tr(ui.tags.td(ui.tags.b(x.zip), f" · {x.city}"), ui.tags.td(f"{x.miles:.1f}", class_="num"),
                               ui.tags.td(money(x.price), class_="num"), ui.tags.td(fmt(x.zhvi if mode == "buy" else x.zori), class_="num"),
                               ui.tags.td("–" if pd.isna(x.rdc_active_listings) else f"{x.rdc_active_listings:.0f}", class_="num"),
                               ui.tags.td("–" if pd.isna(x.rdc_dom) else f"{x.rdc_dom:.0f}", class_="num"),
                               ui.tags.td(*[ui.tags.a(n, href=u, target="_blank", class_="me-2") for n, u in L.zip_links(x.zip, mode)]))
                    for x in pick.itertuples()]
            meta = D.zip_housing_meta()
            out += [ui.h5(title, class_="mt-3"),
                    ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("ZIP · area"), ui.tags.th("Miles", class_="num"), ui.tags.th(price_label().capitalize(), class_="num"),
                                                           ui.tags.th(zillow_col, class_="num"), ui.tags.th("Active listings", class_="num"),
                                                           ui.tags.th("Days on market", class_="num"), ui.tags.th("See listings"))),
                                  ui.tags.tbody(*rows), class_="formal"),
                    ui.p(("Rent: HUD FY2026 Small Area Fair Market Rents (40th-percentile rent by ZIP and bedroom count; HUD caps some downtown ZIPs), "
                          "Zillow Observed Rent Index (Mar 2026)." if mode == "rent" else
                          "Price: Realtor.com median list price by ZIP (Mar 2026), Zillow Home Value Index (Mar 2026).")
                         + f" Active listings and days on market: Realtor.com, {meta['as_of']['realtor'].replace('2026-03', 'Mar 2026')}. "
                         "These are typical prices, not individual listings; the links open live listings for each ZIP.", class_="note mt-1")]
        return ui.div(*out)

    @render.ui
    def h_market():
        r = METROS.set_index("id").loc[input.loc_detail()]
        rate = D.rules()["housing"]["mortgage_rate_30y"]
        price = r.list_price
        items = [("Median list price (Realtor.com, Sep 2026)", money(price) if pd.notna(price) else "run FRED refresh"),
                 ("Change vs. a year ago", f"{r.list_yoy:+.1f}%" if pd.notna(r.list_yoy) else "–"),
                 ("Listings with a price cut", f"{r.price_cut_share:.1f}%" if pd.notna(r.price_cut_share) else "–"),
                 ("30-yr mortgage (Freddie Mac, Nov 5 2026)", f"{rate * 100:.2f}%"),
                 ("Monthly cost, 10% down, incl. tax & insurance", money(L.monthly_mortgage(price, 10, rate)) if pd.notna(price) else "–"),
                 ("Price level (BEA RPP 2024)", f"{r.rpp:.1f}")]
        z = L.neighborhoods(r.lat, r.lon, "rent", 1, None, 12)
        if len(z):
            hud1 = z.hud_1br.dropna()
            zori = z.zori.dropna()
            if len(hud1):
                items.append(("1-bed rent across neighborhoods (HUD FY2026, 12 mi)", f"{money(hud1.min())} – {money(hud1.max())}"))
            if len(zori):
                items.append(("Median typical rent (Zillow, Mar 2026)", money(zori.median())))
        return ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(b_, class_="num")) for a, b_ in items], class_="formal")

    @render_plotly
    def h_trend():
        data_tick()
        r = METROS.set_index("id").loc[input.loc_detail()]
        fh = D.load_fred_housing()
        fig = go.Figure()
        col = f"MEDLISPRI{r.cbsa}"
        if fh is not None and col in fh:
            s = fh[col].dropna()
            fig.add_trace(go.Scatter(x=s.index, y=s, name=f"{r['name']} median list price", line=dict(color=NAVY)))
            fig.update_yaxes(tickprefix="$", tickformat="~s")
        else:
            cs = D.case_shiller().loc["2000":]
            fig.add_trace(go.Scatter(x=cs.index, y=cs, name="U.S. national home prices (Case-Shiller)", line=dict(color=NAVY)))
            fig.update_yaxes(title="Index")
        return style(fig, 220)

    @reactive.calc
    def rvb():
        return L.rent_vs_buy(input.rvb_price() or 0, input.rvb_down() or 0, (input.rvb_rate() or 0) / 100, int(input.rvb_years() or 1),
                             input.rvb_tax() or 0, input.rvb_maint() or 0, input.rvb_app() or 0, input.rvb_rent() or 0,
                             input.rvb_rentg() or 0, input.rvb_ret() or 0)

    @render_plotly
    def h_rvb():
        df = rvb()
        fig = go.Figure([go.Bar(x=df.year, y=df["Buy minus rent"], marker_color=[SAGE if v >= 0 else BURG for v in df["Buy minus rent"]], name="Buy minus rent")])
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Wealth advantage of buying")
        fig.update_xaxes(title="Years after buying")
        return style(fig, 240, legend=False)

    @render.ui
    def h_rvb_note():
        df = rvb()
        be = df[df["Buy minus rent"] > 0]
        first = df.iloc[0]
        return ui.p(f"Owning costs about {money(first['Monthly owning cost'])}/mo vs. {money(first['Monthly rent'])} rent in year 1. "
                    + (f"Buying pulls ahead after {int(be.year.iloc[0])} years." if len(be) else "Renting stays ahead for the whole period: renting and investing the difference wins.")
                    + " Includes 3% buying and 6% selling costs.", class_="note")

    # ==================================================================================
    # NEWS
    # ==================================================================================
    @reactive.effect
    @reactive.event(input.news_refresh)
    def _news_refresh():
        news_tick.set(news_tick() + 1)

    def news_block(query: str):
        force = news_tick() > 0
        items, status = D.get_news(query, force=force)
        if not items:
            return ui.p(f"No headlines yet ({status}). Click 'Refresh headlines' while online.", class_="note")
        now = datetime.now().timestamp()

        def ago(ts):
            if not ts:
                return ""
            h = (now - ts) / 3600
            return f"{h:.0f}h ago" if h < 48 else f"{h / 24:.0f}d ago"
        return ui.div(*[ui.div(ui.tags.a(x["title"], href=x["link"], target="_blank"), ui.div(" · ".join(filter(None, [x["source"], ago(x["ts"])])), class_="news-meta"),
                               class_="news-item") for x in items[:8]],
                      ui.p(f"Query: “{query}” · {status}", class_="note mt-1"))

    @render.ui
    def news_field():
        p = prof()
        q = D.careers()["fields"][p["field"]]["news"] + (" academia faculty" if p["target_sector"] == "academe" else "")
        return news_block(q)

    @render.ui
    def news_city():
        p = prof()
        return news_block(f"{METRO_CHOICES[p['target_metro']].split(',')[0]} economy jobs housing")

    @render.ui
    def news_markets():
        tick = [t for t in weights() if D.ETFS.get(t, {}).get("group") in ("Sector", "Theme")]
        q = "stock market today" + (" " + " ".join(D.ETFS[t]["name"] for t in tick[:2]) + " stocks" if tick else "")
        return news_block(q)

    @render.ui
    def news_grad():
        return news_block("graduate students stipend OR \"student loans\" OR \"research funding\"")

    @render.ui
    def news_snapshot():
        data_tick()
        etf = D.load_etf_prices()
        cards = []
        if etf is not None:
            for t, lab in [("SPY", "S&P 500"), ("QQQ", "Nasdaq-100"), ("VEA", "Developed intl."), ("BND", "U.S. bonds"), ("GLD", "Gold")]:
                if t in etf:
                    s = etf[t].dropna()
                    d1 = s.iloc[-1] / s.iloc[-2] - 1
                    m1 = s.iloc[-1] / s.loc[s.index >= s.index[-1] - pd.DateOffset(months=1)].iloc[0] - 1
                    cards.append(ui.value_box(lab, f"{d1 * 100:+.2f}%", f"1 month {m1 * 100:+.1f}% · {s.index[-1]:%b %d}", class_="vb-teal" if d1 >= 0 else "vb-burgundy"))
        else:
            lr = D.longrun()
            cards.append(ui.value_box("S&P 500 (1 month)", f"{lr['stock'].iloc[-1] * 100:+.1f}%", f"{lr.index[-1]:%b %Y}; refresh market data for daily moves"))
        v = D.vix()
        b10 = pd.read_csv(D.BUNDLED / "bond-yields-us-10y.csv").iloc[-1]
        cards.append(ui.value_box("VIX (fear gauge)", f"{v.iloc[-1]:.1f}", f"as of {v.index[-1]:%b %d, %Y}", class_="vb-gold"))
        cards.append(ui.value_box("10-yr Treasury", f"{b10['Rate']:.2f}%", f"{b10['Date'][:7]}", class_="vb-sage"))
        return ui.layout_columns(*cards[:6])

    # ==================================================================================
    # TRAVEL & DEALS
    # ==================================================================================
    @reactive.calc
    def trip():
        req(input.tr_from() != input.tr_to())
        return T.trip_estimate(input.tr_from(), input.tr_to())

    @render.ui
    def tr_summary():
        t = trip()
        modes = [("Fly", t["fly_h"], "airplane")] + ([("Train", t["train_h"], "train-front")] if t["train_h"] else []) + ([("Drive", t["drive_h"], "car-front")] if t["drive_h"] else [])
        return ui.div(ui.layout_columns(
            ui.value_box("Distance", f"{t['miles']:,.0f} mi", f"{t['a']['airport']} → {t['b']['airport']}", showcase=icon("signpost-split"), showcase_layout="top right"),
            *[ui.value_box(m, f"{h:.1f} h", "door to door (est.)" + (" · recommended" if m.lower() == t["best"] else ""), showcase=icon(ic), showcase_layout="top right",
                           class_="vb-gold" if m.lower() == t["best"] else "") for m, h, ic in modes]),
            ui.p("Times are heuristics (airport time + cruise speed; Amtrak average speeds; driving at highway pace). "
                 + ("International trip: check visa rules and re-entry documents (I-20/DS-2019 travel signature)." if t["intl"] and prof()["residency"] == "intl" else ""), class_="note"))

    @render_plotly
    def tr_map():
        t = trip()
        lat = [t["a"]["lat"], t["b"]["lat"]]
        lon = [t["a"]["lon"], t["b"]["lon"]]
        fig = go.Figure(go.Scattermap(lat=lat, lon=lon, mode="lines+markers", line=dict(width=3, color=GOLD),
                                      marker=dict(size=11, color=NAVY), text=[input.tr_from(), input.tr_to()], hovertemplate="%{text}<extra></extra>"))
        span = max(abs(lat[0] - lat[1]), abs(lon[0] - lon[1]) * 0.6, 0.5)
        zoom = float(np.clip(np.log2(180 / span) - 0.6, 0.5, 9))
        fig.update_layout(map=dict(style=input.basemap(), center=dict(lat=sum(lat) / 2, lon=sum(lon) / 2), zoom=zoom),
                          height=280, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        return fig

    @render.ui
    def tr_links():
        t = trip()
        links = T.booking_links(input.tr_from(), input.tr_to(), input.tr_dep(), input.tr_ret(), int(input.tr_n() or 1))
        groups = {"flight": "Flights", "train": "Train & bus", "any": "Compare all modes", "stay": "Stay"}
        out = []
        for g, lab in groups.items():
            ls = [x for x in links if x[1] == g and (g != "train" or t["rail"] or not t["intl"])]
            if ls:
                out.append(ui.div(ui.div(lab, class_="sidebar-section-title"), *[ui.tags.a(n, href=u, target="_blank", class_="link-btn") for n, _, u in ls]))
        out.append(ui.p("Links open the booking sites with your route and dates pre-filled. Booking happens on their site; Athena Capital never handles payment.", class_="note"))
        return ui.div(*out)

    @render.ui
    def tr_budget():
        n = int(input.tr_n() or 1)
        fare = (input.tr_fare() or 0) * n
        lodge = (input.tr_nights() or 0) * (input.tr_hotel() or 0)
        meals = ((input.tr_nights() or 0) + 1) * (input.tr_meals() or 0) * n
        reg = input.tr_reg() or 0 if input.tr_purpose() == "Conference" else 0
        total = fare + lodge + meals + reg
        reimb = total * (input.tr_reimb() or 0) / 100 if input.tr_purpose() in ("Conference", "Interview") else 0
        oop = total - reimb
        months = max(1, (input.tr_dep() - date.today()).days // 30)
        rows = [("Transport", fare), ("Lodging", lodge), ("Meals", meals), ("Registration", reg), ("Total", total), ("Reimbursed", -reimb), ("Out of pocket", oop)]
        return ui.layout_columns(
            ui.tags.table(*[ui.tags.tr(ui.tags.td(a), ui.tags.td(money(b_), class_="num"), class_="hl" if a in ("Out of pocket",) else None) for a, b_ in rows if b_ or a in ("Total", "Out of pocket")], class_="formal"),
            ui.div(ui.div(f"Save {money(oop / months)}/month for {months} month(s)", class_="callout"),
                   ui.p(f"Your budget's travel line is {money(prof()['travel'])}/month. Keep receipts: university reimbursements usually need itemized receipts within 30-60 days.", class_="note"),
                   ui.p("Tip: ask your department or the conference about student travel grants before you book.", class_="note")),
            col_widths=(6, 6))

    @render.ui
    def deal_cards():
        cards = [{"name": input[f"card{i}_name"](), "rates": {cat: input[f"card{i}_{j}"]() or 0 for j, cat in enumerate(T.REWARD_CATS)}} for i in range(3)]
        res = T.card_optimizer(cf()["exp"], cards)
        tbl = res["table"]
        rows = [ui.tags.tr(ui.tags.td(r.Category), ui.tags.td(money(r["Monthly spend"]), class_="num"), ui.tags.td(r["Best card"]),
                           ui.tags.td(f"{r.Rate:.1f}%", class_="num"), ui.tags.td(money(r["Annual rewards"]), class_="num")) for _, r in tbl.iterrows()]
        best_single = max(res["single"].items(), key=lambda kv: kv[1]) if res["single"] else ("–", 0)
        return ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("Category"), ui.tags.th("Spend/mo", class_="num"), ui.tags.th("Use this card"),
                                                             ui.tags.th("Rate", class_="num"), ui.tags.th("Per year", class_="num"))), ui.tags.tbody(*rows), class_="formal mt-2"),
                      ui.div(ui.span(f"Optimized: {money(res['total'])}/yr", class_="pill good"),
                             ui.span(f"Best single card ({best_single[0]}): {money(best_single[1])}/yr", class_="pill"), class_="mt-2"),
                      ui.p("Spending comes from your Monthly spending inputs. Rewards only help if you pay the balance in full: a 23% APR erases years of 2% cash back.", class_="note"))

    @render.ui
    def deal_perks():
        groups = {}
        for g, name, desc, url in T.PERKS:
            groups.setdefault(g, []).append((name, desc, url))
        return ui.div(*[ui.div(ui.div(g, class_="sidebar-section-title mt-2"),
                               *[ui.div(ui.tags.a(n, href=u, target="_blank"), ui.div(d, class_="note"), class_="news-item") for n, d, u in items])
                        for g, items in groups.items()],
                      ui.p("Offers change often; terms and eligibility are set by each provider.", class_="note mt-2"))

    # ==================================================================================
    # REPORT & METHODS
    # ==================================================================================
    @render.ui
    def m_status():
        data_tick()
        st = D.data_status()
        return ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th("Source"), ui.tags.th("Status"))),
                             ui.tags.tbody(*[ui.tags.tr(ui.tags.td(s.name), ui.tags.td(ui.span("●", style=f"color:{SAGE if s.ok else WARN}"), " ", s.status)) for s in st]),
                             class_="formal")

    @render.ui
    def m_methods():
        ref_src = [D.ref("metros")["_sources"], D.careers()["_sources"]]
        r = D.rules()
        src = [
            "<b>Market history (non-WRDS):</b> Robert J. Shiller, Online Data (S&P 500 prices, dividends, CPI, long rates) via github.com/datasets/s-and-p-500; U.S. CPI (datasets/cpi-us); 10-year Treasury yields (datasets/bond-yields-us-10y); gold (datasets/gold-prices); CBOE VIX (datasets/finance-vix); S&P/Case-Shiller U.S. National Home Price Index (datasets/house-prices-us); S&P 500 constituents (datasets/s-and-p-500-companies). Data through Sep–Oct 2026.",
            "<b>WRDS:</b> CRSP monthly returns for the ETF universe and Fama-French factors (ff.factors_monthly), pulled once with scripts/fetch_wrds_data.py and cached in data/cache/.",
            "<b>ETF prices:</b> Yahoo Finance adjusted closes via the yfinance package, cached in data/cache/etf_prices.csv.",
            f"<b>Doctorate salaries:</b> {ref_src[1]['sed_2024']}",
            f"<b>Occupation wages:</b> {ref_src[1]['oews_2025']} Metro wages: BLS Public Data API (OEWS series OEUM…) when refreshed.",
            f"<b>Cost of living:</b> {ref_src[0]['rpp_2024']}",
            f"<b>Housing:</b> {ref_src[0]['list_price_sep2026']} Mortgage rate: {r['housing']['_source']} National trend: S&P/Case-Shiller.",
            f"<b>Federal tax & accounts:</b> {r['federal']['_source']} {r['accounts']['_source']}",
            f"<b>State tax:</b> {r['states']['_source']}",
            f"<b>Student loans:</b> {r['loans']['_source']}",
            f"<b>Peer benchmarks:</b> {r['benchmarks']['_source']}",
            "<b>Neighborhood (ZIP-code) housing:</b> " + D.zip_housing_meta()["hud"] + "; " + D.zip_housing_meta()["zillow"] + "; "
            + D.zip_housing_meta()["realtor"] + ". ZIP locations: " + D.zip_housing_meta()["coords"] + ". Assembled from "
            + D.zip_housing_meta()["assembled_from"] + " (scripts/build_zip_housing.py).",
            "<b>News:</b> Google News RSS search feeds. <b>Listings:</b> RentCast API (optional user key). <b>Booking:</b> deep links to Google Flights, Kayak, Skyscanner, Amtrak, Wanderu, Rome2Rio.",
        ]
        lim = [
            "PhD-track career paths use national median starting salaries for new PhDs by field and sector (NSF SED); master's-track paths use your own expected salary "
            "(government and nonprofit scaled by SED sector pay ratios). Both are scaled by a metro factor; individual offers vary widely. Raises decay over a career; academia includes one promotion bump.",
            "The persona builder only asks PhD questions of clients in a PhD or postdoc, or planning one. 'Compare with doing a PhD' gives master's clients an opt-in what-if "
            f"that assumes a funded PhD at the NSF GRFP stipend (${C.TYPICAL_PHD_STIPEND:,.0f}/yr) and national SED salaries.",
            "The academia path is an expected value: your tenure-track probability times faculty pay, plus the remainder in industry at a 10% late-switch discount.",
            "Taxes are simplified: single filer, standard deduction (none for most nonresidents), state brackets from the Tax Foundation; no local taxes, credits (e.g., Lifetime Learning), or treaty specifics beyond the amount you enter.",
            "Monte Carlo resamples 12-month blocks of 1928–2026 U.S. history in real terms; equity shocks scale by your portfolio's volatility relative to the S&P 500. Cash is modeled as inflation + 0.5%/yr. Shiller dividends after mid-2023 use the trailing yield.",
            "In proxy mode (before market data is refreshed), each ETF follows its asset class's history, so sector and size tilts don't change results until real prices load.",
            "Neighborhood prices are typical values by ZIP code, not individual listings: HUD Small Area FMRs are 40th-percentile rents "
            "(HUD caps some high-rent ZIPs), Zillow indexes are smoothed typical values, and Realtor.com figures are monthly medians (Mar 2026).",
            "Metro scores weight cost-adjusted after-tax pay, a mortgage-to-pay ratio, a keyword match between your field and each metro's major industries (a qualitative tag), and BEA price levels.",
        ]
        return ui.div(ui.h5("Sources"), ui.tags.ul(*[ui.tags.li(ui.HTML(s)) for s in src]), ui.h5("Key assumptions & limitations"), ui.tags.ul(*[ui.tags.li(x) for x in lim]))

    @render.download_button(filename=lambda: f"athena-capital-{prof()['name'].replace(' ', '-').lower()}-{datetime.now():%Y%m%d}.html")
    def dl_report():
        p = prof()
        mc, _ = baseline_mc()
        i35 = min(len(mc["years"]) - 1, max(0, 35 - p["age"]))
        ctx = {"cf": cf(), "health": health(), "paths": [{"label": x.label, **C.path_metrics(x, p)} for x in paths()], "selected": sel(),
               "rec": risk(), "weights": {D.etf_label(k): v for k, v in weights().items()}, "mc": {"p35": mc["pct"][50][i35], "p65": mc["pct"][50][-1]},
               "goals": B.goal_status(p, cf()), "top_metros": L.score_metros(p, p["target_sector"], {"income": 1.5, "housing": 1, "career": 1.5, "cost": 0.5}),
               "nw": peer()["nw"], "nw_pct": peer()["pct"], "stipend_ratio": stipend()["ratio"]}
        yield RP.build(p, ctx, DISCLAIMER)


app = App(app_ui, server, static_assets=HERE / "www")

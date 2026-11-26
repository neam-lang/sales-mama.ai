"""Sales Harness Leaderboard (SalesHarnessBench, SHB-SEA) - Hugging Face Space."""
from __future__ import annotations

import json

import gradio as gr
import pandas as pd
import plotly.graph_objects as go

from src import about
from src.load import leaderboard_df, load_submissions, row, validate
from src.scoring import BENCH_VERSION, TRACKS, index, pareto_front, shs

SUBS = load_submissions()
DF = leaderboard_df(SUBS)

BASE_COLS = ["#", "Harness", "Model", "SHS", "95% CI", "vs leader", "Capability", "Trust", "Coverage", "Status"]
TRACK_COLS = [t.name for t in TRACKS if t.live]
EXTRA_COLS = ["Runtime", "Split", "pass^k", "k", "$/task", "min/task", "Crit. viol. %",
              "Inj. ASR %", "Open weights", "Open harness", "Date", "Flags"]
DEFAULT_EXTRA = ["Split", "pass^k", "$/task", "Crit. viol. %"]


def _datatypes(cols):
    return ["markdown" if c == "Harness" else "str" for c in cols]


def fmt(df: pd.DataFrame) -> pd.DataFrame:
    """Render every cell as text ('—' when missing): Gradio number cells crash on None."""
    def cell(v):
        if v is None or (isinstance(v, float) and v != v):
            return "—"
        if isinstance(v, float):
            return f"{v:.1f}" if abs(v) >= 1 else f"{v:.3g}"
        return str(v)
    return df.apply(lambda col: col.map(cell))


MODELS = ["any"] + (sorted(DF["Model"].unique().tolist()) if not DF.empty else [])


def filter_table(query, split, show_partial, open_only, model, tracks, extras):
    if DF.empty:
        return gr.update(value=pd.DataFrame({"Info": ["No submissions yet. See Submit."]}))
    d = DF.copy()
    if split != "all":
        d = d[d["Split"] == split]
    if not show_partial:
        d = d[d["_full"]]
    if open_only:
        d = d[d["Open weights"] == "yes"]
    if model and model != "any":
        d = d[d["Model"] == model]
    if query:
        q = query.lower()
        d = d[d.apply(lambda r: q in f"{r['Harness']} {r['Model']} {r['Runtime']}".lower(), axis=1)]
    cols = BASE_COLS + [c for c in TRACK_COLS if c in tracks] + [c for c in EXTRA_COLS if c in extras]
    return gr.update(value=fmt(d[cols]), datatype=_datatypes(cols))


def safety_table():
    if DF.empty:
        return pd.DataFrame()
    cols = ["Harness", "Model", "Trust", "Crit. viol. %", "Inj. ASR %", "Status"]
    return fmt(DF[cols])


def pareto_plot():
    fig = go.Figure()
    pts = [(r["$/task"], r["SHS"], r["Harness"], r["Model"]) for _, r in DF.iterrows()
           if r["_rankable"] and pd.notna(r["$/task"]) and pd.notna(r["SHS"])] if not DF.empty else []
    if not pts:
        fig.add_annotation(text="Appears when full-coverage submissions report $/task",
                           showarrow=False, font=dict(size=15))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
    else:
        front = set(pareto_front([(p[0], p[1]) for p in pts]))
        for i, (c, s, h, m) in enumerate(pts):
            fig.add_trace(go.Scatter(x=[c], y=[s], mode="markers", name=f"{h} · {m}",
                                     marker=dict(size=14 if i in front else 9,
                                                 symbol="star" if i in front else "circle")))
        f = sorted((pts[i][0], pts[i][1]) for i in front)
        fig.add_trace(go.Scatter(x=[p[0] for p in f], y=[p[1] for p in f], mode="lines",
                                 line=dict(dash="dot"), name="Pareto front"))
        fig.update_layout(xaxis_title="USD per task (log)", yaxis_title="SHS", xaxis_type="log")
    fig.update_layout(height=460, margin=dict(l=40, r=20, t=30, b=40), template="plotly_white")
    return fig


def index_table(w_score):
    full = DF[DF["_rankable"]] if not DF.empty else DF
    if full.empty or full["$/task"].isna().all():
        return pd.DataFrame({"Info": ["Needs full-coverage rows that report $/task."]})
    best = full["_shs"].max()
    min_usd = full["$/task"].dropna().min()
    d = full[["Harness", "Model", "SHS", "$/task"]].copy()
    d["Index"] = [None if (v := index(s_, best, c, min_usd, w_score)) is None else round(v, 1)
                  for s_, c in zip(full["_shs"], full["$/task"])]
    return fmt(d.sort_values("Index", ascending=False))


def check_submission(text):
    try:
        sub = json.loads(text)
    except json.JSONDecodeError as e:
        return f"❌ Not valid JSON: {e}", gr.update(visible=False)
    errs = validate(sub)
    if errs:
        return "❌ " + "\n❌ ".join(errs), gr.update(visible=False)
    r = shs(sub)
    msg = (f"✅ Valid `{sub['schema']}` submission.\n\n"
           f"- SHS: **{'—' if r['shs'] is None else round(r['shs'], 1)}**"
           f" · capability {round(100 * (r['capability'] or 0), 1)}"
           f" · trust {'not reported' if r['trust'] is None else round(100 * r['trust'], 1)}\n"
           f"- Coverage: {round(100 * r['coverage'])}% of track weight"
           f"{'' if r['full'] else ' → listed as partial, unranked'}\n"
           f"- To list it, open a PR adding this file to `results/` (see steps above).")
    rr = row(sub)
    preview = fmt(pd.DataFrame([{k: v for k, v in rr.items() if not k.startswith("_")}]))
    return msg, gr.update(value=preview, visible=True, datatype=_datatypes(list(preview.columns)))


with gr.Blocks(title="Sales Harness Leaderboard", theme=gr.themes.Soft(primary_hue="orange"),
               css=about.CSS) as demo:
    gr.HTML(about.header_html(len(SUBS), BENCH_VERSION))

    with gr.Tabs():
        with gr.Tab("🏆 Leaderboard"):
            gr.Markdown(about.LEADERBOARD_INTRO)
            with gr.Row():
                query = gr.Textbox(placeholder="Search harness, model or runtime", show_label=False, scale=3)
                split = gr.Radio(["all", "test", "dev"], value="all", label="Split", scale=2)
                show_partial = gr.Checkbox(value=True, label="Show partial / reference rows")
                open_only = gr.Checkbox(value=False, label="Open-weights models only")
            model = gr.Dropdown(MODELS, value="any", label="Hold model fixed (compare harnesses on the same model)")
            with gr.Accordion("Columns", open=False):
                tracks = gr.CheckboxGroup(TRACK_COLS, value=TRACK_COLS, label="Tracks")
                extras = gr.CheckboxGroup(EXTRA_COLS, value=DEFAULT_EXTRA, label="More columns")
            table = gr.Dataframe(interactive=False, wrap=True, elem_id="lb")
            inputs = [query, split, show_partial, open_only, model, tracks, extras]
            for c in inputs:
                c.change(filter_table, inputs, table)
            demo.load(filter_table, inputs, table)

        with gr.Tab("🧭 Tracks"):
            gr.Markdown(about.tracks_md())

        with gr.Tab("🛡️ Trust"):
            gr.Markdown(about.TRUST_MD)
            gr.Dataframe(value=safety_table(), interactive=False, datatype="markdown")

        with gr.Tab("💰 Cost vs score"):
            gr.Markdown(about.COST_MD)
            gr.Plot(value=pareto_plot())
            w = gr.Slider(0, 1, value=0.7, step=0.1, label="Weight on score (1 − weight on cost)")
            idx_tbl = gr.Dataframe(value=index_table(0.7), interactive=False, datatype="markdown")
            w.change(index_table, w, idx_tbl)

        with gr.Tab("📐 Methodology"):
            gr.Markdown(about.METHODOLOGY_MD)

        with gr.Tab("🚀 Submit"):
            gr.Markdown(about.SUBMIT_MD)
            sub_in = gr.Code(value=about.EXAMPLE_SUBMISSION, language="json", label="Submission JSON")
            check_btn = gr.Button("Check my submission", variant="primary")
            check_out = gr.Markdown()
            check_tbl = gr.Dataframe(interactive=False, wrap=True, visible=False)
            check_btn.click(check_submission, sub_in, [check_out, check_tbl])

        with gr.Tab("📚 Research"):
            gr.Markdown(about.REFERENCES_MD)

    with gr.Accordion("📙 Citation", open=False):
        gr.Code(value=about.CITATION, language=None, show_label=False)

if __name__ == "__main__":
    demo.launch()

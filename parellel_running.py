"""
Data Quality Comparator — Enterprise Edition
A sophisticated tool for comparing two data files with rich DQ statistics.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import numpy as np
import os
import json
import csv
from datetime import datetime
from collections import defaultdict
import threading
import math

# ─────────────────────────────────────────────────────────────────────────────
# THEME & PALETTE
# ─────────────────────────────────────────────────────────────────────────────
THEME = {
    "bg_deep":       "#0A0D14",
    "bg_panel":      "#0F1520",
    "bg_card":       "#141C2E",
    "bg_hover":      "#1A2540",
    "border":        "#1E2D4A",
    "border_bright": "#2A3F6A",
    "accent_blue":   "#1B6FE8",
    "accent_cyan":   "#00C4FF",
    "accent_green":  "#00E5A0",
    "accent_orange": "#FF8C42",
    "accent_red":    "#FF4D6A",
    "accent_yellow": "#FFD166",
    "text_primary":  "#E8EDF7",
    "text_secondary":"#8A9BC4",
    "text_muted":    "#4A5A7A",
    "text_accent":   "#00C4FF",
    "tag_only_a":    "#1A3A2A",
    "tag_only_b":    "#3A1A1A",
    "tag_diff":      "#2A2A1A",
    "tag_match":     "#1A2A3A",
}

FONTS = {
    "display":   ("Georgia", 22, "bold"),
    "heading":   ("Georgia", 14, "bold"),
    "subheading":("Courier New", 11, "bold"),
    "body":      ("Courier New", 10),
    "body_sm":   ("Courier New", 9),
    "mono":      ("Courier New", 10),
    "mono_sm":   ("Courier New", 9),
    "badge":     ("Courier New", 8, "bold"),
    "stat_big":  ("Georgia", 26, "bold"),
    "stat_label":("Courier New", 9),
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def load_file(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    elif ext == ".csv":
        return pd.read_csv(path)
    elif ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    elif ext == ".json":
        return pd.read_json(path)
    elif ext == ".parquet":
        return pd.read_parquet(path)
    else:
        return pd.read_csv(path)

def compute_column_stats(df: pd.DataFrame, col: str) -> dict:
    s = df[col]
    total = len(s)
    null_count = s.isna().sum()
    non_null = s.dropna()
    unique_vals = non_null.nunique()
    is_numeric = pd.api.types.is_numeric_dtype(s)
    stats = {
        "total":        total,
        "null_count":   int(null_count),
        "null_pct":     round(null_count / total * 100, 2) if total > 0 else 0,
        "non_null":     int(total - null_count),
        "unique":       int(unique_vals),
        "unique_pct":   round(unique_vals / (total - null_count) * 100, 2) if (total - null_count) > 0 else 0,
        "dtype":        str(s.dtype),
        "is_numeric":   is_numeric,
    }
    if is_numeric and len(non_null) > 0:
        stats.update({
            "min":    round(float(non_null.min()), 4),
            "max":    round(float(non_null.max()), 4),
            "mean":   round(float(non_null.mean()), 4),
            "median": round(float(non_null.median()), 4),
            "std":    round(float(non_null.std()), 4),
        })
    top5 = non_null.value_counts().head(5)
    stats["top_values"] = [(str(k), int(v)) for k, v in top5.items()]
    return stats

def compare_columns(df_a: pd.DataFrame, df_b: pd.DataFrame,
                    key_col: str, compare_cols: list) -> dict:
    results = {}

    # Merge on key
    merged = pd.merge(
        df_a[[key_col] + compare_cols].copy(),
        df_b[[key_col] + compare_cols].copy(),
        on=key_col, how="outer", suffixes=("__A", "__B"), indicator=True
    )

    only_a_mask = merged["_merge"] == "left_only"
    only_b_mask = merged["_merge"] == "right_only"
    both_mask   = merged["_merge"] == "both"

    results["total_keys_a"]    = len(df_a[key_col].dropna().unique())
    results["total_keys_b"]    = len(df_b[key_col].dropna().unique())
    results["keys_only_in_a"]  = merged.loc[only_a_mask, key_col].tolist()
    results["keys_only_in_b"]  = merged.loc[only_b_mask, key_col].tolist()
    results["keys_in_both"]    = int(both_mask.sum())
    results["total_matched"]   = int(both_mask.sum())

    col_diffs = {}
    for col in compare_cols:
        col_a = col + "__A"
        col_b = col + "__B"
        if col_a not in merged.columns or col_b not in merged.columns:
            continue
        matched_rows = merged[both_mask].copy()
        a_vals = matched_rows[col_a]
        b_vals = matched_rows[col_b]

        # Compare with NaN-aware logic
        same_mask = (
            (a_vals == b_vals) |
            (a_vals.isna() & b_vals.isna())
        )
        diff_rows = matched_rows[~same_mask][[key_col, col_a, col_b]].copy()
        diff_rows.columns = [key_col, "value_a", "value_b"]

        col_diffs[col] = {
            "match_count":  int(same_mask.sum()),
            "diff_count":   int((~same_mask).sum()),
            "match_pct":    round(same_mask.sum() / len(matched_rows) * 100, 2) if len(matched_rows) > 0 else 0,
            "diff_pct":     round((~same_mask).sum() / len(matched_rows) * 100, 2) if len(matched_rows) > 0 else 0,
            "diff_rows":    diff_rows.head(500).to_dict("records"),
            "null_only_a":  int(a_vals.isna().sum()),
            "null_only_b":  int(b_vals.isna().sum()),
        }

    results["column_diffs"] = col_diffs
    results["merged"] = merged
    return results

def compute_dq_summary(df: pd.DataFrame) -> dict:
    total_cells = df.shape[0] * df.shape[1]
    null_cells   = df.isna().sum().sum()
    dup_rows     = df.duplicated().sum()
    return {
        "rows":       df.shape[0],
        "cols":       df.shape[1],
        "total_cells":int(total_cells),
        "null_cells": int(null_cells),
        "null_pct":   round(null_cells / total_cells * 100, 2) if total_cells > 0 else 0,
        "dup_rows":   int(dup_rows),
        "dup_pct":    round(dup_rows / df.shape[0] * 100, 2) if df.shape[0] > 0 else 0,
        "dtypes":     {c: str(t) for c, t in df.dtypes.items()},
        "col_stats":  {c: compute_column_stats(df, c) for c in df.columns},
    }

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM WIDGETS
# ─────────────────────────────────────────────────────────────────────────────
class StyledScrolledText(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg_card"],
                         highlightthickness=1,
                         highlightbackground=THEME["border"])
        self.text = tk.Text(self, wrap="none",
                            bg=THEME["bg_card"], fg=THEME["text_primary"],
                            insertbackground=THEME["accent_cyan"],
                            font=FONTS["mono_sm"],
                            bd=0, padx=8, pady=8,
                            selectbackground=THEME["accent_blue"],
                            **kwargs)
        vscroll = tk.Scrollbar(self, orient="vertical",
                               command=self.text.yview,
                               bg=THEME["bg_panel"], troughcolor=THEME["bg_deep"],
                               width=10)
        hscroll = tk.Scrollbar(self, orient="horizontal",
                               command=self.text.xview,
                               bg=THEME["bg_panel"], troughcolor=THEME["bg_deep"],
                               width=10)
        self.text.configure(yscrollcommand=vscroll.set,
                            xscrollcommand=hscroll.set)
        vscroll.pack(side="right", fill="y")
        hscroll.pack(side="bottom", fill="x")
        self.text.pack(fill="both", expand=True)

        # Tag styles
        self.text.tag_configure("heading",   foreground=THEME["accent_cyan"],  font=FONTS["subheading"])
        self.text.tag_configure("subheading",foreground=THEME["accent_yellow"],font=FONTS["subheading"])
        self.text.tag_configure("good",      foreground=THEME["accent_green"])
        self.text.tag_configure("bad",       foreground=THEME["accent_red"])
        self.text.tag_configure("warn",      foreground=THEME["accent_orange"])
        self.text.tag_configure("muted",     foreground=THEME["text_muted"])
        self.text.tag_configure("key",       foreground=THEME["accent_cyan"])
        self.text.tag_configure("value",     foreground=THEME["text_primary"])
        self.text.tag_configure("sep",       foreground=THEME["border_bright"])
        self.text.tag_configure("diff_a",    foreground=THEME["accent_red"])
        self.text.tag_configure("diff_b",    foreground=THEME["accent_green"])

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")

    def write(self, text, tag=None):
        self.text.config(state="normal")
        if tag:
            self.text.insert("end", text, tag)
        else:
            self.text.insert("end", text)

    def freeze(self):
        self.text.config(state="disabled")


class StatCard(tk.Frame):
    def __init__(self, parent, label, value, color=None, **kwargs):
        super().__init__(parent, bg=THEME["bg_card"],
                         highlightthickness=1,
                         highlightbackground=THEME["border"], **kwargs)
        color = color or THEME["accent_cyan"]
        tk.Label(self, text=str(value), font=FONTS["stat_big"],
                 bg=THEME["bg_card"], fg=color).pack(pady=(14, 2))
        tk.Label(self, text=label.upper(), font=FONTS["stat_label"],
                 bg=THEME["bg_card"], fg=THEME["text_muted"],
                 wraplength=110, justify="center").pack(pady=(0, 12))

    def update_value(self, val, color=None):
        pass  # static for now


class FileDropZone(tk.Frame):
    def __init__(self, parent, label, on_load, **kwargs):
        super().__init__(parent, bg=THEME["bg_card"],
                         highlightthickness=2,
                         highlightbackground=THEME["border"], **kwargs)
        self.on_load = on_load
        self.label   = label
        self.df      = None
        self.path    = None
        self._build()

    def _build(self):
        self.configure(cursor="hand2")
        inner = tk.Frame(self, bg=THEME["bg_card"])
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        self.icon_lbl = tk.Label(inner, text="⬆", font=("Georgia", 28),
                                 bg=THEME["bg_card"], fg=THEME["text_muted"])
        self.icon_lbl.pack(pady=(8, 4))

        self.file_lbl = tk.Label(inner, text=f"{self.label}",
                                 font=FONTS["heading"], bg=THEME["bg_card"],
                                 fg=THEME["text_secondary"])
        self.file_lbl.pack()

        self.sub_lbl = tk.Label(inner,
                                text="Click to browse  ·  CSV / XLSX / TSV / JSON / Parquet",
                                font=FONTS["body_sm"], bg=THEME["bg_card"],
                                fg=THEME["text_muted"])
        self.sub_lbl.pack(pady=(2, 8))

        self.meta_lbl = tk.Label(inner, text="", font=FONTS["mono_sm"],
                                 bg=THEME["bg_card"], fg=THEME["accent_green"])
        self.meta_lbl.pack()

        for w in [self, inner, self.icon_lbl, self.file_lbl, self.sub_lbl, self.meta_lbl]:
            w.bind("<Button-1>", lambda e: self._pick())
            w.bind("<Enter>",    lambda e: self.configure(highlightbackground=THEME["accent_blue"]))
            w.bind("<Leave>",    lambda e: self.configure(
                highlightbackground=THEME["accent_green"] if self.df is not None else THEME["border"]))

    def _pick(self):
        path = filedialog.askopenfilename(
            title=f"Select {self.label}",
            filetypes=[("Data files", "*.csv *.xlsx *.xls *.tsv *.json *.parquet"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            df = load_file(path)
            self.df   = df
            self.path = path
            fname = os.path.basename(path)
            self.file_lbl.config(text=fname, fg=THEME["text_primary"])
            self.icon_lbl.config(text="✓", fg=THEME["accent_green"])
            self.sub_lbl.config(
                text=f"{df.shape[0]:,} rows  ×  {df.shape[1]} columns",
                fg=THEME["accent_yellow"])
            size_kb = os.path.getsize(path) / 1024
            self.meta_lbl.config(
                text=f"Size: {size_kb:.1f} KB  ·  Columns: {', '.join(df.columns[:4])}{'…' if len(df.columns) > 4 else ''}",
                fg=THEME["text_secondary"])
            self.configure(highlightbackground=THEME["accent_green"])
            self.on_load(df, path)
        except Exception as ex:
            messagebox.showerror("Load Error", str(ex))


class ChecklistPanel(tk.Frame):
    def __init__(self, parent, title, **kwargs):
        super().__init__(parent, bg=THEME["bg_card"],
                         highlightthickness=1,
                         highlightbackground=THEME["border"], **kwargs)
        self.vars    = {}
        self.checks  = {}
        self._build(title)

    def _build(self, title):
        header = tk.Frame(self, bg=THEME["bg_panel"])
        header.pack(fill="x")
        tk.Label(header, text=title, font=FONTS["subheading"],
                 bg=THEME["bg_panel"], fg=THEME["accent_cyan"],
                 padx=12, pady=8).pack(side="left")

        btn_frame = tk.Frame(header, bg=THEME["bg_panel"])
        btn_frame.pack(side="right", padx=8)
        tk.Button(btn_frame, text="All", font=FONTS["badge"],
                  bg=THEME["accent_blue"], fg="white", bd=0, padx=6, pady=3,
                  cursor="hand2",
                  command=lambda: self._toggle_all(True)).pack(side="left", padx=2)
        tk.Button(btn_frame, text="None", font=FONTS["badge"],
                  bg=THEME["bg_hover"], fg=THEME["text_secondary"], bd=0, padx=6, pady=3,
                  cursor="hand2",
                  command=lambda: self._toggle_all(False)).pack(side="left", padx=2)

        self.canvas   = tk.Canvas(self, bg=THEME["bg_card"], bd=0, highlightthickness=0)
        scrollbar     = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                     width=8, bg=THEME["bg_panel"])
        self.scroll_f = tk.Frame(self.canvas, bg=THEME["bg_card"])
        self.scroll_f.bind("<Configure>",
                           lambda e: self.canvas.configure(
                               scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_f, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)

    def populate(self, columns):
        for w in self.scroll_f.winfo_children():
            w.destroy()
        self.vars   = {}
        self.checks = {}
        for i, col in enumerate(columns):
            var = tk.BooleanVar(value=True)
            row = tk.Frame(self.scroll_f, bg=THEME["bg_card"] if i % 2 == 0 else THEME["bg_hover"])
            row.pack(fill="x")
            cb = tk.Checkbutton(row, text=col, variable=var,
                                bg=row["bg"], fg=THEME["text_primary"],
                                selectcolor=THEME["accent_blue"],
                                activebackground=row["bg"],
                                font=FONTS["body_sm"], anchor="w",
                                padx=10, pady=4)
            cb.pack(side="left", fill="x", expand=True)
            self.vars[col]   = var
            self.checks[col] = cb

    def _toggle_all(self, state: bool):
        for v in self.vars.values():
            v.set(state)

    def get_selected(self) -> list:
        return [c for c, v in self.vars.items() if v.get()]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
class DQComparatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DQ Comparator  ·  Enterprise Edition")
        self.configure(bg=THEME["bg_deep"])
        self.geometry("1440x920")
        self.minsize(1100, 700)

        self.df_a    = None
        self.df_b    = None
        self.path_a  = None
        self.path_b  = None
        self.results = None

        self._configure_ttk_styles()
        self._build_ui()

    # ── TTK Styles ──────────────────────────────────────────────────────────
    def _configure_ttk_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook",
                        background=THEME["bg_deep"],
                        borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=THEME["bg_panel"],
                        foreground=THEME["text_secondary"],
                        font=FONTS["subheading"],
                        padding=[18, 8],
                        borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", THEME["bg_card"])],
                  foreground=[("selected", THEME["accent_cyan"])])
        style.configure("TCombobox",
                        fieldbackground=THEME["bg_card"],
                        background=THEME["bg_card"],
                        foreground=THEME["text_primary"],
                        arrowcolor=THEME["accent_cyan"],
                        borderwidth=1)
        style.configure("Treeview",
                        background=THEME["bg_card"],
                        foreground=THEME["text_primary"],
                        fieldbackground=THEME["bg_card"],
                        font=FONTS["mono_sm"],
                        rowheight=26,
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background=THEME["bg_panel"],
                        foreground=THEME["accent_cyan"],
                        font=FONTS["subheading"],
                        relief="flat")
        style.map("Treeview",
                  background=[("selected", THEME["accent_blue"])],
                  foreground=[("selected", "white")])
        style.configure("Vertical.TScrollbar",
                        troughcolor=THEME["bg_deep"],
                        background=THEME["bg_panel"],
                        arrowcolor=THEME["text_muted"])

    # ── Root Layout ─────────────────────────────────────────────────────────
    def _build_ui(self):
        # HEADER
        header = tk.Frame(self, bg=THEME["bg_panel"], height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        tk.Label(header, text="⬡  DATA QUALITY COMPARATOR",
                 font=FONTS["display"], bg=THEME["bg_panel"],
                 fg=THEME["accent_cyan"]).pack(side="left", padx=24, pady=12)
        self.status_lbl = tk.Label(header, text="Ready  ·  Load two files to begin",
                                   font=FONTS["body_sm"], bg=THEME["bg_panel"],
                                   fg=THEME["text_muted"])
        self.status_lbl.pack(side="right", padx=20)
        tk.Frame(header, bg=THEME["border"], height=1).pack(side="bottom", fill="x")

        # MAIN CONTENT (paned)
        main = tk.Frame(self, bg=THEME["bg_deep"])
        main.pack(fill="both", expand=True)

        # LEFT SIDEBAR
        sidebar = tk.Frame(main, bg=THEME["bg_panel"], width=320)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # RIGHT AREA
        right = tk.Frame(main, bg=THEME["bg_deep"])
        right.pack(side="left", fill="both", expand=True)
        self._build_content(right)

    # ── Sidebar ─────────────────────────────────────────────────────────────
    def _build_sidebar(self, parent):
        tk.Frame(parent, bg=THEME["border_bright"], height=1).pack(fill="x")

        # Section: Files
        sec = tk.Frame(parent, bg=THEME["bg_panel"])
        sec.pack(fill="x", padx=0)
        tk.Label(sec, text="FILES", font=FONTS["badge"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 padx=16, pady=10).pack(anchor="w")

        self.zone_a = FileDropZone(parent, "FILE  A  (baseline)", self._on_load_a)
        self.zone_a.pack(fill="x", padx=12, pady=(0, 6))

        self.zone_b = FileDropZone(parent, "FILE  B  (compare)", self._on_load_b)
        self.zone_b.pack(fill="x", padx=12, pady=(0, 12))

        tk.Frame(parent, bg=THEME["border"], height=1).pack(fill="x", padx=12)

        # Section: Key Column
        sec2 = tk.Frame(parent, bg=THEME["bg_panel"])
        sec2.pack(fill="x", padx=0)
        tk.Label(sec2, text="JOIN KEY COLUMN", font=FONTS["badge"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 padx=16, pady=10).pack(anchor="w")

        key_frame = tk.Frame(sec2, bg=THEME["bg_panel"])
        key_frame.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(key_frame, text="Key Column  (common to both files)",
                 font=FONTS["body_sm"], bg=THEME["bg_panel"],
                 fg=THEME["text_secondary"]).pack(anchor="w")
        self.key_var = tk.StringVar()
        self.key_combo = ttk.Combobox(key_frame, textvariable=self.key_var,
                                      state="readonly", font=FONTS["body_sm"])
        self.key_combo.pack(fill="x", pady=4)

        tk.Frame(parent, bg=THEME["border"], height=1).pack(fill="x", padx=12)

        # Section: Column selection
        sec3 = tk.Frame(parent, bg=THEME["bg_panel"])
        sec3.pack(fill="x")
        tk.Label(sec3, text="COMPARE COLUMNS", font=FONTS["badge"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 padx=16, pady=10).pack(anchor="w")

        self.col_list = ChecklistPanel(parent, "Common Columns")
        self.col_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # RUN BUTTON
        btn_frame = tk.Frame(parent, bg=THEME["bg_panel"])
        btn_frame.pack(fill="x", padx=12, pady=10)

        self.run_btn = tk.Button(btn_frame, text="  ▶  RUN COMPARISON",
                                 font=FONTS["subheading"],
                                 bg=THEME["accent_blue"], fg="white",
                                 relief="flat", bd=0, pady=10,
                                 cursor="hand2",
                                 activebackground=THEME["accent_cyan"],
                                 command=self._run_comparison)
        self.run_btn.pack(fill="x")

        self.export_btn = tk.Button(btn_frame, text="  ↓  EXPORT RESULTS",
                                    font=FONTS["subheading"],
                                    bg=THEME["bg_hover"], fg=THEME["text_secondary"],
                                    relief="flat", bd=0, pady=10,
                                    cursor="hand2",
                                    command=self._export_results)
        self.export_btn.pack(fill="x", pady=(6, 0))

    # ── Content Area ────────────────────────────────────────────────────────
    def _build_content(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # Tab 1 – Overview
        self.tab_overview = tk.Frame(self.notebook, bg=THEME["bg_deep"])
        self.notebook.add(self.tab_overview, text="  Overview  ")
        self._build_overview_tab(self.tab_overview)

        # Tab 2 – Differences
        self.tab_diffs = tk.Frame(self.notebook, bg=THEME["bg_deep"])
        self.notebook.add(self.tab_diffs, text="  Differences  ")
        self._build_diffs_tab(self.tab_diffs)

        # Tab 3 – Only in A / B
        self.tab_only = tk.Frame(self.notebook, bg=THEME["bg_deep"])
        self.notebook.add(self.tab_only, text="  Exclusive Rows  ")
        self._build_only_tab(self.tab_only)

        # Tab 4 – Column Stats
        self.tab_stats = tk.Frame(self.notebook, bg=THEME["bg_deep"])
        self.notebook.add(self.tab_stats, text="  Column Stats  ")
        self._build_stats_tab(self.tab_stats)

        # Tab 5 – Raw Log
        self.tab_log = tk.Frame(self.notebook, bg=THEME["bg_deep"])
        self.notebook.add(self.tab_log, text="  Full Report  ")
        self._build_log_tab(self.tab_log)

    # ── Tab: Overview ───────────────────────────────────────────────────────
    def _build_overview_tab(self, parent):
        # Placeholder — populated after run
        self.overview_placeholder = tk.Label(
            parent,
            text="Run a comparison to see the overview",
            font=FONTS["heading"], bg=THEME["bg_deep"],
            fg=THEME["text_muted"])
        self.overview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _populate_overview(self, res, summary_a, summary_b):
        for w in self.tab_overview.winfo_children():
            w.destroy()

        canvas = tk.Canvas(self.tab_overview, bg=THEME["bg_deep"],
                           bd=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self.tab_overview, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        scroll_frame = tk.Frame(canvas, bg=THEME["bg_deep"])
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        pad = {"padx": 8, "pady": 4}

        # Section: Summary Cards
        tk.Label(scroll_frame, text="COMPARISON SUMMARY",
                 font=FONTS["subheading"], bg=THEME["bg_deep"],
                 fg=THEME["text_muted"]).pack(anchor="w", padx=16, pady=(16, 4))

        kpi_row = tk.Frame(scroll_frame, bg=THEME["bg_deep"])
        kpi_row.pack(fill="x", padx=12, pady=4)

        kpis = [
            ("Keys in A",    f"{res['total_keys_a']:,}",    THEME["accent_cyan"]),
            ("Keys in B",    f"{res['total_keys_b']:,}",    THEME["accent_cyan"]),
            ("Matched Keys", f"{res['keys_in_both']:,}",    THEME["accent_green"]),
            ("Only in A",    f"{len(res['keys_only_in_a']):,}", THEME["accent_orange"]),
            ("Only in B",    f"{len(res['keys_only_in_b']):,}", THEME["accent_red"]),
            ("Cols Compared",f"{len(res['column_diffs'])}",  THEME["accent_yellow"]),
        ]
        for lbl, val, col in kpis:
            StatCard(kpi_row, lbl, val, col).pack(side="left", padx=6, pady=4,
                                                   ipadx=12, fill="y")

        # Section: File summary side-by-side
        tk.Label(scroll_frame, text="FILE PROFILES",
                 font=FONTS["subheading"], bg=THEME["bg_deep"],
                 fg=THEME["text_muted"]).pack(anchor="w", padx=16, pady=(18, 4))

        row2 = tk.Frame(scroll_frame, bg=THEME["bg_deep"])
        row2.pack(fill="x", padx=12, pady=4)

        for tag, summary, fname in [("A", summary_a, self.path_a), ("B", summary_b, self.path_b)]:
            card = tk.Frame(row2, bg=THEME["bg_card"],
                            highlightthickness=1,
                            highlightbackground=THEME["border"])
            card.pack(side="left", fill="both", expand=True, padx=6)
            color = THEME["accent_orange"] if tag == "A" else THEME["accent_red"]
            tk.Label(card, text=f"FILE  {tag}  —  {os.path.basename(fname)}",
                     font=FONTS["subheading"], bg=THEME["bg_card"],
                     fg=color, padx=12, pady=10).pack(anchor="w")
            tk.Frame(card, bg=THEME["border"], height=1).pack(fill="x")
            items = [
                ("Rows",          f"{summary['rows']:,}"),
                ("Columns",       f"{summary['cols']}"),
                ("Total Cells",   f"{summary['total_cells']:,}"),
                ("Null Cells",    f"{summary['null_cells']:,}  ({summary['null_pct']}%)"),
                ("Duplicate Rows",f"{summary['dup_rows']:,}  ({summary['dup_pct']}%)"),
            ]
            for k, v in items:
                r = tk.Frame(card, bg=THEME["bg_card"])
                r.pack(fill="x", padx=12, pady=3)
                tk.Label(r, text=k, font=FONTS["body_sm"],
                         bg=THEME["bg_card"], fg=THEME["text_muted"],
                         width=18, anchor="w").pack(side="left")
                tk.Label(r, text=v, font=FONTS["mono_sm"],
                         bg=THEME["bg_card"], fg=THEME["text_primary"],
                         anchor="w").pack(side="left")

        # Section: Column match matrix
        tk.Label(scroll_frame, text="COLUMN MATCH MATRIX",
                 font=FONTS["subheading"], bg=THEME["bg_deep"],
                 fg=THEME["text_muted"]).pack(anchor="w", padx=16, pady=(18, 4))

        matrix_frame = tk.Frame(scroll_frame, bg=THEME["bg_card"],
                                highlightthickness=1,
                                highlightbackground=THEME["border"])
        matrix_frame.pack(fill="x", padx=12, pady=4)

        headers = ["Column", "Matched", "Different", "Match %", "Null A", "Null B"]
        hrow = tk.Frame(matrix_frame, bg=THEME["bg_panel"])
        hrow.pack(fill="x")
        widths = [28, 10, 10, 10, 8, 8]
        for h, w in zip(headers, widths):
            tk.Label(hrow, text=h, font=FONTS["subheading"],
                     bg=THEME["bg_panel"], fg=THEME["accent_cyan"],
                     width=w, anchor="w", padx=6, pady=6).pack(side="left")

        for i, (col, d) in enumerate(res["column_diffs"].items()):
            bg = THEME["bg_card"] if i % 2 == 0 else THEME["bg_hover"]
            mrow = tk.Frame(matrix_frame, bg=bg)
            mrow.pack(fill="x")
            pct = d["match_pct"]
            pct_color = (THEME["accent_green"] if pct >= 95
                         else THEME["accent_yellow"] if pct >= 70
                         else THEME["accent_red"])
            vals = [col, d["match_count"], d["diff_count"],
                    f"{pct}%", d["null_only_a"], d["null_only_b"]]
            for j, (v, w) in enumerate(zip(vals, widths)):
                col_fg = pct_color if j == 3 else THEME["text_primary"]
                tk.Label(mrow, text=str(v), font=FONTS["mono_sm"],
                         bg=bg, fg=col_fg, width=w, anchor="w",
                         padx=6, pady=5).pack(side="left")

    # ── Tab: Differences ────────────────────────────────────────────────────
    def _build_diffs_tab(self, parent):
        # Left: column list
        left = tk.Frame(parent, bg=THEME["bg_panel"], width=220)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="COLUMNS", font=FONTS["badge"],
                 bg=THEME["bg_panel"], fg=THEME["text_muted"],
                 padx=12, pady=10).pack(anchor="w")
        self.diff_col_lb = tk.Listbox(left, bg=THEME["bg_card"],
                                      fg=THEME["text_primary"],
                                      selectbackground=THEME["accent_blue"],
                                      font=FONTS["body_sm"], bd=0,
                                      activestyle="none",
                                      highlightthickness=0)
        self.diff_col_lb.pack(fill="both", expand=True, padx=6, pady=6)
        self.diff_col_lb.bind("<<ListboxSelect>>", self._show_diff_detail)

        # Right: detail
        right = tk.Frame(parent, bg=THEME["bg_deep"])
        right.pack(side="left", fill="both", expand=True)

        self.diff_title = tk.Label(right, text="Select a column →",
                                   font=FONTS["heading"], bg=THEME["bg_deep"],
                                   fg=THEME["accent_cyan"], padx=12, pady=10)
        self.diff_title.pack(anchor="w")

        cols = ("key", "value_a", "value_b")
        tree_frame = tk.Frame(right, bg=THEME["bg_deep"])
        tree_frame.pack(fill="both", expand=True, padx=8, pady=4)
        self.diff_tree = ttk.Treeview(tree_frame, columns=cols,
                                      show="headings", selectmode="browse")
        for c, w, txt in zip(cols, [200, 280, 280],
                             ["Key", "Value in  A", "Value in  B"]):
            self.diff_tree.heading(c, text=txt)
            self.diff_tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.diff_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                            command=self.diff_tree.xview)
        self.diff_tree.configure(yscrollcommand=vsb.set,
                                 xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.diff_tree.pack(fill="both", expand=True)
        self.diff_tree.tag_configure("odd",  background=THEME["bg_hover"])
        self.diff_tree.tag_configure("even", background=THEME["bg_card"])

    def _show_diff_detail(self, event=None):
        sel = self.diff_col_lb.curselection()
        if not sel or not self.results:
            return
        col = self.diff_col_lb.get(sel[0])
        data = self.results["column_diffs"].get(col, {})
        diffs = data.get("diff_rows", [])
        self.diff_title.config(
            text=f"⬡  {col}  —  {len(diffs)} difference(s)  "
                 f"[ {data.get('diff_pct', 0)}% mismatch ]")
        for row in self.diff_tree.get_children():
            self.diff_tree.delete(row)
        for i, r in enumerate(diffs):
            tag = "even" if i % 2 == 0 else "odd"
            key = list(r.values())[0]
            self.diff_tree.insert("", "end",
                                  values=(key, r.get("value_a", ""),
                                          r.get("value_b", "")),
                                  tags=(tag,))

    # ── Tab: Only in A / B ──────────────────────────────────────────────────
    def _build_only_tab(self, parent):
        panes = tk.Frame(parent, bg=THEME["bg_deep"])
        panes.pack(fill="both", expand=True)

        for side, color, attr in [
            ("A", THEME["accent_orange"], "only_a_text"),
            ("B", THEME["accent_red"],    "only_b_text")
        ]:
            frame = tk.Frame(panes, bg=THEME["bg_deep"])
            frame.pack(side="left", fill="both", expand=True, padx=4, pady=8)
            tk.Label(frame, text=f"ROWS EXCLUSIVE TO FILE  {side}",
                     font=FONTS["subheading"], bg=THEME["bg_deep"],
                     fg=color, pady=8).pack(anchor="w", padx=8)
            txt = StyledScrolledText(frame, height=8)
            txt.pack(fill="both", expand=True, padx=4)
            setattr(self, attr, txt)

    # ── Tab: Column Stats ───────────────────────────────────────────────────
    def _build_stats_tab(self, parent):
        self.stats_placeholder = tk.Label(
            parent, text="Run comparison to populate stats",
            font=FONTS["heading"], bg=THEME["bg_deep"], fg=THEME["text_muted"])
        self.stats_placeholder.place(relx=0.5, rely=0.5, anchor="center")

    def _populate_stats_tab(self, summary_a, summary_b):
        for w in self.tab_stats.winfo_children():
            w.destroy()

        notebook2 = ttk.Notebook(self.tab_stats)
        notebook2.pack(fill="both", expand=True, padx=4, pady=4)

        common_cols = set(summary_a["col_stats"]) & set(summary_b["col_stats"])

        for col in sorted(common_cols):
            frame = tk.Frame(notebook2, bg=THEME["bg_deep"])
            notebook2.add(frame, text=f"  {col}  ")
            self._build_col_stat_card(frame, col,
                                      summary_a["col_stats"][col],
                                      summary_b["col_stats"][col])

    def _build_col_stat_card(self, parent, col_name, sa, sb):
        canvas = tk.Canvas(parent, bg=THEME["bg_deep"], bd=0,
                           highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        sf = tk.Frame(canvas, bg=THEME["bg_deep"])
        canvas.create_window((0, 0), window=sf, anchor="nw")
        sf.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        tk.Label(sf, text=f"⬡  {col_name}",
                 font=FONTS["heading"], bg=THEME["bg_deep"],
                 fg=THEME["accent_cyan"], padx=16, pady=12).pack(anchor="w")

        # Side-by-side
        row = tk.Frame(sf, bg=THEME["bg_deep"])
        row.pack(fill="x", padx=12, pady=4)

        for tag, s in [("A", sa), ("B", sb)]:
            color = THEME["accent_orange"] if tag == "A" else THEME["accent_red"]
            card = tk.Frame(row, bg=THEME["bg_card"],
                            highlightthickness=1,
                            highlightbackground=THEME["border"])
            card.pack(side="left", fill="both", expand=True, padx=6, pady=4)
            tk.Label(card, text=f"FILE  {tag}", font=FONTS["subheading"],
                     bg=THEME["bg_card"], fg=color,
                     padx=12, pady=8).pack(anchor="w")
            tk.Frame(card, bg=THEME["border"], height=1).pack(fill="x")

            base_stats = [
                ("Total Rows",   f"{s['total']:,}"),
                ("Null Count",   f"{s['null_count']:,}  ({s['null_pct']}%)"),
                ("Non-Null",     f"{s['non_null']:,}"),
                ("Unique Values",f"{s['unique']:,}  ({s['unique_pct']}%)"),
                ("Data Type",    s["dtype"]),
            ]
            if s.get("is_numeric"):
                base_stats += [
                    ("Min",    str(s.get("min", ""))),
                    ("Max",    str(s.get("max", ""))),
                    ("Mean",   str(s.get("mean", ""))),
                    ("Median", str(s.get("median", ""))),
                    ("Std Dev",str(s.get("std", ""))),
                ]
            for k, v in base_stats:
                r = tk.Frame(card, bg=THEME["bg_card"])
                r.pack(fill="x", padx=12, pady=3)
                tk.Label(r, text=k, font=FONTS["body_sm"],
                         bg=THEME["bg_card"], fg=THEME["text_muted"],
                         width=16, anchor="w").pack(side="left")
                tk.Label(r, text=v, font=FONTS["mono_sm"],
                         bg=THEME["bg_card"], fg=THEME["text_primary"],
                         anchor="w").pack(side="left")

            # Top values
            tk.Label(card, text="TOP VALUES", font=FONTS["badge"],
                     bg=THEME["bg_card"], fg=THEME["text_muted"],
                     padx=12, pady=6).pack(anchor="w")
            for val, cnt in s.get("top_values", []):
                r2 = tk.Frame(card, bg=THEME["bg_hover"])
                r2.pack(fill="x", padx=12, pady=1)
                total = s["non_null"] or 1
                pct = cnt / total * 100
                bar_w = max(2, int(pct / 100 * 120))
                tk.Label(r2, text=val[:30], font=FONTS["mono_sm"],
                         bg=THEME["bg_hover"], fg=THEME["text_primary"],
                         width=24, anchor="w", padx=4, pady=3).pack(side="left")
                bar = tk.Frame(r2, bg=THEME["accent_blue"], height=6, width=bar_w)
                bar.pack(side="left", padx=4)
                tk.Label(r2, text=f"{pct:.1f}%  ({cnt:,})",
                         font=FONTS["mono_sm"],
                         bg=THEME["bg_hover"], fg=THEME["text_secondary"]).pack(side="left")

    # ── Tab: Log ─────────────────────────────────────────────────────────────
    def _build_log_tab(self, parent):
        toolbar = tk.Frame(parent, bg=THEME["bg_panel"])
        toolbar.pack(fill="x")
        tk.Button(toolbar, text="  Copy All  ", font=FONTS["badge"],
                  bg=THEME["bg_hover"], fg=THEME["text_secondary"],
                  bd=0, padx=8, pady=6,
                  command=self._copy_log).pack(side="left", padx=4, pady=4)
        self.log_txt = StyledScrolledText(parent)
        self.log_txt.pack(fill="both", expand=True, padx=8, pady=4)
        self._write_welcome_log()

    def _write_welcome_log(self):
        self.log_txt.clear()
        self.log_txt.write("╔" + "═" * 70 + "╗\n", "sep")
        self.log_txt.write("║  DATA QUALITY COMPARATOR  ·  Enterprise Edition".ljust(71) + "║\n", "heading")
        self.log_txt.write("╚" + "═" * 70 + "╝\n\n", "sep")
        self.log_txt.write("Load two files and press Run Comparison to generate a full report.\n", "muted")
        self.log_txt.freeze()

    # ── Event Handlers ───────────────────────────────────────────────────────
    def _on_load_a(self, df, path):
        self.df_a   = df
        self.path_a = path
        self._refresh_controls()

    def _on_load_b(self, df, path):
        self.df_b   = df
        self.path_b = path
        self._refresh_controls()

    def _refresh_controls(self):
        if self.df_a is None or self.df_b is None:
            return
        common = [c for c in self.df_a.columns if c in self.df_b.columns]
        self.key_combo["values"] = common
        if common:
            self.key_var.set(common[0])
        self.col_list.populate(common)
        self._set_status(f"Files loaded  ·  {len(common)} common column(s)")

    def _run_comparison(self):
        if self.df_a is None or self.df_b is None:
            messagebox.showwarning("Missing Files", "Please load both files first.")
            return
        key = self.key_var.get()
        if not key:
            messagebox.showwarning("No Key", "Please select a join key column.")
            return
        compare_cols = [c for c in self.col_list.get_selected() if c != key]
        if not compare_cols:
            messagebox.showwarning("No Columns", "Select at least one column to compare.")
            return

        self.run_btn.config(text="  ⌛  Running…", state="disabled")
        self._set_status("Running comparison…")

        def worker():
            try:
                summary_a = compute_dq_summary(self.df_a)
                summary_b = compute_dq_summary(self.df_b)
                res = compare_columns(self.df_a, self.df_b, key, compare_cols)
                self.after(0, lambda: self._render_results(res, summary_a, summary_b))
            except Exception as ex:
                self.after(0, lambda: messagebox.showerror("Error", str(ex)))
                self.after(0, lambda: self.run_btn.config(text="  ▶  RUN COMPARISON",
                                                          state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _render_results(self, res, summary_a, summary_b):
        self.results   = res
        self.summary_a = summary_a
        self.summary_b = summary_b

        self._populate_overview(res, summary_a, summary_b)
        self._populate_diffs_panel(res)
        self._populate_only_panels(res)
        self._populate_stats_tab(summary_a, summary_b)
        self._populate_log(res, summary_a, summary_b)

        self.run_btn.config(text="  ▶  RUN COMPARISON", state="normal")
        total_diffs = sum(d["diff_count"] for d in res["column_diffs"].values())
        self._set_status(
            f"Done  ·  {res['keys_in_both']:,} matched rows  ·  "
            f"{total_diffs:,} cell difference(s)  ·  "
            f"{len(res['keys_only_in_a'])} only-A  ·  "
            f"{len(res['keys_only_in_b'])} only-B")
        self.notebook.select(0)

    def _populate_diffs_panel(self, res):
        self.diff_col_lb.delete(0, "end")
        for col, d in sorted(res["column_diffs"].items(),
                              key=lambda x: -x[1]["diff_count"]):
            label = f"{col}  ({d['diff_count']})"
            self.diff_col_lb.insert("end", col)
            if d["diff_count"] > 0:
                self.diff_col_lb.itemconfig("end", fg=THEME["accent_red"])
            else:
                self.diff_col_lb.itemconfig("end", fg=THEME["accent_green"])

    def _populate_only_panels(self, res):
        for txt, keys, tag in [
            (self.only_a_text, res["keys_only_in_a"], "diff_a"),
            (self.only_b_text, res["keys_only_in_b"], "diff_b"),
        ]:
            txt.clear()
            if not keys:
                txt.write("✓  All keys are present in both files.\n", "good")
            else:
                txt.write(f"{len(keys):,} exclusive row(s):\n\n", "warn")
                for i, k in enumerate(keys[:1000]):
                    txt.write(f"  {i+1:>5}.  {k}\n", tag)
                if len(keys) > 1000:
                    txt.write(f"\n  … and {len(keys)-1000:,} more (export for full list)\n", "muted")
            txt.freeze()

    def _populate_log(self, res, sa, sb):
        ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        w  = self.log_txt
        w.clear()
        sep = "─" * 72

        def line(txt="", tag=None):
            w.write(txt + "\n", tag)

        line("╔" + "═" * 70 + "╗", "sep")
        line("║  DQ COMPARATOR  ·  FULL REPORT".ljust(71) + "║", "heading")
        line("║  Generated: " + ts.ljust(58) + "║", "muted")
        line("╚" + "═" * 70 + "╝", "sep")
        line()
        line("FILE A:  " + (self.path_a or ""), "key")
        line("FILE B:  " + (self.path_b or ""), "key")
        line()
        line(sep, "sep")
        line("  GLOBAL STATISTICS", "subheading")
        line(sep, "sep")
        for tag, s in [("A", sa), ("B", sb)]:
            line(f"  File {tag}:", "subheading")
            line(f"    Rows:          {s['rows']:,}")
            line(f"    Columns:       {s['cols']}")
            line(f"    Null cells:    {s['null_cells']:,}  ({s['null_pct']}%)")
            line(f"    Duplicate rows:{s['dup_rows']:,}  ({s['dup_pct']}%)")
        line()
        line(sep, "sep")
        line("  KEY ANALYSIS", "subheading")
        line(sep, "sep")
        line(f"  Keys in A:      {res['total_keys_a']:,}")
        line(f"  Keys in B:      {res['total_keys_b']:,}")
        line(f"  Matched (both): {res['keys_in_both']:,}")
        cnt_a = len(res["keys_only_in_a"])
        cnt_b = len(res["keys_only_in_b"])
        col_a = "warn" if cnt_a > 0 else "good"
        col_b = "warn" if cnt_b > 0 else "good"
        line(f"  Only in A:      {cnt_a:,}", col_a)
        line(f"  Only in B:      {cnt_b:,}", col_b)
        line()
        line(sep, "sep")
        line("  COLUMN COMPARISON DETAIL", "subheading")
        line(sep, "sep")
        for col, d in sorted(res["column_diffs"].items(),
                              key=lambda x: -x[1]["diff_count"]):
            status = "good" if d["diff_count"] == 0 else "bad"
            tick   = "✓" if d["diff_count"] == 0 else "✗"
            line(f"\n  {tick}  {col}", status)
            line(f"     Matched:   {d['match_count']:,}  ({d['match_pct']}%)")
            line(f"     Different: {d['diff_count']:,}  ({d['diff_pct']}%)",
                 "bad" if d["diff_count"] > 0 else None)
            line(f"     Nulls A:   {d['null_only_a']:,}  |  Nulls B: {d['null_only_b']:,}", "muted")
            if d["diff_rows"]:
                line(f"     Sample diffs (up to 10):", "muted")
                for r in d["diff_rows"][:10]:
                    line(f"       key={list(r.values())[0]}  A={r.get('value_a','')}  B={r.get('value_b','')}", "muted")
        line()
        line(sep, "sep")
        line("  END OF REPORT", "subheading")
        line(sep, "sep")
        w.freeze()

    # ── Export ───────────────────────────────────────────────────────────────
    def _export_results(self):
        if not self.results:
            messagebox.showwarning("No Results", "Run a comparison first.")
            return
        path = filedialog.askdirectory(title="Select export folder")
        if not path:
            return
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(path, f"dq_comparison_{ts}")
        os.makedirs(base, exist_ok=True)
        res  = self.results

        # 1. Summary JSON
        summary = {
            "generated":     datetime.now().isoformat(),
            "file_a":        self.path_a,
            "file_b":        self.path_b,
            "total_keys_a":  res["total_keys_a"],
            "total_keys_b":  res["total_keys_b"],
            "keys_in_both":  res["keys_in_both"],
            "keys_only_in_a":len(res["keys_only_in_a"]),
            "keys_only_in_b":len(res["keys_only_in_b"]),
            "column_summary":{
                col: {k: v for k, v in d.items() if k != "diff_rows"}
                for col, d in res["column_diffs"].items()
            },
        }
        with open(os.path.join(base, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)

        # 2. Differences per column
        for col, d in res["column_diffs"].items():
            if d["diff_rows"]:
                safe = col.replace("/", "_").replace("\\", "_")
                with open(os.path.join(base, f"diffs_{safe}.csv"), "w",
                          newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(d["diff_rows"][0].keys()))
                    writer.writeheader()
                    writer.writerows(d["diff_rows"])

        # 3. Only-in-A / Only-in-B
        for side, keys in [("a", res["keys_only_in_a"]),
                           ("b", res["keys_only_in_b"])]:
            with open(os.path.join(base, f"only_in_{side}.txt"), "w") as f:
                f.write("\n".join(str(k) for k in keys))

        # 4. Full text log
        log_content = self.log_txt.text.get("1.0", "end")
        with open(os.path.join(base, "full_report.txt"), "w",
                  encoding="utf-8") as f:
            f.write(log_content)

        # 5. Excel summary workbook
        try:
            with pd.ExcelWriter(os.path.join(base, "dq_comparison.xlsx"),
                                engine="openpyxl") as writer:
                # Overview sheet
                overview_data = []
                for col, d in res["column_diffs"].items():
                    overview_data.append({
                        "Column":       col,
                        "Matched":      d["match_count"],
                        "Different":    d["diff_count"],
                        "Match_Pct":    d["match_pct"],
                        "Null_A":       d["null_only_a"],
                        "Null_B":       d["null_only_b"],
                    })
                pd.DataFrame(overview_data).to_excel(writer, sheet_name="Overview", index=False)

                # Keys sheet
                keys_df = pd.DataFrame({
                    "Keys Only in A": pd.Series(res["keys_only_in_a"]),
                    "Keys Only in B": pd.Series(res["keys_only_in_b"]),
                })
                keys_df.to_excel(writer, sheet_name="Exclusive Keys", index=False)

                # Per-column diff sheets
                for col, d in res["column_diffs"].items():
                    if d["diff_rows"]:
                        safe = col[:28].replace("/", "_")
                        pd.DataFrame(d["diff_rows"]).to_excel(
                            writer, sheet_name=f"Diff_{safe}", index=False)
        except Exception:
            pass  # openpyxl optional

        messagebox.showinfo("Export Complete",
                            f"Results exported to:\n{base}")
        self._set_status(f"Exported to {base}")

    def _copy_log(self):
        content = self.log_txt.text.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(content)
        self._set_status("Log copied to clipboard")

    def _set_status(self, msg: str):
        self.status_lbl.config(text=msg)

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = DQComparatorApp()
    app.mainloop()

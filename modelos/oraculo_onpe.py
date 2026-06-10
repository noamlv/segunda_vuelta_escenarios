#!/usr/bin/env python3
"""Proyeccion reproducible de la segunda vuelta a partir de cortes ONPE."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


FP = "fp"
JP = "jp"
VALID = "valid"
COUNTED = "CONTABILIZADA"
COLORS = {
    "fp": "#F0986E",
    "jp": "#71B436",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "gold": "#FFE15B",
    "olive": "#A3D576",
}


@dataclass
class Snapshot:
    path: Path
    timestamp: datetime
    advance_label: float
    data: pd.DataFrame


def ascii_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper().strip()


def normalize_mesa(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)


def parse_snapshot_metadata(path: Path) -> tuple[datetime, float]:
    name = path.stem
    match = re.search(
        r"_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(AM|PM)_([0-9.]+)",
        name,
        re.IGNORECASE,
    )
    if not match:
        return datetime.fromtimestamp(path.stat().st_mtime), math.nan
    year, month, day, hour, minute, ampm, advance = match.groups()
    hour_num = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
    return (
        datetime(int(year), int(month), int(day), hour_num, int(minute)),
        float(advance),
    )


def load_master(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Sheet 1", skiprows=10, dtype=str)
    raw.columns = [ascii_text(col).replace(" ", "_") for col in raw.columns]
    rename = {
        "MESA_DE_SUFRAGIO": "mesa",
        "TOTAL_ELECTORES": "electores",
        "DEPARTAMENTO": "region",
        "PROVINCIA": "provincia",
        "DISTRITO": "distrito",
        "NOMBRE_ODPE": "odpe",
        "NOMBRE_LV": "local",
    }
    raw = raw.rename(columns=rename)
    keep = ["mesa", "electores", "region", "provincia", "distrito", "odpe", "local"]
    master = raw[keep].copy()
    master["mesa"] = normalize_mesa(master["mesa"])
    master["electores"] = pd.to_numeric(master["electores"], errors="coerce").fillna(0)
    for col in ["region", "provincia", "distrito", "odpe", "local"]:
        master[col] = master[col].map(ascii_text)
    master["ambito"] = np.where(
        master["region"].isin(["AFRICA", "AMERICA", "ASIA", "EUROPA", "OCEANIA"]),
        "EXTRANJERO",
        "PERU",
    )
    return master.drop_duplicates("mesa", keep="first")


def load_snapshot(path: Path) -> Snapshot:
    timestamp, advance = parse_snapshot_metadata(path)
    raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, dtype=str)
    columns = {ascii_text(col): col for col in raw.columns}

    def get(name: str, default: object = "") -> pd.Series:
        source = columns.get(name)
        if source is None:
            return pd.Series(default, index=raw.index)
        return raw[source]

    data = pd.DataFrame(
        {
            "mesa": normalize_mesa(get("NUMERO DE MESA")),
            "estado": get("ESTADO DEL ACTA").map(ascii_text),
            "ambito": get("AMBITO").map(ascii_text),
            "region": get("REGION / CONTINENTE").map(ascii_text),
            "provincia": get("PROVINCIA / PAIS").map(ascii_text),
            "distrito": get("DISTRITO / CIUDAD").map(ascii_text),
            "local": get("LOCAL DE VOTACION").map(ascii_text),
            "electores": pd.to_numeric(
                get("ELECTORES HABILES"), errors="coerce"
            ).fillna(0),
            FP: pd.to_numeric(get("FUERZA POPULAR"), errors="coerce").fillna(0),
            JP: pd.to_numeric(get("JUNTOS POR EL PERU"), errors="coerce").fillna(0),
            "blancos": pd.to_numeric(get("VOTOS EN BLANCO"), errors="coerce").fillna(0),
            "nulos": pd.to_numeric(get("VOTOS NULOS"), errors="coerce").fillna(0),
            "impugnados": pd.to_numeric(get("VOTOS IMPUGNADOS"), errors="coerce").fillna(0),
        }
    )
    data[VALID] = data[FP] + data[JP]
    data = data.drop_duplicates("mesa", keep="last")
    return Snapshot(path, timestamp, advance, data)


def attach_snapshot(master: pd.DataFrame, snapshot: Snapshot) -> pd.DataFrame:
    cols = ["mesa", "estado", FP, JP, VALID, "blancos", "nulos", "impugnados"]
    data = master.merge(snapshot.data[cols], on="mesa", how="left")
    data["estado"] = data["estado"].fillna("NO PROCESADA")
    for col in [FP, JP, VALID, "blancos", "nulos", "impugnados"]:
        data[col] = data[col].fillna(0.0)
    data["contada"] = data["estado"].eq(COUNTED)
    return data


def aggregate_stats(data: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    counted = data[data["contada"]].copy()
    if not len(group_cols):
        return pd.DataFrame(
            {
                FP: [counted[FP].sum()],
                JP: [counted[JP].sum()],
                VALID: [counted[VALID].sum()],
                "electores": [counted["electores"].sum()],
                "mesas": [len(counted)],
            },
            index=pd.Index(["NACIONAL"], name="key"),
        )
    return counted.groupby(group_cols, dropna=False).agg(
        fp=(FP, "sum"),
        jp=(JP, "sum"),
        valid=(VALID, "sum"),
        electores=("electores", "sum"),
        mesas=("mesa", "count"),
    )


def shrink_rate(
    numer: pd.Series,
    denom: pd.Series,
    parent: pd.Series | float,
    prior_weight: float,
) -> pd.Series:
    return (numer + prior_weight * parent) / (denom + prior_weight)


def estimate_pending_by_hierarchy(
    data: pd.DataFrame,
    hierarchy: list[tuple[list[str], float]],
) -> tuple[float, float, pd.DataFrame]:
    pending = data[~data["contada"]].copy()
    national = aggregate_stats(data, [])
    national_p = float(national[FP].iloc[0] / max(national[VALID].iloc[0], 1))
    national_valid_rate = float(
        national[VALID].iloc[0] / max(national["electores"].iloc[0], 1)
    )
    pending["p_fp"] = national_p
    pending["valid_rate"] = national_valid_rate

    for group_cols, prior_weight in hierarchy:
        stats = aggregate_stats(data, group_cols).reset_index().rename(
            columns={
                FP: "observed_fp",
                JP: "observed_jp",
                VALID: "observed_valid",
                "electores": "observed_electores",
                "mesas": "observed_mesas",
            }
        )
        keys = group_cols
        merged = pending[keys].merge(stats, on=keys, how="left")
        valid = merged["observed_valid"].fillna(0)
        electores = merged["observed_electores"].fillna(0)
        local_p = shrink_rate(
            merged["observed_fp"].fillna(0),
            valid,
            pending["p_fp"].to_numpy(),
            prior_weight,
        )
        local_valid_rate = shrink_rate(
            valid,
            electores,
            pending["valid_rate"].to_numpy(),
            prior_weight * 1.5,
        )
        has_data = merged["observed_mesas"].fillna(0).to_numpy() > 0
        pending["p_fp"] = np.where(has_data, local_p, pending["p_fp"])
        pending["valid_rate"] = np.where(
            has_data, local_valid_rate, pending["valid_rate"]
        )

    pending["valid_proyectados"] = (
        pending["electores"] * pending["valid_rate"].clip(0.15, 0.95)
    )
    pending["fp_proyectados"] = pending["valid_proyectados"] * pending["p_fp"]
    pending["jp_proyectados"] = (
        pending["valid_proyectados"] - pending["fp_proyectados"]
    )
    return (
        float(pending["fp_proyectados"].sum()),
        float(pending["jp_proyectados"].sum()),
        pending,
    )


def model_projection(
    name: str,
    data: pd.DataFrame,
    pending_fp: float,
    pending_jp: float,
) -> dict[str, float | str]:
    observed_fp = float(data.loc[data["contada"], FP].sum())
    observed_jp = float(data.loc[data["contada"], JP].sum())
    final_fp = observed_fp + pending_fp
    final_jp = observed_jp + pending_jp
    total = final_fp + final_jp
    return {
        "modelo": name,
        "fp_final": final_fp,
        "jp_final": final_jp,
        "fp_pct": final_fp / total if total else math.nan,
        "jp_pct": final_jp / total if total else math.nan,
        "margen_votos_fp": final_fp - final_jp,
        "margen_pp_fp": 100 * (final_fp - final_jp) / total if total else math.nan,
        "validos_pendientes": pending_fp + pending_jp,
    }


def get_model_metadata(data: pd.DataFrame) -> dict:
    """Extrae metadatos detallados de cada modelo para visualización."""
    counted = data[data["contada"]]
    pending = data[~data["contada"]]
    
    # Estadísticas base
    national_stats = aggregate_stats(data, [])
    national_p = float(national_stats[FP].iloc[0] / max(national_stats[VALID].iloc[0], 1))
    national_valid_rate = float(
        national_stats[VALID].iloc[0] / max(national_stats["electores"].iloc[0], 1)
    )
    
    # Jerarquía territorial
    territorial_hierarchy = [
        (["ambito"], 20000),
        (["ambito", "region"], 10000),
        (["ambito", "region", "provincia"], 3500),
        (["ambito", "region", "provincia", "distrito"], 1200),
    ]
    
    # ODPE
    odpe_hierarchy = [
        (["ambito"], 20000),
        (["ambito", "odpe"], 5000),
    ]
    
    # Estadísticas por nivel jerárquico
    hierarchy_stats = {}
    for group_cols, prior_weight in territorial_hierarchy:
        level_name = "_".join(group_cols)
        stats = aggregate_stats(data, group_cols).reset_index()
        hierarchy_stats[level_name] = {
            "niveles": len(stats),
            "prior_weight": prior_weight,
            "mesas_promedio": float(stats["mesas"].mean()) if len(stats) > 0 else 0,
            "electores_promedio": float(stats["electores"].mean()) if len(stats) > 0 else 0,
        }
    
    # Estadísticas ODPE
    odpe_stats_data = aggregate_stats(data, ["ambito", "odpe"]).reset_index()
    odpe_stats = {
        "n_odpes": len(odpe_stats_data),
        "prior_weight": 5000,
        "mesas_promedio": float(odpe_stats_data["mesas"].mean()) if len(odpe_stats_data) > 0 else 0,
    }
    
    # Estadísticas JEE
    jee_count = int(pending["estado"].eq("PARA ENVIO AL JEE").sum())
    
    return {
        "observado": {
            "descripcion": "Solo resume los votos ya contabilizados. No hace proyección.",
            "mesas_contabilizadas": int(counted.shape[0]),
            "votos_validos": float(counted[VALID].sum()),
            "formula": "fp_final = fp_observado",
        },
        "arrastre_nacional": {
            "descripcion": "Imputa a lo pendiente la participación y el reparto nacional observado. Supone ingreso aleatorio.",
            "paquete": "numpy, pandas",
            "parametros": {
                "p_fp_nacional": round(national_p, 6),
                "valid_rate_nacional": round(national_valid_rate, 6),
            },
            "formula": "fp_pendiente = electores_pendientes × valid_rate × p_fp_nacional",
            "limitaciones": "No considera heterogeneidad territorial. Asume que mesas pendientes tienen el mismo comportamiento que las contabilizadas.",
        },
        "jerarquico_territorial": {
            "descripcion": "Estima participación válida y preferencia por mesa usando ámbito, departamento, provincia y distrito. Los grupos pequeños se contraen hacia su nivel superior.",
            "paquete": "numpy, pandas",
            "jerarquia": [
                {
                    "nivel": "_".join(cols),
                    "columnas": cols,
                    "prior_weight": pw,
                    "descripcion": f"Contracción hacia nivel {'/'.join(cols)}",
                }
                for cols, pw in territorial_hierarchy
            ],
            "hierarchy_stats": hierarchy_stats,
            "formula": "p_local = (fp_observado + prior_weight × p_superior) / (valid_observado + prior_weight)",
            "limitaciones": "Asume que mesas pendientes en un territorio se comportan como las ya contabilizadas en ese territorio.",
        },
        "odpe_ponderado": {
            "descripcion": "Repite la lógica de contracción dentro de cada ODPE. Captura patrones específicos de cada oficina descentralizada.",
            "paquete": "numpy, pandas",
            "jerarquia": [
                {
                    "nivel": "_".join(cols),
                    "columnas": cols,
                    "prior_weight": pw,
                    "descripcion": f"Contracción hacia nivel {'/'.join(cols)}",
                }
                for cols, pw in odpe_hierarchy
            ],
            "odpe_stats": odpe_stats,
            "formula": "p_odpe = (fp_observado_odpe + prior_weight × p_ambito) / (valid_observado_odpe + prior_weight)",
            "limitaciones": "Algunas ODPEs pueden tener pocas mesas contabilizadas, lo que aumenta la incertidumbre.",
        },
        "jee_reportado": {
            "descripcion": "Suma los votos ya digitados de las actas enviadas al JEE y proyecta las mesas que todavía no aparecen mediante el modelo jerárquico territorial.",
            "paquete": "numpy, pandas",
            "mesas_jee_digitadas": jee_count,
            "mesas_no_ingresadas": int(pending["estado"].eq("NO PROCESADA").sum()),
            "formula": "fp_final = fp_observado + fp_jee_digitado + fp_no_ingresadas_proyectadas",
            "limitaciones": "Es un escenario de admisión, no una predicción sobre la decisión jurídica del JEE.",
        },
    }


def run_models(data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    counted = data[data["contada"]]
    pending = data[~data["contada"]]
    observed_fp = float(counted[FP].sum())
    observed_jp = float(counted[JP].sum())
    observed_valid = observed_fp + observed_jp
    p_fp = observed_fp / observed_valid
    valid_rate = observed_valid / max(float(counted["electores"].sum()), 1)
    remaining_valid = float((pending["electores"] * valid_rate).sum())

    national = model_projection(
        "Arrastre nacional",
        data,
        remaining_valid * p_fp,
        remaining_valid * (1 - p_fp),
    )
    territorial_fp, territorial_jp, territorial_detail = estimate_pending_by_hierarchy(
        data,
        [
            (["ambito"], 20000),
            (["ambito", "region"], 10000),
            (["ambito", "region", "provincia"], 3500),
            (["ambito", "region", "provincia", "distrito"], 1200),
        ],
    )
    territorial = model_projection(
        "Jerarquico territorial", data, territorial_fp, territorial_jp
    )
    odpe_fp, odpe_jp, odpe_detail = estimate_pending_by_hierarchy(
        data,
        [(["ambito"], 20000), (["ambito", "odpe"], 5000)],
    )
    odpe = model_projection("ODPE ponderado", data, odpe_fp, odpe_jp)
    is_jee = pending["estado"].eq("PARA ENVIO AL JEE")
    reported_pending_fp = float(
        np.where(is_jee, pending[FP], territorial_detail["fp_proyectados"]).sum()
    )
    reported_pending_jp = float(
        np.where(is_jee, pending[JP], territorial_detail["jp_proyectados"]).sum()
    )
    reported_jee = model_projection(
        "JEE reportado + faltantes territoriales",
        data,
        reported_pending_fp,
        reported_pending_jp,
    )
    observed = model_projection("Resultado observado", data, 0, 0)
    return pd.DataFrame([observed, national, territorial, odpe, reported_jee]), {
        "territorial": territorial_detail,
        "odpe": odpe_detail,
    }


def backtest_models(
    master: pd.DataFrame,
    snapshots: list[Snapshot],
    latest_data: pd.DataFrame,
) -> pd.DataFrame:
    final_known = latest_data[latest_data["contada"]]["mesa"]
    evaluation_master = master[master["mesa"].isin(final_known)].copy()
    target = latest_data[latest_data["mesa"].isin(final_known)]
    target_fp = target[FP].sum()
    target_valid = target[VALID].sum()
    target_share = target_fp / target_valid
    rows: list[dict[str, object]] = []

    for snapshot in snapshots:
        if snapshot.advance_label < 10 or snapshot.timestamp >= snapshots[-1].timestamp:
            continue
        data = attach_snapshot(evaluation_master, snapshot)
        if data["contada"].sum() < 100:
            continue
        models, _ = run_models(data)
        for record in models.to_dict("records"):
            if record["modelo"] == "Resultado observado":
                continue
            if record["modelo"] == "JEE reportado + faltantes territoriales":
                continue
            rows.append(
                {
                    "corte": snapshot.timestamp,
                    "avance_archivo": snapshot.advance_label,
                    "modelo": record["modelo"],
                    "fp_pct_proyectado": record["fp_pct"],
                    "fp_pct_objetivo": target_share,
                    "error_pp": 100 * (record["fp_pct"] - target_share),
                    "error_abs_pp": abs(100 * (record["fp_pct"] - target_share)),
                }
            )
    return pd.DataFrame(rows)


def model_weights(backtest: pd.DataFrame) -> dict[str, float]:
    recent = backtest[backtest["avance_archivo"] >= 60].copy()
    if recent.empty:
        recent = backtest.copy()
    mae = recent.groupby("modelo")["error_abs_pp"].mean().clip(lower=0.01)
    inverse = 1 / mae
    weights = inverse / inverse.sum()
    return weights.to_dict()


def add_ensemble(models: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    candidates = models[models["modelo"].isin(weights)].copy()
    candidates["peso"] = candidates["modelo"].map(weights)
    ensemble = {
        "modelo": "Ensamble por backtesting",
        "fp_final": float((candidates["fp_final"] * candidates["peso"]).sum()),
        "jp_final": float((candidates["jp_final"] * candidates["peso"]).sum()),
        "validos_pendientes": float(
            (candidates["validos_pendientes"] * candidates["peso"]).sum()
        ),
    }
    total = ensemble["fp_final"] + ensemble["jp_final"]
    ensemble["fp_pct"] = ensemble["fp_final"] / total
    ensemble["jp_pct"] = ensemble["jp_final"] / total
    ensemble["margen_votos_fp"] = ensemble["fp_final"] - ensemble["jp_final"]
    ensemble["margen_pp_fp"] = 100 * ensemble["margen_votos_fp"] / total
    return pd.concat([models, pd.DataFrame([ensemble])], ignore_index=True)


def simulate_uncertainty(
    models: pd.DataFrame,
    backtest: pd.DataFrame,
    weights: dict[str, float],
    draws: int = 50000,
    seed: int = 20260609,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    observed = models.loc[models["modelo"].eq("Resultado observado")].iloc[0]
    model_names = list(weights)
    probabilities = np.array([weights[name] for name in model_names], dtype=float)
    probabilities = probabilities / probabilities.sum()
    selected = rng.choice(model_names, size=draws, p=probabilities)
    centers = models.set_index("modelo").loc[model_names]
    pending_valid_map = centers["validos_pendientes"].to_dict()
    pending_p_map = (
        (centers["fp_final"] - float(observed["fp_final"]))
        / centers["validos_pendientes"]
    ).to_dict()
    pending_valid = np.array([pending_valid_map[name] for name in selected], dtype=float)
    pending_p = np.array([pending_p_map[name] for name in selected], dtype=float)
    pending_p = np.clip(pending_p, 0.001, 0.999)

    recent_errors = backtest.loc[
        backtest["avance_archivo"] >= 75, "error_pp"
    ].to_numpy()
    calibration_sd_pp = float(np.std(recent_errors, ddof=1)) if len(recent_errors) > 2 else 0.15
    calibration_sd_pp = max(calibration_sd_pp, 0.06)
    concentration = np.clip(pending_valid / 100, 400, 6000)
    p_draw = rng.beta(pending_p * concentration, (1 - pending_p) * concentration)
    p_draw = np.clip(
        p_draw + rng.normal(0, calibration_sd_pp / 100, draws), 0.001, 0.999
    )
    pending_fp_draw = pending_valid * p_draw
    final_fp = float(observed["fp_final"]) + pending_fp_draw
    final_jp = float(observed["jp_final"]) + pending_valid - pending_fp_draw
    margin_votes = final_fp - final_jp
    final_share = final_fp / (final_fp + final_jp)
    return pd.DataFrame(
        {
            "modelo_sorteado": selected,
            "fp_pct": final_share,
            "margen_votos_fp": margin_votes,
        }
    )


def plot_outputs(
    output_dir: Path,
    models: pd.DataFrame,
    backtest: pd.DataFrame,
    simulations: pd.DataFrame,
    snapshots_summary: pd.DataFrame,
) -> None:
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": "#FCFCFD",
            "axes.facecolor": "#FFFFFF",
            "grid.color": COLORS["grid"],
            "axes.labelcolor": COLORS["ink"],
            "text.color": COLORS["ink"],
        },
    )

    plot_models = models[~models["modelo"].eq("Resultado observado")].copy()
    plot_models["margen_miles"] = plot_models["margen_votos_fp"] / 1000
    fig, ax = plt.subplots(figsize=(10, 5.6))
    palette = [
        COLORS["gold"] if value >= 0 else COLORS["jp"]
        for value in plot_models["margen_miles"]
    ]
    sns.barplot(
        data=plot_models,
        y="modelo",
        x="margen_miles",
        hue="modelo",
        palette=dict(zip(plot_models["modelo"], palette)),
        legend=False,
        ax=ax,
    )
    ax.axvline(0, color=COLORS["ink"], linewidth=1)
    ax.set_title("Margen final proyectado por modelo", loc="left", weight="bold")
    ax.set_xlabel("Miles de votos: positivo favorece a Keiko; negativo a Sanchez")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(output_dir / "proyeccion_modelos.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.6))
    for model, group in backtest.groupby("modelo"):
        ax.plot(
            group["avance_archivo"],
            group["error_abs_pp"],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=model,
        )
    ax.set_title("Error retrospectivo de las proyecciones", loc="left", weight="bold")
    ax.set_xlabel("Avance indicado en el archivo (%)")
    ax.set_ylabel("Error absoluto en la cuota de Keiko (puntos porcentuales)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_dir / "backtesting_modelos.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.6))
    sns.histplot(
        simulations["margen_votos_fp"] / 1000,
        bins=60,
        color=COLORS["gold"],
        edgecolor=COLORS["ink"],
        linewidth=0.3,
        ax=ax,
    )
    ax.axvline(0, color=COLORS["ink"], linewidth=1.2)
    ax.set_title("Distribucion simulada del margen final", loc="left", weight="bold")
    ax.set_xlabel("Miles de votos: positivo favorece a Keiko; negativo a Sanchez")
    ax.set_ylabel("Simulaciones")
    fig.tight_layout()
    fig.savefig(output_dir / "incertidumbre_margen.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.plot(
        snapshots_summary["timestamp"],
        snapshots_summary["margen_pp_fp"],
        color=COLORS["fp"],
        marker="o",
        markersize=3,
    )
    ax.axhline(0, color=COLORS["ink"], linewidth=1)
    ax.set_title("Evolucion del margen observado", loc="left", weight="bold")
    ax.set_xlabel("Corte ONPE")
    ax.set_ylabel("Margen de Keiko sobre votos validos (pp)")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_dir / "evolucion_margen.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def fmt_int(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def fmt_pct(value: float, digits: int = 3) -> str:
    return f"{100 * value:.{digits}f}%"


def render_report(
    output_dir: Path,
    latest: Snapshot,
    latest_data: pd.DataFrame,
    models: pd.DataFrame,
    backtest: pd.DataFrame,
    weights: dict[str, float],
    simulations: pd.DataFrame,
) -> None:
    counted = latest_data[latest_data["contada"]]
    pending = latest_data[~latest_data["contada"]]
    observed = models.loc[models["modelo"].eq("Resultado observado")].iloc[0]
    ensemble = models.loc[models["modelo"].eq("Ensamble por backtesting")].iloc[0]
    reported_jee = models.loc[
        models["modelo"].eq("JEE reportado + faltantes territoriales")
    ].iloc[0]
    winner = "Keiko Fujimori" if ensemble["margen_votos_fp"] > 0 else "Sanchez"
    technical_tie = abs(float(ensemble["margen_votos_fp"])) < 10000
    ensemble_read = (
        f"un empate tecnico, con margen central de {fmt_int(abs(ensemble['margen_votos_fp']))} "
        f"votos favorable a {winner}"
        if technical_tie
        else f"como ganador final a {winner}, con un margen central de "
        f"{fmt_int(abs(ensemble['margen_votos_fp']))} votos"
    )
    probability_fp = float((simulations["margen_votos_fp"] > 0).mean())
    lower, median, upper = simulations["margen_votos_fp"].quantile([0.025, 0.5, 0.975])
    pending_valid = float(ensemble["validos_pendientes"])
    required_jp_share = (
        0.5 + float(observed["margen_votos_fp"]) / (2 * pending_valid)
        if pending_valid
        else math.nan
    )
    required_fp_share = 1 - required_jp_share
    observed_leader = (
        "Keiko" if observed["margen_votos_fp"] > 0 else "Sanchez"
    )
    model_rows = []
    for row in models.to_dict("records"):
        model_rows.append(
            "<tr>"
            f"<td>{row['modelo']}</td>"
            f"<td>{fmt_pct(row['fp_pct'])}</td>"
            f"<td>{fmt_pct(row['jp_pct'])}</td>"
            f"<td>{fmt_int(row['margen_votos_fp'])}</td>"
            "</tr>"
        )
    weight_text = ", ".join(
        f"{name}: {100 * weight:.1f}%" for name, weight in sorted(weights.items())
    )
    backtest_mae = (
        backtest[backtest["avance_archivo"] >= 60]
        .groupby("modelo")["error_abs_pp"]
        .mean()
        .sort_values()
    )
    mae_text = ", ".join(f"{name}: {value:.3f} pp" for name, value in backtest_mae.items())

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Proyeccion electoral ONPE 2026</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f8fafc; color: #1f2430; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 36px 22px 64px; }}
    header, section {{ margin-bottom: 34px; }}
    h1, h2 {{ line-height: 1.15; margin: 0 0 12px; }}
    p, li {{ line-height: 1.6; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #e6e8f0; border-radius: 12px; padding: 16px; }}
    .value {{ font-size: 26px; font-weight: 700; margin-top: 6px; }}
    .muted {{ color: #6f768a; font-size: 14px; }}
    .warning {{ border-left: 5px solid #f0986e; background: #ffedde; padding: 14px 16px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ text-align: right; padding: 10px; border-bottom: 1px solid #e6e8f0; }}
    th:first-child, td:first-child {{ text-align: left; }}
    img {{ width: 100%; height: auto; background: white; border-radius: 8px; }}
    code {{ background: #eef1f6; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
<main data-report-audience="technical">
  <header data-contract-section="title">
    <h1>Proyeccion electoral ONPE 2026</h1>
    <p class="muted">Corte: {latest.timestamp:%d/%m/%Y %H:%M} | Archivo: {latest.path.name}</p>
  </header>

  <section data-contract-section="technical-summary">
    <h2>Resumen tecnico</h2>
    <p><strong>Sanchez lidera actualmente el resultado oficial contabilizado por
    {fmt_int(abs(observed['margen_votos_fp']))} votos.</strong> Por separado, el ensamble estadistico
    proyecta {ensemble_read}.
    La probabilidad condicional de Keiko, mezclando los modelos segun su backtesting, es {probability_fp:.1%}.</p>
    <div class="kpis">
      <div class="card"><div class="muted">Lider oficial contabilizado</div><div class="value">Sanchez +{fmt_int(abs(observed['margen_votos_fp']))}</div></div>
      <div class="card"><div class="muted">Actas contabilizadas</div><div class="value">{counted.shape[0]:,}</div></div>
      <div class="card"><div class="muted">Actas pendientes/JEE</div><div class="value">{pending.shape[0]:,}</div></div>
      <div class="card"><div class="muted">JEE digitado + faltantes proyectadas</div><div class="value">{('Keiko' if reported_jee['margen_votos_fp'] > 0 else 'Sanchez')} +{fmt_int(abs(reported_jee['margen_votos_fp']))}</div></div>
    </div>
    <div class="warning"><strong>Advertencia:</strong> esta es una proyeccion estadistica, no una prediccion
    sobre decisiones del JEE. Las actas observadas no son una muestra aleatoria y pueden cambiar por
    resoluciones, anulaciones o correcciones.</div>
  </section>

  <section data-contract-section="key-findings">
    <h2>La eleccion sigue dentro de un margen muy estrecho</h2>
    <p>En las actas oficialmente contabilizadas, {observed_leader} lidera: Keiko tiene
    {fmt_pct(observed['fp_pct'])} y Sanchez {fmt_pct(observed['jp_pct'])}. Para revertir ese resultado,
    Keiko necesita aproximadamente {fmt_pct(required_fp_share, 2)} de los votos validos pendientes;
    los votos ya digitados en las actas JEE le asignan una proporcion suficiente para terminar
    {fmt_int(reported_jee['margen_votos_fp'])} votos adelante si fueran admitidos sin cambios.</p>
    <figure><img src="proyeccion_modelos.png" alt="Proyeccion por modelo"></figure>
    <p>La dispersion entre modelos representa diferencias en como se trata la composicion territorial
    de las actas pendientes. El intervalo mixto de 95% va de {fmt_int(lower)} a {fmt_int(upper)}
    votos para el margen de Keiko. El ensamble pondera cada proyeccion segun su error en cortes anteriores.</p>
    <figure><img src="incertidumbre_margen.png" alt="Distribucion simulada del margen"></figure>
  </section>

  <section data-contract-section="scope-data-and-metric-definitions">
    <h2>Alcance, datos y definiciones</h2>
    <p>Se usa la mesa como unidad. Voto valido equivale a Fuerza Popular mas Juntos por el Peru.
    El universo proviene de la maestra de mesas y el estado/voto de cada corte proviene de los CSV ONPE.
    En el ultimo corte hay {fmt_int(counted[VALID].sum())} votos validos contabilizados y
    {fmt_int(pending['electores'].sum())} electores habiles asociados a actas no contabilizadas.</p>
  </section>

  <section data-contract-section="methodology">
    <h2>Modelos y validacion retrospectiva</h2>
    <table><thead><tr><th>Modelo</th><th>Keiko</th><th>Sanchez</th><th>Margen votos Keiko</th></tr></thead>
    <tbody>{''.join(model_rows)}</tbody></table>
    <p><strong>Arrastre nacional:</strong> mantiene participacion y reparto nacional observado.
    <strong>Jerarquico territorial:</strong> estima cada mesa pendiente mediante distrito, provincia,
    departamento y ambito, con contraccion hacia niveles superiores.
    <strong>ODPE ponderado:</strong> usa el patron observado dentro de cada ODPE.
    <strong>JEE reportado + faltantes territoriales:</strong> usa los votos digitados de las actas
    enviadas al JEE y proyecta territorialmente las mesas aun no presentes en el extracto.
    <strong>Ensamble:</strong> pesos por error retrospectivo desde 60% de
    avance: {weight_text}.</p>
    <figure><img src="backtesting_modelos.png" alt="Backtesting de modelos"></figure>
    <p>Error absoluto medio reciente: {mae_text}.</p>
    <figure><img src="evolucion_margen.png" alt="Evolucion del margen observado"></figure>
  </section>

  <section data-contract-section="limitations-uncertainty-and-robustness-checks">
    <h2>Limitaciones e incertidumbre</h2>
    <ul>
      <li>El backtesting usa como objetivo el ultimo resultado contabilizado disponible, no un resultado final certificado.</li>
      <li>Las actas enviadas al JEE tienen un mecanismo de seleccion distinto al ingreso ordinario de actas.</li>
      <li>La probabilidad de victoria es condicional a los modelos y no incorpora decisiones juridicas extraordinarias.</li>
      <li>La cobertura ODPE es 99.84%; 147 mesas no tienen cruce ODPE, aunque conservan su geografia ONPE.</li>
    </ul>
  </section>

  <section data-contract-section="recommended-next-steps">
    <h2>Siguiente actualizacion</h2>
    <p>Al agregar un nuevo CSV a <code>insumos/descargas_modulo</code>, ejecutar
    <code>python3 modelos/oraculo_onpe.py</code>. El pipeline vuelve a seleccionar el corte mas reciente,
    recalibra el backtesting y reemplaza este informe.</p>
  </section>

  <section data-contract-section="further-questions">
    <h2>Pregunta que puede cambiar la conclusion</h2>
    <p>La principal incertidumbre es si las actas que salen del JEE conservan el patron electoral de
    mesas comparables o presentan un sesgo sistematico por tipo de observacion y territorio.</p>
  </section>
</main>
</body>
</html>"""
    (output_dir / "reporte_oraculo_onpe.html").write_text(html, encoding="utf-8")


def save_cache(project: Path, cache_data: dict) -> Path:
    """Guarda resultados de modelos en cache JSON."""
    cache_dir = project / "modelos" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "modelos_cache.json"
    cache_path.write_text(
        json.dumps(cache_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return cache_path


def load_cache(project: Path) -> dict | None:
    """Carga resultados de modelos desde cache JSON."""
    cache_path = project / "modelos" / "cache" / "modelos_cache.json"
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_latest_csv(project: Path) -> tuple[datetime, Path] | None:
    """Obtiene el corte electoral más reciente disponible."""
    input_dir = project / "insumos" / "descargas_modulo"
    if not input_dir.exists():
        return None
    csv_files = list(input_dir.glob("*.csv"))
    if not csv_files:
        return None
    dated_files = [(parse_snapshot_metadata(path)[0], path) for path in csv_files]
    return max(dated_files, key=lambda item: (item[0], item[1].stat().st_mtime_ns))


def should_run_models(project: Path, force: bool = False) -> bool:
    """Determina si es necesario re-ejecutar los modelos."""
    if force:
        return True
    cache = load_cache(project)
    if not cache:
        return True
    latest_csv = get_latest_csv(project)
    if not latest_csv:
        return True
    latest_timestamp, latest_path = latest_csv
    cache_timestamp = cache.get("latest_csv_timestamp")
    if not cache_timestamp or not cache.get("latest_file"):
        return True
    cache_time = datetime.fromisoformat(cache_timestamp)
    if latest_timestamp != cache_time or latest_path.name != cache["latest_file"]:
        return True
    cached_size = cache.get("latest_csv_size")
    cached_mtime = cache.get("latest_csv_mtime_ns")
    if cached_size is None or cached_mtime is None:
        generated_at = cache.get("generated_at")
        if not generated_at:
            return True
        generated_time = datetime.fromisoformat(generated_at).timestamp()
        return latest_path.stat().st_mtime > generated_time
    stat = latest_path.stat()
    return stat.st_size != cached_size or stat.st_mtime_ns != cached_mtime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--draws", type=int, default=50000)
    parser.add_argument("--force", action="store_true", help="Forzar re-ejecucion de modelos aunque haya cache")
    parser.add_argument("--cache-only", action="store_true", help="Solo generar cache, no generar reportes")
    parser.add_argument(
        "--needs-refresh",
        action="store_true",
        help="Termina con código 0 si hay data nueva y 1 si el cache está vigente",
    )
    args = parser.parse_args()
    project = args.project_dir.resolve()
    input_dir = project / "insumos" / "descargas_modulo"
    master_path = project / "insumos" / "maestras" / "Mesa por Mesa SEP2026 25.05.26.xlsx"
    output_dir = project / "modelos" / "salidas"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.needs_refresh:
        needs_refresh = should_run_models(project, force=args.force)
        print("nueva-data" if needs_refresh else "cache-vigente")
        raise SystemExit(0 if needs_refresh else 1)
    
    # Verificar si es necesario ejecutar modelos
    if not should_run_models(project, force=args.force):
        print("Cache vigente. No se requiere re-ejecutar modelos.")
        print("Usa --force para forzar re-ejecucion.")
        return

    full_master = load_master(master_path)
    snapshots = sorted(
        (load_snapshot(path) for path in input_dir.glob("*.csv")),
        key=lambda item: item.timestamp,
    )
    if not snapshots:
        raise SystemExit("No se encontraron CSV en insumos/descargas_modulo")
    latest = snapshots[-1]
    master = full_master
    latest_data = attach_snapshot(master, latest)
    models, details = run_models(latest_data)
    model_metadata = get_model_metadata(latest_data)
    backtest = backtest_models(master, snapshots, latest_data)
    weights = model_weights(backtest)
    models = add_ensemble(models, weights)
    simulations = simulate_uncertainty(
        models, backtest, weights, draws=args.draws
    )

    snapshots_rows = []
    for snapshot in snapshots:
        data = attach_snapshot(master, snapshot)
        counted = data[data["contada"]]
        valid = counted[VALID].sum()
        snapshots_rows.append(
            {
                "timestamp": snapshot.timestamp,
                "avance_archivo": snapshot.advance_label,
                "actas_contabilizadas": int(counted.shape[0]),
                "fp": counted[FP].sum(),
                "jp": counted[JP].sum(),
                "fp_pct": counted[FP].sum() / valid if valid else math.nan,
                "margen_pp_fp": 100 * (counted[FP].sum() - counted[JP].sum()) / valid
                if valid
                else math.nan,
            }
        )
    snapshots_summary = pd.DataFrame(snapshots_rows)
    plot_outputs(output_dir, models, backtest, simulations, snapshots_summary)
    render_report(
        output_dir, latest, latest_data, models, backtest, weights, simulations
    )

    models.to_csv(output_dir / "proyecciones_modelos.csv", index=False)
    backtest.to_csv(output_dir / "backtesting_modelos.csv", index=False)
    snapshots_summary.to_csv(output_dir / "evolucion_cortes.csv", index=False)
    details["territorial"].to_csv(
        output_dir / "detalle_actas_pendientes_territorial.csv", index=False
    )
    pending_by_odpe = (
        details["territorial"]
        .groupby(["ambito", "region", "odpe"], dropna=False)
        .agg(
            actas_pendientes=("mesa", "count"),
            electores_pendientes=("electores", "sum"),
            validos_proyectados=("valid_proyectados", "sum"),
            fp_proyectados=("fp_proyectados", "sum"),
            jp_proyectados=("jp_proyectados", "sum"),
        )
        .reset_index()
    )
    pending_by_odpe["margen_proyectado_fp"] = (
        pending_by_odpe["fp_proyectados"] - pending_by_odpe["jp_proyectados"]
    )
    pending_by_odpe.sort_values(
        "electores_pendientes", ascending=False
    ).to_csv(output_dir / "pendientes_por_odpe.csv", index=False)
    
    # Exportar metadatos de modelos para el dashboard
    (output_dir / "model_metadata.json").write_text(
        json.dumps(model_metadata, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    
    # Exportar detalles territoriales para visualizaciones
    territorial_summary = (
        details["territorial"]
        .groupby(["ambito", "region"], dropna=False)
        .agg(
            mesas_pendientes=("mesa", "count"),
            electores_pendientes=("electores", "sum"),
            fp_proyectados=("fp_proyectados", "sum"),
            jp_proyectados=("jp_proyectados", "sum"),
        )
        .reset_index()
    )
    territorial_summary["margen_proyectado"] = (
        territorial_summary["fp_proyectados"] - territorial_summary["jp_proyectados"]
    )
    territorial_summary["p_fp_proyectado"] = (
        territorial_summary["fp_proyectados"]
        / (territorial_summary["fp_proyectados"] + territorial_summary["jp_proyectados"])
    )
    territorial_summary.sort_values(
        "mesas_pendientes", ascending=False
    ).to_csv(output_dir / "resumen_territorial.csv", index=False)
    summary = {
        "latest_file": latest.path.name,
        "latest_timestamp": latest.timestamp.isoformat(),
        "master_mesas": int(master.shape[0]),
        "counted_mesas": int(latest_data["contada"].sum()),
        "pending_mesas": int((~latest_data["contada"]).sum()),
        "weights": weights,
        "probability_keiko": float((simulations["margen_votos_fp"] > 0).mean()),
        "ensemble": models.loc[
            models["modelo"].eq("Ensamble por backtesting")
        ].iloc[0].to_dict(),
        "simulation_margin_quantiles": simulations["margen_votos_fp"]
        .quantile([0.025, 0.5, 0.975])
        .to_dict(),
        "model_metadata": model_metadata,
    }
    (output_dir / "resumen_modelo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    
    # Guardar cache completo para el dashboard
    cache_data = {
        "generated_at": datetime.now().isoformat(),
        "latest_csv_timestamp": latest.timestamp.isoformat(),
        "latest_file": latest.path.name,
        "latest_csv_size": latest.path.stat().st_size,
        "latest_csv_mtime_ns": latest.path.stat().st_mtime_ns,
        "models": models.to_dict("records"),
        "backtest": backtest.to_dict("records"),
        "weights": weights,
        "simulations": simulations.to_dict("records"),
        "snapshots_summary": snapshots_summary.to_dict("records"),
        "territorial_details": details["territorial"].to_dict("records"),
        "model_metadata": model_metadata,
        "summary": summary,
    }
    cache_path = save_cache(project, cache_data)
    print(f"Cache guardado en: {cache_path}")
    
    if args.cache_only:
        print("Modo cache-only: no se generaron reportes.")
        return
    
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=float))


if __name__ == "__main__":
    main()

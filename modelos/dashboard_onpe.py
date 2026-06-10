#!/usr/bin/env python3
"""Generador del panel HTML para seguimiento y proyección electoral."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import oraculo_onpe as oracle


def compact_records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.replace({np.nan: None})
    return clean.to_dict("records")


def simulations_from_cache(raw: object) -> pd.DataFrame:
    if isinstance(raw, list):
        return pd.DataFrame(raw)
    if isinstance(raw, dict):
        margins = raw.get("margen_votos_fp", [])
        return pd.DataFrame(
            {
                "margen_votos_fp": margins,
                "modelo_sorteado": ["Ensamble"] * len(margins),
            }
        )
    return pd.DataFrame()


def spanish_datetime(value: datetime) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{value.day} de {months[value.month - 1]} de {value.year}, {value:%H:%M}"


def build_dashboard(project: Path) -> Path:
    input_dir = project / "insumos" / "descargas_modulo"
    master_path = (
        project / "insumos" / "maestras" / "Mesa por Mesa SEP2026 25.05.26.xlsx"
    )
    output_dir = project / "modelos" / "panel"
    output_dir.mkdir(parents=True, exist_ok=True)

    master = oracle.load_master(master_path)
    snapshots = sorted(
        (oracle.load_snapshot(path) for path in input_dir.glob("*.csv")),
        key=lambda item: item.timestamp,
    )
    if not snapshots:
        raise SystemExit("No se encontraron CSV en insumos/descargas_modulo")
    latest = snapshots[-1]
    latest_data = oracle.attach_snapshot(master, latest)
    latest_data["status"] = np.select(
        [
            latest_data["estado"].eq(oracle.COUNTED),
            latest_data["estado"].eq("PARA ENVIO AL JEE"),
        ],
        ["Contabilizada", "Enviada al JEE"],
        default="No ingresada",
    )

    progress_series = []
    for snapshot in snapshots:
        data = oracle.attach_snapshot(master, snapshot)
        counted_snapshot = data["estado"].eq(oracle.COUNTED)
        jee_snapshot = data["estado"].eq("PARA ENVIO AL JEE")
        valid = data.loc[counted_snapshot, oracle.VALID].sum()
        progress_series.append(
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "label": snapshot.timestamp.strftime("%d/%m %H:%M"),
                "avance_archivo": snapshot.advance_label,
                "contabilizadas": int(counted_snapshot.sum()),
                "jee": int(jee_snapshot.sum()),
                "no_ingresadas": int((~counted_snapshot & ~jee_snapshot).sum()),
                "pct_contabilizadas": 100 * counted_snapshot.mean(),
                "pct_jee": 100 * jee_snapshot.mean(),
                "pct_no_ingresadas": 100 * (~counted_snapshot & ~jee_snapshot).mean(),
                "margen_observado_fp": float(
                    data.loc[counted_snapshot, oracle.FP].sum()
                    - data.loc[counted_snapshot, oracle.JP].sum()
                ),
                "fp_pct_observado": float(
                    data.loc[counted_snapshot, oracle.FP].sum() / valid
                    if valid else np.nan
                ),
            }
        )

    model_series_path = output_dir / "serie_modelos.csv"
    if model_series_path.exists():
        prior_model_series = pd.read_csv(model_series_path).to_dict("records")
    else:
        prior_model_series = []
    valid_timestamps = {snapshot.timestamp.isoformat() for snapshot in snapshots}
    model_series = [
        row for row in prior_model_series if row.get("timestamp") in valid_timestamps
    ]
    modeled_timestamps = {row.get("timestamp") for row in model_series}
    for snapshot in snapshots:
        timestamp = snapshot.timestamp.isoformat()
        if timestamp in modeled_timestamps:
            continue
        data = oracle.attach_snapshot(master, snapshot)
        if data["estado"].eq(oracle.COUNTED).sum() < 100:
            continue
        models_iter, _ = oracle.run_models(data)
        for row in models_iter.to_dict("records"):
            if row["modelo"] == "Resultado observado":
                continue
            model_series.append(
                {
                    "timestamp": timestamp,
                    "label": snapshot.timestamp.strftime("%d/%m %H:%M"),
                    "avance_archivo": snapshot.advance_label,
                    "modelo": row["modelo"],
                    "margen_votos_fp": row["margen_votos_fp"],
                    "fp_pct": row["fp_pct"],
                }
            )
    model_series = (
        pd.DataFrame(model_series)
        .drop_duplicates(["timestamp", "modelo"], keep="last")
        .sort_values(["timestamp", "modelo"])
        .to_dict("records")
    )

    cache = oracle.load_cache(project)
    if cache and not oracle.should_run_models(project, force=False):
        print(f"Usando caché del {cache['generated_at']}")
        if "latest_csv_size" not in cache or "latest_csv_mtime_ns" not in cache:
            cache["latest_csv_size"] = latest.path.stat().st_size
            cache["latest_csv_mtime_ns"] = latest.path.stat().st_mtime_ns
            oracle.save_cache(project, cache)
        models = pd.DataFrame(cache["models"])
        backtest = pd.DataFrame(cache["backtest"])
        weights = cache["weights"]
        simulations = simulations_from_cache(cache["simulations"])
        model_metadata = cache["model_metadata"]
        details = {"territorial": pd.DataFrame(cache["territorial_details"])}
    else:
        print("Caché no disponible o desactualizado. Ejecutando modelos...")
        models, details = oracle.run_models(latest_data)
        model_metadata = oracle.get_model_metadata(latest_data)
        backtest = oracle.backtest_models(master, snapshots, latest_data)
        weights = oracle.model_weights(backtest)
        models = oracle.add_ensemble(models, weights)
        simulations = oracle.simulate_uncertainty(
            models, backtest, weights, draws=50000
        )
        
        # Guardar cache para próximas ejecuciones
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
            "snapshots_summary": progress_series,
            "territorial_details": details["territorial"].to_dict("records"),
            "model_metadata": model_metadata,
        }
        oracle.save_cache(project, cache_data)
        print("Caché generado y guardado")

    current_models = models
    
    # Preparar datos detallados de modelos para visualización interactiva
    model_details = {
        "arrastre_nacional": {
            "descripcion": "Proyecta mesas pendientes asumiendo que mantienen la participación y distribución de votos observadas a nivel nacional.",
            "metodologia": "Aplica las tasas nacionales observadas (Keiko/total válidos y válidos/electores) a todas las mesas pendientes.",
            "paquete": "pandas + numpy",
            "formula": "p_fp_nacional = Σ FP contabilizado / Σ válidos contabilizado",
            "fortalezas": "Simple, robusto, sin supuestos territoriales",
            "debilidades": "Ignora heterogeneidad geográfica",
            "hierarchy_levels": 1,
        },
        "jerarquico_territorial": {
            "descripcion": "Estimador jerárquico bayesiano que contrae estimaciones distritales hacia niveles superiores cuando hay pocos datos.",
            "metodologia": "Shrinkage estimator con contracción ponderada: distrito → provincia → región → ámbito → nacional.",
            "paquete": "numpy (custom shrinkage)",
            "formula": "p_local = (FP_obs + w·p_padre) / (válidos_obs + w)",
            "fortalezas": "Captura heterogeneidad territorial, estable con pocas observaciones",
            "debilidades": "Requiere jerarquía bien definida, sensibilidad a pesos de contracción",
            "hierarchy_levels": 4,
            "prior_weights": [20000, 10000, 3500, 1200],
        },
        "odpe_ponderado": {
            "descripcion": "Usa patrones observados dentro de cada Oficina Descentralizada de Procesos Electorales (ODPE).",
            "metodologia": "Aplica tasas específicas por ODPE con contracción hacia el promedio nacional cuando hay pocos datos.",
            "paquete": "pandas + numpy (custom shrinkage)",
            "formula": "p_odpe = (FP_odpe + w·p_nacional) / (válidos_odpe + w)",
            "fortalezas": "Respeta jurisdicciones ONPE, útil para monitoreo operativo",
            "debilidades": "ODPEs no son unidades políticas naturales",
            "hierarchy_levels": 2,
            "prior_weights": [20000, 5000],
        },
        "jee_reportado": {
            "descripcion": "Combina votos ya digitados en actas JEE con proyección territorial de mesas aún no ingresadas.",
            "metodologia": "Para actas JEE: usa votos observados. Para no ingresadas: proyección jerárquica territorial.",
            "paquete": "pandas + numpy",
            "formula": "Final = FP_JEE + FP_no_ingresadas_proyectadas",
            "fortalezas": "Incorpora información de actas observadas",
            "debilidades": "Asume que actas JEE no cambiarán por resolución",
            "hierarchy_levels": 2,
        },
        "ensamble": {
            "descripcion": "Combinación ponderada de modelos según error retrospectivo en backtesting.",
            "metodologia": "Pesos inversamente proporcionales al error absoluto medio (MAE) desde 60% de avance.",
            "paquete": "numpy (optimización de pesos)",
            "formula": "w_i = (1/MAE_i) / Σ(1/MAE_j)",
            "fortalezas": "Robustez, aprovecha fortalezas de cada modelo",
            "debilidades": "Sensible a calidad del backtesting",
            "weights": weights,
        },
    }
    
    # Preparar backtest detallado para visualización
    backtest_detailed = backtest.copy()
    backtest_detailed["error_pp"] = backtest_detailed["error_abs_pp"]
    backtest_by_model = (
        backtest_detailed.groupby("modelo")
        .agg(
            mae=("error_pp", "mean"),
            rmse=("error_pp", lambda x: np.sqrt((x ** 2).mean())),
            max_error=("error_pp", "max"),
            std_error=("error_pp", "std"),
            n_cortes=("error_pp", "count"),
        )
        .reset_index()
    )
    
    # Preparar datos para visualizaciones de modelos
    backtest_summary = (
        backtest.groupby("modelo")
        .agg(
            mae=("error_abs_pp", "mean"),
            rmse=("error_abs_pp", lambda x: np.sqrt((x ** 2).mean())),
            n_cortes=("error_abs_pp", "count"),
        )
        .reset_index()
    )
    
    # Contribución territorial al margen
    territorial_contrib = (
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
    territorial_contrib["margen_proyectado"] = (
        territorial_contrib["fp_proyectados"] - territorial_contrib["jp_proyectados"]
    )
    territorial_contrib["contribucion_margen_pct"] = (
        100 * territorial_contrib["margen_proyectado"]
        / territorial_contrib["margen_proyectado"].abs().sum()
    )
    territorial_contrib = territorial_contrib.sort_values(
        "contribucion_margen_pct", ascending=False
    )

    counted = latest_data["status"].eq("Contabilizada")
    jee = latest_data["status"].eq("Enviada al JEE")
    missing = latest_data["status"].eq("No ingresada")
    official_fp = int(latest_data.loc[counted, oracle.FP].sum())
    official_jp = int(latest_data.loc[counted, oracle.JP].sum())

    geography = (
        latest_data.groupby(["ambito", "region"], dropna=False)
        .agg(
            total=("mesa", "count"),
            contabilizadas=("status", lambda x: int((x == "Contabilizada").sum())),
            jee=("status", lambda x: int((x == "Enviada al JEE").sum())),
            no_ingresadas=("status", lambda x: int((x == "No ingresada").sum())),
            electores_pendientes=(
                "electores",
                lambda x: int(
                    x[
                        latest_data.loc[x.index, "status"].isin(
                            ["Enviada al JEE", "No ingresada"]
                        )
                    ].sum()
                ),
            ),
        )
        .reset_index()
    )
    geography["pendientes"] = geography["jee"] + geography["no_ingresadas"]
    geography["pct_contabilizadas"] = (
        100 * geography["contabilizadas"] / geography["total"]
    )
    geography = geography.sort_values(
        ["pendientes", "electores_pendientes"], ascending=False
    )

    odpe = (
        latest_data.groupby(["ambito", "region", "odpe"], dropna=False)
        .agg(
            total=("mesa", "count"),
            contabilizadas=("status", lambda x: int((x == "Contabilizada").sum())),
            jee=("status", lambda x: int((x == "Enviada al JEE").sum())),
            no_ingresadas=("status", lambda x: int((x == "No ingresada").sum())),
            electores_pendientes=(
                "electores",
                lambda x: int(
                    x[
                        latest_data.loc[x.index, "status"].isin(
                            ["Enviada al JEE", "No ingresada"]
                        )
                    ].sum()
                ),
            ),
        )
        .reset_index()
    )
    odpe["pendientes"] = odpe["jee"] + odpe["no_ingresadas"]
    odpe["pct_contabilizadas"] = 100 * odpe["contabilizadas"] / odpe["total"]
    odpe = odpe.sort_values(
        ["pendientes", "electores_pendientes"], ascending=False
    )

    current_model_rows = []
    for row in current_models.to_dict("records"):
        margin = float(row["margen_votos_fp"])
        current_model_rows.append(
            {
                "modelo": row["modelo"],
                "ganador": "Keiko" if margin > 0 else "Sánchez",
                "margen_votos_fp": margin,
                "fp_pct": 100 * row["fp_pct"],
                "jp_pct": 100 * row["jp_pct"],
            }
        )

    ensemble = current_models[
        current_models["modelo"].eq("Ensamble por backtesting")
    ].iloc[0]
    quantiles = simulations["margen_votos_fp"].quantile([0.025, 0.5, 0.975])
    summary = {
        "latest_file": latest.path.name,
        "latest_label": spanish_datetime(latest.timestamp),
        "total_mesas": int(len(master)),
        "contabilizadas": int(counted.sum()),
        "jee": int(jee.sum()),
        "no_ingresadas": int(missing.sum()),
        "pct_contabilizadas": 100 * counted.mean(),
        "pct_jee": 100 * jee.mean(),
        "pct_no_ingresadas": 100 * missing.mean(),
        "official_fp": official_fp,
        "official_jp": official_jp,
        "official_margin_fp": official_fp - official_jp,
        "ensemble_margin_fp": float(ensemble["margen_votos_fp"]),
        "probability_keiko": float((simulations["margen_votos_fp"] > 0).mean()),
        "interval_low": float(quantiles.loc[0.025]),
        "interval_median": float(quantiles.loc[0.5]),
        "interval_high": float(quantiles.loc[0.975]),
    }

    pd.DataFrame(progress_series).to_csv(
        output_dir / "serie_avance.csv", index=False
    )
    pd.DataFrame(model_series).to_csv(
        output_dir / "serie_modelos.csv", index=False
    )
    geography.to_csv(output_dir / "pendientes_territorio.csv", index=False)
    odpe.to_csv(output_dir / "pendientes_odpe.csv", index=False)
    pd.DataFrame(current_model_rows).to_csv(
        output_dir / "modelos_actuales.csv", index=False
    )
    backtest_summary.to_csv(output_dir / "backtesting_resumen.csv", index=False)
    territorial_contrib.to_csv(output_dir / "contribucion_territorial.csv", index=False)

    payload = {
        "summary": summary,
        "progress": progress_series,
        "modelSeries": model_series,
        "geography": compact_records(geography),
        "odpe": compact_records(odpe),
        "models": current_model_rows,
        "modelMetadata": model_metadata,
        "modelDetails": model_details,
        "backtestSummary": compact_records(backtest_summary),
        "backtestDetailed": compact_records(backtest_by_model),
        "territorialContrib": compact_records(territorial_contrib),
        "simulations": [
            {
                "margen_votos_fp": float(v),
                "modelo": s,
            }
            for v, s in zip(
                simulations["margen_votos_fp"].head(5000),
                simulations["modelo_sorteado"].head(5000),
            )
        ],
        "weights": weights,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    html = DASHBOARD_HTML.replace("__DATA__", payload_json)
    output_path = output_dir / "panel_electoral_onpe.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


DASHBOARD_HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pronósticos de la segunda vuelta presidencial Perú 2026</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root{--bg:#f6f7fb;--panel:#fff;--ink:#1f2430;--muted:#6f768a;--grid:#e6e8f0;--blue:#5477c4;--blue-light:#cedffe;--keiko:#f0986e;--sanchez:#71b436;--gold:#d4a72c;--purple:#8a5aa8;--pink:#bd569b;--shadow:0 10px 28px rgba(31,36,48,.06);--radius:14px}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Aptos,"Segoe UI",Arial,sans-serif}
main{max-width:1440px;margin:auto;padding:28px}.header{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:20px}
h1{font-size:30px;margin:0 0 7px;white-space:nowrap}.subtitle,.small{color:var(--muted);font-size:14px}.source-note{margin-top:4px;color:var(--muted);font-size:12px}.header-summary{display:flex;flex-direction:column;align-items:flex-end;gap:8px}.vote-badges{display:flex;justify-content:flex-end;gap:8px}.badge{padding:8px 11px;border-radius:999px;font-size:14px;font-weight:700;white-space:nowrap}.badge.keiko{background:#ffedde;border:1px solid var(--keiko);color:#8c4328}.badge.sanchez{background:#edf7e4;border:1px solid var(--sanchez);color:#3f6f1e}.badge.difference{background:#fff;border:1px solid var(--grid);color:var(--ink)}
.cards{display:grid;gap:12px;margin-bottom:16px}.cards.five-up{grid-template-columns:repeat(5,minmax(0,1fr))}.card,.panel{background:var(--panel);border:1px solid var(--grid);border-radius:var(--radius);box-shadow:var(--shadow)}
.card{padding:16px;min-height:112px;transition:transform .2s}.card:hover{transform:translateY(-2px);box-shadow:0 14px 36px rgba(31,36,48,.1)}.card .label{font-size:13px;color:var(--muted);line-height:1.3}.card .value{font-size:25px;font-weight:750;margin:9px 0 4px}.card .note{font-size:12px;color:var(--muted)}
.progress-panel{padding:20px;margin-bottom:20px}.progress-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:14px}.status-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}.status-kpi{padding:11px 12px;background:#f8f9fc;border:1px solid var(--grid);border-radius:10px}.status-kpi .kpi-label{display:block;color:var(--muted);font-size:11px;line-height:1.3}.status-kpi .kpi-value{display:block;margin-top:5px;font-size:20px;font-weight:750;color:var(--ink)}.status-kpi .kpi-context{display:block;margin-top:2px;color:var(--muted);font-size:11px}.progressbar{height:25px;display:flex;overflow:hidden;border-radius:8px;background:#eee}.seg{height:100%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;white-space:nowrap}.counted{background:var(--blue);color:white}.jee{background:var(--pink);color:white}.missing{background:#e7c85a}
.section-title{font-size:20px;margin:22px 0 12px}
.progress-panel .legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:13px;color:var(--muted)}.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:16px}.panel{padding:18px;min-width:0}.span-6{grid-column:span 6}.span-7{grid-column:span 7}.span-5{grid-column:span 5}.span-12{grid-column:span 12}.span-4{grid-column:span 4}.span-8{grid-column:span 8}
.panel h2{font-size:18px;margin:0}.panel-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:12px}.panel-sub{font-size:12px;color:var(--muted);margin-top:4px}
.panel>svg{width:100%;height:320px;display:block}.plotly-chart{width:100%;height:400px;border-radius:10px;background:white}#uncertaintyChart{height:480px}#territorialContribChart{height:620px}
.axis{stroke:#d7dbe7;stroke-width:1}.gridline{stroke:#e6e8f0;stroke-width:1}.tick{font-size:11px;fill:#6f768a}.chart-label{font-size:11px;fill:#1f2430}.zero{stroke:#464c55;stroke-width:1.4}
.controls{display:flex;gap:8px;flex-wrap:wrap}select,input{border:1px solid #d7dbe7;border-radius:8px;padding:8px 10px;background:white;color:var(--ink);font:inherit;font-size:13px}
.table-wrap{overflow:auto;max-height:460px;border:1px solid var(--grid);border-radius:10px}table{width:100%;border-collapse:collapse;font-size:13px;background:white}th{position:sticky;top:0;background:#f4f5f7;text-align:right;color:#464c55;z-index:1}th,td{padding:9px 10px;border-bottom:1px solid var(--grid);white-space:nowrap}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}td{text-align:right}
.callout{padding:14px 16px;border-left:5px solid var(--keiko);background:#ffedde;border-radius:8px;margin-top:16px;font-size:14px;line-height:1.5}
.method{font-size:13px;line-height:1.55;color:#464c55}.empty{text-align:center;color:var(--muted);padding:30px}

/* Model cards */
.models-section{margin-top:24px}
.models-section h2{font-size:22px;margin-bottom:8px}
.models-section .subtitle{font-size:14px;color:var(--muted);margin-bottom:20px}
.models-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-bottom:24px}
.model-card{background:white;border:1px solid var(--grid);border-radius:var(--radius);padding:20px;box-shadow:var(--shadow);transition:all .2s}
.model-card:hover{transform:translateY(-3px);box-shadow:0 16px 40px rgba(31,36,48,.12)}
.model-card h3{font-size:17px;margin:0 0 12px;color:var(--blue);display:flex;align-items:center;gap:8px}
.model-card .model-icon{width:28px;height:28px;background:var(--blue-light);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;color:var(--blue)}
.model-card .desc{font-size:13px;color:#464c55;line-height:1.55;margin-bottom:14px}
.model-card .spec{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.model-card .tag{font-size:11px;padding:4px 9px;border-radius:6px;background:#eef1f6;color:#464c55}
.model-card .tag.pkg{background:#d4edda;color:#155724}
.model-card .tag.formula{background:#fff3cd;color:#856404;font-family:monospace;font-size:10px}
.model-card .detail-row{display:flex;justify-content:space-between;padding:6px 0;font-size:12px;border-bottom:1px solid var(--grid)}
.model-card .detail-row:last-child{border-bottom:none}
.model-card .detail-label{color:var(--muted)}
.model-card .detail-value{font-weight:600;color:var(--ink)}
.model-card .strengths{margin-top:12px}
.model-card .strengths h4{font-size:12px;color:var(--muted);margin:0 0 6px;text-transform:uppercase;letter-spacing:.5px}
.model-card .strengths ul{margin:0;padding-left:18px;font-size:12px;color:#464c55;line-height:1.6}
.model-card .strengths li{margin-bottom:2px}

/* Backtest section */
.backtest-section{background:white;border:1px solid var(--grid);border-radius:var(--radius);padding:22px;box-shadow:var(--shadow);margin-bottom:24px}
.backtest-section h3{font-size:18px;margin:0 0 6px}
.backtest-section .panel-sub{margin-bottom:16px}
.backtest-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.backtest-chart{min-height:400px;position:relative}
.backtest-chart .modebar{display:none !important}
.backtest-chart .js-plotly-plot .plotly .modebar{display:none !important}

/* Weights visualization */
.weights-section{background:linear-gradient(135deg,#f0f4ff,#fff);border:1px solid #d7dbe7;border-radius:var(--radius);padding:22px;margin-bottom:24px}
.weights-section h3{font-size:18px;margin:0 0 6px}
.weights-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:16px}
.weight-card{background:white;border-radius:10px;padding:16px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.05)}
.weight-card .model-name{font-size:13px;color:var(--muted);margin-bottom:8px}
.weight-card .weight-value{font-size:28px;font-weight:800;color:var(--blue)}
.weight-bar{height:6px;background:#e6e8f0;border-radius:3px;margin-top:10px;overflow:hidden}
.weight-bar-fill{height:100%;border-radius:3px;transition:width .8s ease}
.weights-note{margin-top:16px;padding:13px 15px;border-radius:10px;background:#fff;border:1px solid var(--grid);font-size:13px;line-height:1.55;color:#464c55}

/* Chart explanations */
.chart-explanation{margin-top:14px;border:1px solid var(--grid);border-radius:10px;background:#fafbfc}
.chart-explanation summary{padding:12px 16px;cursor:pointer;font-size:13px;font-weight:600;color:var(--blue);user-select:none;list-style:none}
.chart-explanation summary::-webkit-details-marker{display:none}
.chart-explanation summary::before{content:"▸ ";display:inline-block;margin-right:6px;transition:transform .2s}
.chart-explanation[open] summary::before{transform:rotate(90deg)}
.chart-explanation .explanation-content{padding:0 16px 14px;font-size:13px;line-height:1.6;color:#464c55}
.chart-explanation .explanation-content p{margin:0 0 10px}
.chart-explanation .explanation-content strong{color:var(--ink)}

@media(max-width:1200px){.header{display:block}.header-summary{align-items:flex-start;margin-top:12px}.vote-badges{justify-content:flex-start}h1{font-size:27px}}
@media(max-width:1050px){.span-5,.span-6,.span-7,.span-4,.span-8{grid-column:span 12}.backtest-grid{grid-template-columns:1fr}.models-grid{grid-template-columns:1fr}.cards.five-up{grid-template-columns:repeat(2,minmax(0,1fr))}.status-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){main{padding:16px}.header{display:block}.header-summary{align-items:flex-start}.vote-badges{flex-wrap:wrap}.badge{white-space:normal}h1{font-size:26px;white-space:normal}.cards.five-up,.status-kpis{grid-template-columns:1fr}.card .value{font-size:21px}.panel{padding:14px}.panel>svg{height:290px}.plotly-chart{height:340px}}
</style>
</head>
<body>
<main>
  <header class="header">
    <div>
      <h1>Pronósticos de la segunda vuelta presidencial Perú 2026</h1>
      <div class="subtitle" id="freshness"></div>
      <div class="source-note">Procesamiento de datos a partir de la publicación de resultados de la ONPE.</div>
    </div>
    <div class="header-summary">
      <div class="vote-badges">
        <div class="badge sanchez" id="officialSanchez"></div>
        <div class="badge keiko" id="officialKeiko"></div>
      </div>
      <div class="badge difference" id="officialDifference"></div>
    </div>
  </header>
  <section class="panel progress-panel">
    <div class="progress-head"><div><strong>Estado de las 92,766 mesas</strong><div class="panel-sub">El porcentaje oficial contabilizado usa el universo completo de la maestra electoral.</div></div></div>
    <div class="status-kpis" id="statusKpis"></div>
    <div class="progressbar" id="progressbar"></div><div class="legend" id="progresslegend"></div>
  </section>
  <h2 class="section-title">Escenarios posibles</h2>
  <section class="cards five-up" id="modelCards" aria-label="Pronósticos por modelo"></section>
  <section class="grid">
    <article class="panel span-6"><div class="panel-head"><div><h2>Avance del procesamiento</h2><div class="panel-sub">Porcentaje del universo total por corte</div></div></div><svg id="advanceChart"></svg><details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Tres líneas de tiempo: el porcentaje de actas contabilizadas (azul), enviadas al JEE (rosado) y aún no ingresadas (amarillo) en cada corte temporal.</p><p>Permite ver la velocidad de procesamiento de la ONPE y cuánto falta por contabilizar del universo total de 92,766 mesas.</p><p>Cómo leer: la línea azul debería subir progresivamente hasta cerca del 100%. Si se estanca, indica que el procesamiento se ha ralentizado. La línea amarilla (no ingresadas) debería bajar hasta cerca de cero.</p></div></details></article>
    <article class="panel span-6"><div class="panel-head"><div><h2>Margen observado y proyectado</h2><div class="panel-sub">Miles de votos; positivo favorece a Keiko, negativo a Sánchez</div></div></div><svg id="marginChart"></svg><details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Línea punteada: el margen observado en actas contabilizadas (sólo votos oficiales).</p><p>Líneas sólidas: cómo cada modelo proyecta el margen final incluyendo las mesas pendientes. Si las líneas convergen hacia el mismo resultado, hay consenso entre modelos.</p><p>Cómo leer: si la línea punteada (oficial) está por encima de cero pero las líneas de proyección están por debajo, significa que las mesas pendientes probablemente favorecerán a Sánchez y el resultado final podría revertirse. Cuanto más cerca estén las líneas sólidas entre sí, mayor consenso.</p></div></details></article>
    <article class="panel span-6"><div class="panel-head"><div><h2>Dónde están las mesas pendientes</h2><div class="panel-sub">Top territorios por actas en JEE o todavía no ingresadas</div></div><select id="territoryCount"><option value="12">Top 12</option><option value="20">Top 20</option><option value="40">Todos</option></select></div><svg id="geoChart"></svg><details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Barras apiladas: cuántas mesas faltan por contabilizar en cada región, separadas por estado (rosado = JEE observadas, amarillo = aún no ingresadas).</p><p>Identifica los territorios críticos donde aún hay mucho trabajo pendiente y que pueden cambiar el resultado final.</p><p>Cómo leer: las regiones con barras más largas tienen más mesas pendientes. El rosado indica actas que ya fueron procesadas pero tienen observaciones y pueden cambiar por resolución del JEE. El amarillo indica actas que todavía no aparecen en el sistema de la ONPE.</p></div></details></article>
    <article class="panel span-6"><div class="panel-head"><div><h2>Resultado por modelo</h2><div class="panel-sub">Margen final proyectado en votos</div></div></div><svg id="modelChart"></svg><details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Barras divergentes: el margen final que proyecta cada modelo. Barras naranjas hacia la derecha indican victoria de Keiko. Barras verdes hacia la izquierda indican victoria de Sánchez. Cada etiqueta muestra el candidato ganador y el margen proyectado en votos.</p><p>Si todos los modelos apuntan al mismo ganador, la proyección es robusta. Si divergen, hay incertidumbre sobre el resultado final.</p><p>Cómo leer: compara la dirección y longitud de las barras. Si todas apuntan al mismo lado con magnitudes similares, hay alto consenso. Si algunas apuntan a Keiko y otras a Sánchez, los modelos no se ponen de acuerdo sobre el resultado final.</p></div></details></article>
    <!-- Modelos: nueva sección detallada -->
    <article class="panel span-12 models-section">
      <h2>Modelos de proyección: ficha técnica</h2>
      <p class="subtitle">Cada modelo proyecta las mesas pendientes con supuestos distintos. El ensamble los combina según su desempeño histórico.</p>
      
      <div class="models-grid" id="modelsGrid"></div>
    </article>
    
    <!-- Pesos del ensamble -->
    <article class="panel span-12 weights-section">
      <h3>Pesos del ensamble</h3>
      <div class="panel-sub">Calculados inversamente al error absoluto medio (MAE) en backtesting desde 60% de avance</div>
      <div class="weights-grid" id="weightsGrid"></div>
      <div class="weights-note"><strong>Cómo leerlo:</strong> un peso mayor indica que el modelo tuvo menor error promedio en los cortes anteriores y, por eso, influye más en la proyección combinada. Los pesos suman 100% y no representan probabilidades de victoria; son la participación de cada modelo en el resultado del ensamble.</div>
    </article>
    
    <!-- Backtesting interactivo -->
    <article class="panel span-12 backtest-section">
      <h3>Validación retrospectiva (backtesting)</h3>
      <div class="panel-sub">Cómo se desempeñó cada modelo en cortes anteriores: error en puntos porcentuales respecto al resultado observado final</div>
      <div class="backtest-grid">
        <div class="backtest-chart" id="backtestMAEChart"></div>
        <div class="backtest-chart" id="backtestRMSEChart"></div>
      </div>
      <div class="backtest-chart" id="backtestEvolutionChart" style="margin-top:16px;min-height:380px"></div>
      <details class="chart-explanation"><summary>Qué muestran estos gráficos</summary><div class="explanation-content"><p>MAE (error absoluto medio): cuánto se equivocó cada modelo en promedio al proyectar cortes anteriores. Menor es mejor.</p><p>RMSE y error máximo: dispersión del error y el peor caso observado. Ayuda a identificar modelos con valores atípicos.</p><p>Evolución temporal: cómo cada modelo fue proyectando el margen a lo largo de los cortes. La línea punteada es el resultado observado real.</p><p>Cómo leer: en los dos gráficos superiores, busca las barras más bajas. En el gráfico de evolución, si las líneas están muy dispersas, los modelos no se ponen de acuerdo; si convergen hacia la línea punteada, están acertando.</p></div></details>
    </article>
    
    <!-- Distribución simulada de incertidumbre -->
    <article class="panel span-12">
      <div class="panel-head"><div><h2>Distribución de incertidumbre (simulación Monte Carlo)</h2><div class="panel-sub">50,000 simulaciones mezclando modelos según pesos de backtesting</div></div></div>
      <div id="uncertaintyChart" class="plotly-chart"></div>
      <details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Histograma: distribución de 50,000 resultados posibles del margen final, generados sorteando modelos según su peso en el ensamble. Barras naranjas = Keiko gana; barras verdes = Sánchez gana.</p><p>Líneas verticales: la mediana (línea sólida) y el intervalo de confianza del 95% (líneas punteadas). La línea roja marca el empate (margen cero).</p><p>Si la distribución cruza el cero, hay incertidumbre real sobre el ganador. Si está completamente a un lado, el resultado es más claro.</p><p>Cómo leer: mira la proporción de barras naranjas y verdes. La distancia entre las líneas punteadas (2.5% y 97.5%) indica el rango de incertidumbre: cuanto más ancho, más incierto el resultado.</p></div></details>
    </article>
    
    <!-- Contribución territorial al margen -->
    <article class="panel span-12">
      <div class="panel-head"><div><h2>Contribución territorial al margen proyectado</h2><div class="panel-sub">Qué regiones aportan más al margen final del ensamble</div></div></div>
      <div id="territorialContribChart" class="plotly-chart"></div>
      <details class="chart-explanation"><summary>Qué muestra este gráfico</summary><div class="explanation-content"><p>Barras horizontales: las 15 regiones que más contribuyen al margen proyectado del ensamble.</p><p>Colores: naranja si favorece a Keiko y verde si favorece a Sánchez. El porcentaje indica cuánto aporta esa región al margen total.</p><p>Ayuda a identificar los bastiones territoriales de cada candidato y dónde se define la elección.</p><p>Cómo leer: las barras naranjas hacia la derecha son regiones donde Keiko obtiene ventaja. Las barras verdes hacia la izquierda son regiones donde Sánchez obtiene ventaja. Las regiones con barras más largas son las más decisivas.</p></div></details>
    </article>
    
    <!-- Tabla ODPE al final -->
    <article class="panel span-12">
      <div class="panel-head"><div><h2>Detalle territorial por ODPE</h2><div class="panel-sub">Busca y filtra las jurisdicciones con trabajo pendiente</div></div>
      <div class="controls"><select id="regionFilter"><option value="">Todas las regiones</option></select><select id="statusFilter"><option value="pending">Con pendientes</option><option value="jee">Con actas JEE</option><option value="missing">Con no ingresadas</option><option value="all">Todas</option></select><input id="search" placeholder="Buscar ODPE"></div></div>
      <div class="table-wrap"><table><thead><tr><th>Región</th><th>ODPE</th><th>Total</th><th>Contabilizadas</th><th>JEE</th><th>No ingresadas</th><th>Electores pendientes</th><th>% contabilizado</th></tr></thead><tbody id="odpeRows"></tbody></table></div>
    </article>
    
    <article class="panel span-12 method"><h2>Definiciones y cautelas</h2>
      <p><strong>Contabilizada:</strong> acta incorporada al resultado oficial. <strong>Enviada al JEE:</strong> acta procesada con observación y pendiente de resolución. <strong>No ingresada:</strong> mesa de la maestra que todavía no aparece en el CSV del corte.</p>
      <p>El liderazgo oficial usa solo actas contabilizadas. Las proyecciones incorporan modelos nacionales, territoriales y por ODPE. Los votos digitados en actas JEE pueden modificarse por resolución. Fuente: CSV ONPE del módulo especializado y maestra “Mesa por Mesa SEP2026 25.05.26.xlsx”.</p>
    </article>
  </section>
</main>
<script>
const DATA=__DATA__, S=DATA.summary, fmt=n=>Math.round(n).toLocaleString("es-PE"), pct=n=>n.toFixed(3)+"%";
const winner=m=>m>0?"Keiko":"Sánchez", signed=m=>(m>0?"+":"")+fmt(m);
const candidateColor=m=>m>0?"#f0986e":"#71b436";
document.getElementById("freshness").textContent=`Actualizado: ${S.latest_label}`;
const officialDifference=document.getElementById("officialDifference");
document.getElementById("officialSanchez").textContent=`Sánchez: ${fmt(S.official_jp)} votos`;
document.getElementById("officialKeiko").textContent=`Keiko: ${fmt(S.official_fp)} votos`;
officialDifference.textContent=`Diferencia: ${fmt(Math.abs(S.official_margin_fp))} votos`;
// Obtener datos de cada modelo
const modelMap = {
  "Arrastre nacional": "arrastre_nacional",
  "Jerarquico territorial": "jerarquico_territorial",
  "ODPE ponderado": "odpe_ponderado",
  "JEE reportado + faltantes territoriales": "jee_reportado",
  "Ensamble por backtesting": "ensamble",
};
const modelDisplayNames = {
  "Arrastre nacional": "Arrastre nacional",
  "Jerarquico territorial": "Jerárquico territorial",
  "ODPE ponderado": "ODPE ponderado",
  "JEE reportado + faltantes territoriales": "JEE reportado + faltantes territoriales",
  "Ensamble por backtesting": "Ensamble por backtesting",
};
const detailDisplayNames = {
  "arrastre_nacional": "Arrastre nacional",
  "jerarquico_territorial": "Jerárquico territorial",
  "odpe_ponderado": "ODPE ponderado",
  "jee_reportado": "JEE reportado",
  "ensamble": "Ensamble",
};
const modelCurrents = {};
DATA.models.forEach(m => {
  const key = modelMap[m.modelo];
  if(key) modelCurrents[key] = m;
});

const statusKpis = [
  ["Actas totales", fmt(S.total_mesas), "100.000%"],
  ["Actas contabilizadas", fmt(S.contabilizadas), pct(S.pct_contabilizadas)],
  ["Avance contabilizado", pct(S.pct_contabilizadas), `${fmt(S.contabilizadas)} actas`],
  ["Enviadas al JEE", fmt(S.jee), pct(S.pct_jee)],
  ["Porcentaje enviado al JEE", pct(S.pct_jee), `${fmt(S.jee)} actas`],
];
document.getElementById("statusKpis").innerHTML=statusKpis.map(d=>`<div class="status-kpi"><span class="kpi-label">${d[0]}</span><span class="kpi-value">${d[1]}</span><span class="kpi-context">${d[2]}</span></div>`).join("");

// Cards de modelos (5) - cada uno muestra quién gana y por cuánto
const modelCards = Object.entries(modelMap).map(([fullName, key]) => {
  const m = modelCurrents[key];
  if (!m) return null;
  const margin = m.margen_votos_fp;
  const ganador = margin > 0 ? "Keiko" : "Sánchez";
  const margenAbs = Math.abs(margin);
  const shortName = modelDisplayNames[fullName].replace(" + faltantes territoriales", " + faltantes");
  return [
    shortName,
    ganador + " +" + fmt(margenAbs),
    `${m.fp_pct.toFixed(2)}% vs ${m.jp_pct.toFixed(2)}%`,
    candidateColor(margin),
  ];
}).filter(Boolean);

const renderCards=(target,rows)=>document.getElementById(target).innerHTML=rows.map(d=>`<div class="card"><div class="label">${d[0]}</div><div class="value"${d[3]?` style="color:${d[3]}"`:""}>${d[1]}</div><div class="note">${d[2]}</div></div>`).join("");
renderCards("modelCards",modelCards);
const progress=[["Contabilizadas",S.pct_contabilizadas,"counted"],["JEE",S.pct_jee,"jee"],["No ingresadas",S.pct_no_ingresadas,"missing"]];
document.getElementById("progressbar").innerHTML=progress.map(d=>`<div class="seg ${d[2]}" style="width:${d[1]}%">${d[1]>3?pct(d[1]):""}</div>`).join("");
document.getElementById("progresslegend").innerHTML=progress.map(d=>`<span><i class="dot ${d[2]}"></i>${d[0]}: ${pct(d[1])}</span>`).join("");
const NS="http://www.w3.org/2000/svg";
function el(name,attrs={},text=""){const e=document.createElementNS(NS,name);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text)e.textContent=text;return e}
function clear(svg){while(svg.firstChild)svg.removeChild(svg.firstChild)}
function dims(svg){const w=Math.max(420,svg.clientWidth||700),h=parseInt(getComputedStyle(svg).height);svg.setAttribute("viewBox",`0 0 ${w} ${h}`);return{w,h}}
function lineChart(svgId,series,yDomain,colors,yFormat){
 const svg=document.getElementById(svgId);clear(svg);const{w,h}=dims(svg),legendCols=w<600?2:series.length,legendRows=Math.ceil(series.length/legendCols),m={l:58,r:18,t:12+legendRows*18,b:42},iw=w-m.l-m.r,ih=h-m.t-m.b;
 const all=series.flatMap(s=>s.values),xs=all.map(d=>new Date(d.x).getTime()),xmin=Math.min(...xs),xmax=Math.max(...xs);let[ymin,ymax]=yDomain;
 const X=x=>m.l+(new Date(x).getTime()-xmin)/(xmax-xmin||1)*iw,Y=y=>m.t+(ymax-y)/(ymax-ymin||1)*ih;
 for(let i=0;i<=4;i++){let y=ymin+(ymax-ymin)*i/4,py=Y(y);svg.append(el("line",{x1:m.l,x2:w-m.r,y1:py,y2:py,class:"gridline"}));svg.append(el("text",{x:m.l-8,y:py+4,"text-anchor":"end",class:"tick"},yFormat(y)))}
 for(let i=0;i<5;i++){let t=xmin+(xmax-xmin)*i/4,px=m.l+iw*i/4;svg.append(el("text",{x:px,y:h-13,"text-anchor":"middle",class:"tick"},new Date(t).toLocaleString("es-PE",{day:"2-digit",month:"2-digit",hour:"2-digit"})))}
 if(ymin<0&&ymax>0)svg.append(el("line",{x1:m.l,x2:w-m.r,y1:Y(0),y2:Y(0),class:"zero"}));
 series.forEach((s,j)=>{const pts=s.values.map(d=>`${X(d.x)},${Y(d.y)}`).join(" ");svg.append(el("polyline",{points:pts,fill:"none",stroke:colors[j],"stroke-width":s.width||2.2,"stroke-dasharray":s.dash||""}));});
 const legendWidth=iw/legendCols;
 series.forEach((s,j)=>{const col=j%legendCols,row=Math.floor(j/legendCols),lx=m.l+col*legendWidth,ly=10+row*18;svg.append(el("line",{x1:lx,y1:ly,x2:lx+20,y2:ly,stroke:colors[j],"stroke-width":3,"stroke-dasharray":s.dash||""}));svg.append(el("text",{x:lx+25,y:ly+4,class:"tick"},s.name))});
}
function renderAdvance(){
 const p=DATA.progress,series=[
  {name:"Contabilizadas",values:p.map(d=>({x:d.timestamp,y:d.pct_contabilizadas}))},
  {name:"JEE",values:p.map(d=>({x:d.timestamp,y:d.pct_jee}))},
  {name:"No ingresadas",values:p.map(d=>({x:d.timestamp,y:d.pct_no_ingresadas}))}
 ];lineChart("advanceChart",series,[0,100],["#5477c4","#bd569b","#d4a72c"],v=>v.toFixed(0)+"%");
}
function renderMargins(){
 const observed={name:"Observado",dash:"5 3",width:2.6,values:DATA.progress.filter(d=>d.avance_archivo>=90&&Number.isFinite(d.margen_observado_fp)).map(d=>({x:d.timestamp,y:d.margen_observado_fp/1000}))};
 const wanted=["Jerarquico territorial","ODPE ponderado","Arrastre nacional"],cols=["#1f2430","#8a5aa8","#d4a72c","#5477c4"];
 const short={"Jerarquico territorial":"Territorial","ODPE ponderado":"ODPE","Arrastre nacional":"Nacional"};
 const series=[observed,...wanted.map(name=>({name:short[name],values:DATA.modelSeries.filter(d=>d.modelo===name&&d.avance_archivo>=90).map(d=>({x:d.timestamp,y:d.margen_votos_fp/1000}))}))];
 const vals=series.flatMap(s=>s.values.map(d=>d.y)),pad=(Math.max(...vals)-Math.min(...vals))*.08;lineChart("marginChart",series,[Math.min(...vals)-pad,Math.max(...vals)+pad],cols,v=>v.toFixed(0)+"k");
}
function barChart(svgId,rows,options){
 const svg=document.getElementById(svgId);clear(svg);const{w,h}=dims(svg),m={l:options.left||150,r:25,t:12,b:30},iw=w-m.l-m.r,ih=h-m.t-m.b,n=rows.length,bh=Math.max(5,ih/Math.max(n,1)*.67),max=options.max||Math.max(...rows.map(options.value),1);
 rows.forEach((r,i)=>{const y=m.t+i*ih/n+(ih/n-bh)/2;svg.append(el("text",{x:m.l-8,y:y+bh*.72,"text-anchor":"end",class:"chart-label"},options.label(r)));let cursor=m.l;(options.parts||[{value:options.value,color:"#5477c4"}]).forEach(p=>{const val=p.value(r),bw=iw*val/max;svg.append(el("rect",{x:cursor,y,width:bw,height:bh,rx:2,fill:p.color}));cursor+=bw});svg.append(el("text",{x:Math.min(cursor+6,w-4),y:y+bh*.72,class:"tick"},fmt(options.value(r))))});
}
function renderGeo(){const n=+document.getElementById("territoryCount").value,rows=DATA.geography.filter(d=>d.pendientes>0).slice(0,n);barChart("geoChart",rows,{left:120,value:r=>r.pendientes,label:r=>r.region,parts:[{value:r=>r.jee,color:"#bd569b"},{value:r=>r.no_ingresadas,color:"#e7c85a"}]});const svg=document.getElementById("geoChart"),{w,h}=dims(svg),legendY=h-8;svg.append(el("rect",{x:120,y:legendY-10,width:12,height:10,fill:"#bd569b",rx:2}));svg.append(el("text",{x:136,y:legendY,class:"tick"},"JEE (observadas)"));svg.append(el("rect",{x:240,y:legendY-10,width:12,height:10,fill:"#e7c85a",rx:2}));svg.append(el("text",{x:256,y:legendY,class:"tick"},"No ingresadas"))}
function renderModels(){
 const rows=DATA.models.filter(d=>d.modelo!=="Resultado observado"),svg=document.getElementById("modelChart");
 clear(svg);
 const{w,h}=dims(svg),compact=w<560,m=compact?{l:18,r:18,t:12,b:58}:{l:215,r:72,t:14,b:58},iw=w-m.l-m.r,ih=h-m.t-m.b,max=Math.max(...rows.map(r=>Math.abs(r.margen_votos_fp)),1),X=v=>m.l+iw/2+(v/(max*1.15))*(iw/2);
 svg.append(el("line",{x1:X(0),x2:X(0),y1:m.t,y2:h-m.b,class:"zero"}));
 svg.append(el("text",{x:X(0)+30,y:h-m.b+18,class:"tick",style:"fill:#f0986e"},"Favorece a Keiko (+)"));svg.append(el("text",{x:X(0)-30,y:h-m.b+18,"text-anchor":"end",class:"tick",style:"fill:#71b436"},"Favorece a Sánchez (-)"));
 rows.forEach((r,i)=>{
   const slot=ih/rows.length,bh=compact?slot*.40:slot*.58,y=compact?m.t+i*slot+slot*.46:m.t+i*slot+(slot-bh)/2,x0=X(0),x1=X(r.margen_votos_fp),positive=r.margen_votos_fp>0,color=positive?"#f0986e":"#71b436";
   const label=modelDisplayNames[r.modelo].replace(" + faltantes territoriales","");
   svg.append(el("text",compact?{x:m.l,y:y-5,class:"chart-label"}:{x:m.l-16,y:y+bh*.72,"text-anchor":"end",class:"chart-label"},label));
   svg.append(el("rect",{x:Math.min(x0,x1),y,width:Math.abs(x1-x0),height:bh,rx:3,fill:color}));
   const ganador=positive?"Keiko":"Sánchez",inside=Math.abs(x1-x0)>(compact?82:105);
   svg.append(el("text",{x:inside?(positive?x1-8:x1+8):(positive?x1+8:x1-8),y:y+bh*.72,"text-anchor":inside?(positive?"end":"start"):(positive?"start":"end"),class:"tick",style:`fill:${inside?"#ffffff":color};font-weight:700`},ganador+" "+signed(r.margen_votos_fp)));
 });
 const legendY=h-28,legendX=compact?Math.max(20,X(0)-105):Math.max(m.l,X(0)-105);
 svg.append(el("rect",{x:legendX,y:legendY,width:12,height:10,fill:"#f0986e",rx:2}));svg.append(el("text",{x:legendX+16,y:legendY+9,class:"tick"},"Keiko gana"));svg.append(el("rect",{x:legendX+105,y:legendY,width:12,height:10,fill:"#71b436",rx:2}));svg.append(el("text",{x:legendX+121,y:legendY+9,class:"tick"},"Sánchez gana"));
}
const regionSel=document.getElementById("regionFilter");[...new Set(DATA.odpe.map(d=>d.region))].sort().forEach(r=>regionSel.insertAdjacentHTML("beforeend",`<option>${r}</option>`));
function renderTable(){const reg=regionSel.value,st=document.getElementById("statusFilter").value,q=document.getElementById("search").value.toUpperCase();let rows=DATA.odpe.filter(r=>(!reg||r.region===reg)&&(!q||r.odpe.includes(q)));if(st==="pending")rows=rows.filter(r=>r.pendientes>0);if(st==="jee")rows=rows.filter(r=>r.jee>0);if(st==="missing")rows=rows.filter(r=>r.no_ingresadas>0);rows=rows.slice(0,250);document.getElementById("odpeRows").innerHTML=rows.length?rows.map(r=>`<tr><td>${r.region}</td><td>${r.odpe}</td><td>${fmt(r.total)}</td><td>${fmt(r.contabilizadas)}</td><td>${fmt(r.jee)}</td><td>${fmt(r.no_ingresadas)}</td><td>${fmt(r.electores_pendientes)}</td><td>${r.pct_contabilizadas.toFixed(2)}%</td></tr>`).join(""):`<tr><td colspan="8" class="empty">Sin resultados</td></tr>`}
document.getElementById("territoryCount").addEventListener("change",renderGeo);[regionSel,document.getElementById("statusFilter"),document.getElementById("search")].forEach(e=>e.addEventListener(e.tagName==="INPUT"?"input":"change",renderTable));

// ========== MODELOS: FICHAS TÉCNICAS INTERACTIVAS ==========
const modelIcons = {
  "arrastre_nacional": "[A]",
  "jerarquico_territorial": "[J]",
  "odpe_ponderado": "[O]",
  "jee_reportado": "[E]",
  "ensamble": "[B]",
};
const modelColors = {
  "arrastre_nacional": "#5477c4",
  "jerarquico_territorial": "#8a5aa8",
  "odpe_ponderado": "#d4a72c",
  "jee_reportado": "#bd569b",
  "ensamble": "#464c55",
};
function renderModelCards(){
  const container = document.getElementById("modelsGrid");
  const currentModels = {};
  DATA.models.forEach(m => {
    const key = modelMap[m.modelo];
    if(key) currentModels[key] = m;
  });
  const html = Object.entries(DATA.modelDetails).map(([key, detail]) => {
    const current = currentModels[key];
    const color = modelColors[key];
    const icon = modelIcons[key];
    const marginText = current ? (current.margen_votos_fp > 0 ? "Keiko" : "Sánchez") + " +" + fmt(Math.abs(current.margen_votos_fp)) : "-";
    const winnerColor = current && current.margen_votos_fp > 0 ? "#f0986e" : "#71b436";
    const fpPct = current ? current.fp_pct.toFixed(3) + "%" : "-";
    const jpPct = current ? current.jp_pct.toFixed(3) + "%" : "-";
    
    let detailRows = "";
    if(detail.hierarchy_levels){
      detailRows += `<div class="detail-row"><span class="detail-label">Niveles jerárquicos</span><span class="detail-value">${detail.hierarchy_levels}</span></div>`;
    }
    if(detail.prior_weights){
      detailRows += `<div class="detail-row"><span class="detail-label">Pesos de contracción</span><span class="detail-value">${detail.prior_weights.join(" → ")}</span></div>`;
    }
    if(current){
      detailRows += `<div class="detail-row"><span class="detail-label">Keiko</span><span class="detail-value" style="color:#f0986e">${fpPct}</span></div>`;
      detailRows += `<div class="detail-row"><span class="detail-label">Sánchez</span><span class="detail-value" style="color:#71b436">${jpPct}</span></div>`;
      detailRows += `<div class="detail-row"><span class="detail-label">Margen proyectado</span><span class="detail-value" style="color:${winnerColor}">${marginText}</span></div>`;
    }
    
    return `
      <div class="model-card">
        <h3><span class="model-icon" style="background:${color}22;color:${color}">${icon}</span>${detailDisplayNames[key]}</h3>
        <div class="desc">${detail.descripcion}</div>
        <div class="spec">
          <span class="tag pkg">${detail.paquete}</span>
          <span class="tag formula">${detail.formula}</span>
        </div>
        ${detailRows}
        <div class="strengths">
          <h4>Fortalezas</h4>
          <ul>${detail.fortalezas.split(",").map(s=>`<li>${s.trim()}</li>`).join("")}</ul>
          <h4 style="margin-top:8px">Debilidades</h4>
          <ul>${detail.debilidades.split(",").map(s=>`<li>${s.trim()}</li>`).join("")}</ul>
        </div>
      </div>
    `;
  }).join("");
  container.innerHTML = html;
}

// ========== PESOS DEL ENSAMBLE ==========
function renderWeights(){
  const container = document.getElementById("weightsGrid");
  const weights = DATA.weights;
  const maxWeight = Math.max(...Object.values(weights));
  const html = Object.entries(weights).map(([name, weight]) => {
    const key = modelMap[name] || name;
    const color = modelColors[key] || "#5477c4";
    const icon = modelIcons[key] || "📊";
    const pct = (weight * 100).toFixed(1);
    const barWidth = (weight / maxWeight * 100).toFixed(1);
    return `
      <div class="weight-card">
        <div class="model-name">${icon} ${modelDisplayNames[name] || name}</div>
        <div class="weight-value" style="color:${color}">${pct}%</div>
        <div class="weight-bar"><div class="weight-bar-fill" style="width:${barWidth}%;background:${color}"></div></div>
      </div>
    `;
  }).join("");
  container.innerHTML = html;
}

// ========== BACKTESTING INTERACTIVO CON PLOTLY ==========
function renderBacktestMAE(){
  const bt = DATA.backtestDetailed;
  const labels = bt.map(d => modelDisplayNames[d.modelo] || d.modelo);
  const mae = bt.map(d => d.mae);
  const maxMae = Math.max(...mae, 1);
  const traces = bt.map((d, index) => ({
    x: [d.mae],
    y: [labels[index]],
    name: labels[index],
    type: "bar",
    orientation: "h",
    marker: {color: modelColors[modelMap[d.modelo]] || "#5477c4"},
    text: [d.mae.toFixed(3) + " pp"],
    textposition: "outside",
    cliponaxis: false,
    hovertemplate: "<b>%{y}</b><br>MAE: %{x:.3f} pp<extra></extra>",
  }));
  Plotly.newPlot("backtestMAEChart", traces, {
    title: {text: "Error absoluto medio (MAE)", font: {size: 14}},
    xaxis: {title: "Error (puntos porcentuales)", gridcolor: "#e6e8f0", range: [0, maxMae * 1.28]},
    yaxis: {automargin: true, tickfont: {size: 11}, categoryorder: "array", categoryarray: labels.slice().reverse()},
    showlegend: true,
    legend: {orientation: "h", y: -0.18, x: 0.5, xanchor: "center", yanchor: "top"},
    margin: {t: 55, b: 80, l: 175, r: 75},
    plot_bgcolor: "white",
    paper_bgcolor: "white",
  }, {responsive: true, displayModeBar: false});
}

function renderBacktestRMSE(){
  const bt = DATA.backtestDetailed;
  const models = bt.map(d => d.modelo);
  const modelLabels = models.map(m => modelDisplayNames[m] || m);
  const rmse = bt.map(d => d.rmse);
  const maxError = bt.map(d => d.max_error);
  const xMax = Math.max(...maxError, ...rmse, 1) * 1.25;
  Plotly.newPlot("backtestRMSEChart", [
    {
      x: rmse,
      y: modelLabels,
      name: "RMSE",
      type: "bar",
      orientation: "h",
      marker: {color: "#5477c4"},
      text: rmse.map(v => v.toFixed(3) + " pp"),
      textposition: "outside",
      cliponaxis: false,
      hovertemplate: "<b>%{y}</b><br>RMSE: %{x:.3f} pp<extra></extra>",
    },
    {
      x: maxError,
      y: modelLabels,
      name: "Error máximo",
      type: "scatter",
      mode: "markers+text",
      marker: {color: "#8a5aa8", size: 10, symbol: "diamond"},
      text: maxError.map(v => v.toFixed(3) + " pp"),
      textposition: "middle right",
      cliponaxis: false,
      hovertemplate: "<b>%{y}</b><br>Error máx: %{x:.3f} pp<extra></extra>",
    }
  ], {
    title: {text: "RMSE y error máximo", font: {size: 14}},
    xaxis: {title: "Error (puntos porcentuales)", gridcolor: "#e6e8f0", range: [0, xMax]},
    yaxis: {automargin: true, tickfont: {size: 11}, categoryorder: "array", categoryarray: modelLabels.slice().reverse()},
    legend: {orientation: "h", y: -0.18, x: 0.5, xanchor: "center", yanchor: "top"},
    margin: {t: 55, b: 80, l: 175, r: 105},
    plot_bgcolor: "white",
    paper_bgcolor: "white",
  }, {responsive: true, displayModeBar: false});
}

function renderBacktestEvolution(){
  const ms = DATA.modelSeries;
  const wanted = ["Jerarquico territorial","ODPE ponderado","Arrastre nacional","JEE reportado + faltantes territoriales"];
  const short = {"Jerarquico territorial":"Territorial","ODPE ponderado":"ODPE","Arrastre nacional":"Nacional","JEE reportado + faltantes territoriales":"JEE + faltantes"};
  const traces = wanted.map(name => ({
    x: ms.filter(d => d.modelo === name).map(d => d.label),
    y: ms.filter(d => d.modelo === name).map(d => d.margen_votos_fp / 1000),
    name: short[name] || name,
    type: "scatter",
    mode: "lines+markers",
    line: {color: modelColors[modelMap[name]] || "#5477c4", width: 2.5},
    marker: {size: 5},
    hovertemplate: "<b>%{x}</b><br>Margen: %{y:.1f}k votos<br>" + (short[name] || name) + "<extra></extra>",
  }));
  const observed = DATA.progress.filter(d => Number.isFinite(d.margen_observado_fp)).map(d => ({x: d.label, y: d.margen_observado_fp / 1000}));
  traces.push({
    x: observed.map(d => d.x),
    y: observed.map(d => d.y),
    name: "Observado",
    type: "scatter",
    mode: "lines",
    line: {color: "#1f2430", width: 3, dash: "dot"},
    hovertemplate: "<b>%{x}</b><br>Observado: %{y:.1f}k votos<extra></extra>",
  });
  Plotly.newPlot("backtestEvolutionChart", traces, {
    title: {text: "Evolución del margen proyectado por modelo (miles de votos)", font: {size: 14}},
    xaxis: {title: "Corte temporal", tickangle: -30, tickfont: {size: 9}},
    yaxis: {title: "Margen Keiko (miles de votos)", gridcolor: "#e6e8f0", zeroline: true, zerolinecolor: "#464c55", zerolinewidth: 1.5},
    legend: {orientation: "h", y: -0.28, x: 0.5, xanchor: "center"},
    margin: {t: 60, b: 125, l: 75, r: 35},
    plot_bgcolor: "white",
    paper_bgcolor: "white",
    hovermode: "x unified",
  }, {responsive: true, displayModeBar: false});
}

// ========== DISTRIBUCIÓN DE INCERTIDUMBRE (MONTE CARLO) ==========
function renderUncertainty(){
  const sims = DATA.simulations;
  const margins = sims.map(d => d.margen_votos_fp);
  const probKeiko = (sims.filter(d => d.margen_votos_fp > 0).length / sims.length * 100).toFixed(1);
  const probSanchez = (100 - parseFloat(probKeiko)).toFixed(1);
  const low = S.interval_low, med = S.interval_median, high = S.interval_high;
  // Separar en dos trazas para la leyenda
  const keikoVals = margins.filter(v => v > 0);
  const sanchezVals = margins.filter(v => v <= 0);
  Plotly.newPlot("uncertaintyChart", [
    {
      x: keikoVals,
      type: "histogram",
      name: `Keiko gana (${probKeiko}%)`,
      nbinsx: 120,
      marker: {color: "#F0986E", line: {width: 0}},
      hovertemplate: "Margen: %{x:,.0f} votos<br>Cantidad: %{y}<extra></extra>",
    },
    {
      x: sanchezVals,
      type: "histogram",
      name: `Sánchez gana (${probSanchez}%)`,
      nbinsx: 120,
      marker: {color: "#71B436", line: {width: 0}},
      hovertemplate: "Margen: %{x:,.0f} votos<br>Cantidad: %{y}<extra></extra>",
    },
  ], {
    title: {text: "Distribución del margen de Keiko (50,000 simulaciones)", font: {size: 14}},
    xaxis: {title: "Margen de votos (Keiko positivo, Sánchez negativo)", zeroline: true, zerolinecolor: "#464c55", zerolinewidth: 2},
    yaxis: {title: "Frecuencia (simulaciones)", gridcolor: "#e6e8f0"},
    barmode: "stack",
    showlegend: true,
    legend: {
      x: 0.5,
      y: -0.27,
      xanchor: "center",
      yanchor: "top",
      orientation: "h",
      font: {size: 12},
      bgcolor: "rgba(255,255,255,0.9)",
      bordercolor: "#e6e8f0",
      borderwidth: 1,
    },
    shapes: [
      {type: "line", x0: low, x1: low, y0: 0, y1: 1, yref: "paper", line: {color: "#888", dash: "dash"}},
      {type: "line", x0: med, x1: med, y0: 0, y1: 1, yref: "paper", line: {color: "#464c55", width: 2}},
      {type: "line", x0: high, x1: high, y0: 0, y1: 1, yref: "paper", line: {color: "#888", dash: "dash"}},
      {type: "line", x0: 0, x1: 0, y0: 0, y1: 1, yref: "paper", line: {color: "#d32f2f", width: 2, dash: "dot"}},
    ],
    annotations: [
      {x: med, y: 1, yref: "paper", text: `Mediana: ${fmt(med)}`, showarrow: true, arrowhead: 2, ax: 30, ay: -20},
      {x: low, y: 0.9, yref: "paper", text: `2.5%: ${fmt(low)}`, showarrow: true, arrowhead: 2, ax: -30, ay: -20},
      {x: high, y: 0.9, yref: "paper", text: `97.5%: ${fmt(high)}`, showarrow: true, arrowhead: 2, ax: 30, ay: -20},
      {x: 0, y: 0.7, yref: "paper", text: "Empate", showarrow: false, font: {color: "#d32f2f", size: 12}},
    ],
    margin: {t: 65, b: 135, l: 75, r: 45},
    plot_bgcolor: "white",
    paper_bgcolor: "white",
  }, {responsive: true, displayModeBar: false});
}

// ========== CONTRIBUCIÓN TERRITORIAL ==========
function renderTerritorialContrib(){
  const tc = DATA.territorialContrib
    .filter(d => d.ambito === "PERU")
    .sort((a,b) => Math.abs(b.contribucion_margen_pct) - Math.abs(a.contribucion_margen_pct))
    .slice(0, 15)
    .sort((a,b) => a.contribucion_margen_pct - b.contribucion_margen_pct);
  const regions = tc.map(d => d.region);
  const values = tc.map(d => d.contribucion_margen_pct);
  const minX = Math.min(...values, 0);
  const maxX = Math.max(...values, 0);
  const candidateTrace = (positive, name, color) => {
    const rows = tc.filter(d => positive ? d.contribucion_margen_pct > 0 : d.contribucion_margen_pct <= 0);
    return {
      x: rows.map(d => d.contribucion_margen_pct),
      y: rows.map(d => d.region),
      name,
      type: "bar",
      orientation: "h",
      marker: {color},
      text: rows.map(d => `${d.contribucion_margen_pct.toFixed(1)}% (${d.margen_proyectado > 0 ? "+" : ""}${Math.round(d.margen_proyectado).toLocaleString("es-PE")} votos)`),
      textposition: "outside",
      textfont: {size: 11},
      cliponaxis: false,
      hovertemplate: "<b>%{y}</b><br>Contribución: %{x:.2f}%<br>%{text}<extra></extra>",
    };
  };
  Plotly.newPlot("territorialContribChart", [
    candidateTrace(true, "Favorece a Keiko", "#F0986E"),
    candidateTrace(false, "Favorece a Sánchez", "#71B436"),
  ], {
    title: {text: `Top ${tc.length} regiones por contribución al margen proyectado`, font: {size: 14}},
    xaxis: {title: "Contribución al margen (%)", zeroline: true, zerolinecolor: "#464c55", zerolinewidth: 2, gridcolor: "#e6e8f0", range: [Math.min(minX * 3, -maxX * 0.22), maxX * 1.35]},
    margin: {t: 55, b: 110, l: 185, r: 185},
    plot_bgcolor: "white",
    paper_bgcolor: "white",
    showlegend: true,
    legend: {
      x: 0.5,
      y: -0.16,
      xanchor: "center",
      yanchor: "top",
      orientation: "h",
      font: {size: 12},
      itemsizing: "constant",
      traceorder: "normal",
    },
    yaxis: {automargin: true, tickfont: {size: 12}, categoryorder: "array", categoryarray: regions},
  }, {responsive: true, displayModeBar: false});
}

function renderAll(){renderAdvance();renderMargins();renderGeo();renderModels();renderTable();renderModelCards();renderWeights();renderBacktestMAE();renderBacktestRMSE();renderBacktestEvolution();renderUncertainty();renderTerritorialContrib();} window.addEventListener("resize",()=>{clearTimeout(window.rt);window.rt=setTimeout(()=>{renderAdvance();renderMargins();renderGeo();renderModels()},120)});renderAll();
</script>
</body></html>"""


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(build_dashboard(root))

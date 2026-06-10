import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const baseDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const salidasDir = path.join(baseDir, "salidas");
const descargasDir = path.join(baseDir, "insumos", "descargas_modulo");
const inputCsv = path.join(salidasDir, "resumen_departamento_odpe.csv");
const outputXlsx = path.join(salidasDir, "Ranking de procesamiento por ODPE.xlsx");

const title = "Elecci\u00f3n presidencial de segunda vuelta Per\u00fa 2026";
const subtitle = "Avance de la contabilizaci\u00f3n de actas por ODPE a nivel nacional";
const fallbackUpdateLabel = "Actualizaci\u00f3n: 8 de junio \u2013 1:30pm";
const sourceNote = "Fuente: Sistema de presentaci\u00f3n de resultados \u2013 M\u00f3dulo Especializado - ONPE.";

const artifactToolModule =
  process.env.ARTIFACT_TOOL_MODULE ||
  "C:/Users/AsistentedeDatos/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const { SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactToolModule).href);

async function inferUpdateLabel() {
  const monthNames = {
    "01": "enero",
    "02": "febrero",
    "03": "marzo",
    "04": "abril",
    "05": "mayo",
    "06": "junio",
    "07": "julio",
    "08": "agosto",
    "09": "septiembre",
    "10": "octubre",
    "11": "noviembre",
    "12": "diciembre",
  };

  try {
    const files = await fs.readdir(descargasDir);
    const csvFiles = [];
    for (const file of files.filter((f) => f.toLowerCase().endsWith(".csv"))) {
      const full = path.join(descargasDir, file);
      const stat = await fs.stat(full);
      csvFiles.push({ file, mtimeMs: stat.mtimeMs });
    }
    csvFiles.sort((a, b) => b.mtimeMs - a.mtimeMs);
    const latest = csvFiles[0]?.file || "";
    const match = latest.match(/_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(AM|PM)_/i);
    if (!match) return fallbackUpdateLabel;

    const [, , month, day, hh, mm, ampmRaw] = match;
    const ampm = ampmRaw.toLowerCase();
    let hour = Number(hh);
    if (hour === 0) hour = 12;
    return `Actualizaci\u00f3n: ${Number(day)} de ${monthNames[month] || month} \u2013 ${hour}:${mm}${ampm}`;
  } catch {
    return fallbackUpdateLabel;
  }
}

const updateLabel = process.env.ONPE_SV_UPDATE_LABEL || await inferUpdateLabel();

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (quoted) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

function toNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16));
}

function rgbToHex([r, g, b]) {
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function blend(c1, c2, t) {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  return rgbToHex(a.map((v, i) => Math.round(v + (b[i] - v) * t)));
}

function rampColor(value, min, max) {
  if (value === null || Number.isNaN(value)) return "#D9D9D9";
  if (max <= min) return "#FDAE61";
  const x = Math.max(0, Math.min(1, (value - min) / (max - min)));
  if (x <= 0.5) return blend("#D73027", "#FDAE61", x / 0.5);
  return blend("#FDAE61", "#1A9850", (x - 0.5) / 0.5);
}

function textColor(bg) {
  const [r, g, b] = hexToRgb(bg);
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance < 150 ? "#FFFFFF" : "#000000";
}

function pctLabel(value) {
  return value === null ? "" : value;
}

function formatRange(range, format) {
  range.format = format;
}

const csvText = await fs.readFile(inputCsv, "utf8");
const parsed = parseCsv(csvText);
const header = parsed.shift();
const index = Object.fromEntries(header.map((name, i) => [name, i]));

const rows = parsed
  .filter((r) => r.length > 1)
  .map((r) => ({
    eleccion: r[index.eleccion],
    departamento: r[index.departameto],
    odpe: r[index.odpe],
    nombreOdpe: r[index.nombre_odpe],
    mesasTotales: toNumber(r[index.mesas_totales]),
    mesasContabilizadas: toNumber(r[index.mesas_contabilizadas]),
    pctMesasContabilizadas: toNumber(r[index.pct_mesas_contabilizadas]),
    mesasAlJee: toNumber(r[index.mesas_al_jee]),
    pctMesasAlJee: toNumber(r[index.pct_mesas_al_jee]),
    electoresTotales: toNumber(r[index.electores_totales]),
    electoresContabilizados: toNumber(r[index.electores_contabilizados]),
    electoresPorContabilizar: toNumber(r[index.electores_por_contabilizar]),
    pctElectoresContabilizados: toNumber(r[index.pct_electores_contabilizados]),
    pctElectoresPorContabilizar: toNumber(r[index.pct_electores_por_contabilizar]),
  }))
  .sort((a, b) =>
    (a.pctMesasContabilizadas ?? 0) - (b.pctMesasContabilizadas ?? 0) ||
    a.nombreOdpe.localeCompare(b.nombreOdpe) ||
    a.odpe.localeCompare(b.odpe),
  );

const minMesas = Math.min(...rows.map((r) => r.pctMesasContabilizadas).filter((v) => v !== null));
const maxMesas = Math.max(...rows.map((r) => r.pctMesasContabilizadas).filter((v) => v !== null));
const tableHeader = [
  "Rango",
  "Departamento",
  "ODPE",
  "Nombre ODPE",
  "Actas totales",
  "Actas contabilizadas",
  "% avance",
  "Actas enviadas al JEE",
  "% actas enviadas al JEE",
  "Electores totales",
  "Electores contabilizados",
  "Electores por contabilizar",
  "% electores por contabilizar",
];

const tableRows = rows.map((r, i) => [
  i + 1,
  r.departamento,
  r.odpe,
  r.nombreOdpe,
  r.mesasTotales,
  r.mesasContabilizadas,
  pctLabel(r.pctMesasContabilizadas),
  r.mesasAlJee,
  pctLabel(r.pctMesasAlJee),
  r.electoresTotales,
  r.electoresContabilizados,
  r.electoresPorContabilizar,
  pctLabel(r.pctElectoresPorContabilizar),
]);

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Ranking ODPE");
sheet.showGridLines = false;

sheet.getRange("A1:M1").merge();
sheet.getRange("A2:M2").merge();
sheet.getRange("A3:M3").merge();

sheet.getRange("A1").values = [[title]];
sheet.getRange("A2").values = [[subtitle]];
sheet.getRange("A3").values = [[updateLabel]];

formatRange(sheet.getRange("A1:M1"), {
  font: { bold: true, size: 16, color: "#1F4E79" },
  horizontalAlignment: "center",
});
formatRange(sheet.getRange("A2:M2"), {
  font: { italic: true, size: 11, color: "#404040" },
  horizontalAlignment: "center",
});
formatRange(sheet.getRange("A3:M3"), {
  font: { bold: true, size: 10, color: "#595959" },
  horizontalAlignment: "center",
});

sheet.getRange("A5:M5").values = [tableHeader];
sheet.getRangeByIndexes(5, 0, tableRows.length, tableHeader.length).values = tableRows;

const lastRow = 5 + tableRows.length;
const tableRange = `A5:M${lastRow}`;
sheet.tables.add(tableRange, true, "RankingODPE");

formatRange(sheet.getRange("A5:M5"), {
  fill: "#4F81BD",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#BFBFBF" },
});

formatRange(sheet.getRange(`A6:M${lastRow}`), {
  font: { size: 9, color: "#1F1F1F" },
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#D9D9D9" },
});

formatRange(sheet.getRange(`A6:A${lastRow}`), { horizontalAlignment: "center" });
formatRange(sheet.getRange(`B6:D${lastRow}`), { horizontalAlignment: "left" });
formatRange(sheet.getRange(`E6:M${lastRow}`), { horizontalAlignment: "center" });
sheet.getRange(`E6:F${lastRow}`).format.numberFormat = "#,##0";
sheet.getRange(`H6:H${lastRow}`).format.numberFormat = "#,##0";
sheet.getRange(`J6:L${lastRow}`).format.numberFormat = "#,##0";
sheet.getRange(`G6:G${lastRow}`).format.numberFormat = "0.0%";
sheet.getRange(`I6:I${lastRow}`).format.numberFormat = "0.0%";
sheet.getRange(`M6:M${lastRow}`).format.numberFormat = "0.0%";

for (let i = 0; i < rows.length; i += 1) {
  const excelRow = 6 + i;
  const mesasFill = rampColor(rows[i].pctMesasContabilizadas, minMesas, maxMesas);
  formatRange(sheet.getRange(`G${excelRow}`), {
    fill: mesasFill,
    font: { bold: true, color: textColor(mesasFill), size: 9 },
    horizontalAlignment: "center",
  });
}

const noteRow = lastRow + 2;
sheet.getRange(`A${noteRow}:M${noteRow}`).merge();
sheet.getRange(`A${noteRow}`).values = [[sourceNote]];
formatRange(sheet.getRange(`A${noteRow}:M${noteRow}`), {
  font: { italic: true, size: 9, color: "#595959" },
  horizontalAlignment: "left",
});

const widths = [9, 18, 24, 24, 14, 18, 12, 18, 22, 16, 20, 22, 24];
widths.forEach((width, i) => {
  sheet.getRangeByIndexes(0, i, lastRow + 2, 1).format.columnWidth = width;
});

sheet.getRange("A1:M3").format.rowHeight = 24;
sheet.getRange("A5:M5").format.rowHeight = 30;
sheet.freezePanes.freezeRows(5);

if (process.env.ONPE_SV_RENDER_PREVIEW === "1") {
  const preview = await workbook.render({
    sheetName: "Ranking ODPE",
    range: `A1:M${Math.min(noteRow, 42)}`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(salidasDir, "_qa_ranking_odpe_excel_preview.png"),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputXlsx);

console.log(`Archivo generado: ${outputXlsx}`);
console.log(`Filas totales: ${rows.length}`);

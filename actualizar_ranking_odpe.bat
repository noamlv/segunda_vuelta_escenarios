@echo off
setlocal
chcp 65001 >nul

set "BASE_DIR=%~dp0"
set "RSCRIPT=C:\Users\AsistentedeDatos\AppData\Local\Programs\R\R-4.5.3\bin\Rscript.exe"
set "NODE_EXE=C:\Users\AsistentedeDatos\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
set "PYTHON_EXE=C:\Users\AsistentedeDatos\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "ARTIFACT_TOOL_MODULE=C:\Users\AsistentedeDatos\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\@oai\artifact-tool\dist\artifact_tool.mjs"

if not exist "%RSCRIPT%" (
  echo No se encontro Rscript en:
  echo %RSCRIPT%
  echo.
  pause
  exit /b 1
)

if not exist "%NODE_EXE%" (
  echo No se encontro Node.js en:
  echo %NODE_EXE%
  echo.
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo No se encontro Python en:
  echo %PYTHON_EXE%
  echo.
  pause
  exit /b 1
)

echo Recalculando cruce ONPE-ODPE con el CSV mas reciente...
"%RSCRIPT%" "%BASE_DIR%scripts\01_onpe_odpe_cruce_segunda_vuelta.R"
if errorlevel 1 (
  echo.
  echo Fallo el cruce ONPE-ODPE.
  pause
  exit /b 1
)

echo.
echo Generando Excel de ranking ODPE...
"%NODE_EXE%" "%BASE_DIR%scripts\04_ranking_odpe_excel.mjs"
if errorlevel 1 (
  echo.
  echo Fallo la generacion del Excel.
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%BASE_DIR%scripts\05_finalizar_ranking_excel.py"
if errorlevel 1 (
  echo.
  echo Fallo el ajuste final del Excel.
  pause
  exit /b 1
)

echo.
echo Listo. Archivo generado:
echo %BASE_DIR%salidas\Ranking de procesamiento por ODPE.xlsx
echo.
pause

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from freshmart.settings import DATA_DIR, REPORT_PATH


def analizar_csv(
    nombre_archivo: str,
    columnas_muestra: list[str] | None = None,
    columna_id: str | None = None,
    filas_muestra: int = 10,
    data_dir: Path = DATA_DIR,
) -> dict[str, Any]:
    """Analiza un CSV y devuelve un informe serializable a JSON."""
    ruta = data_dir / nombre_archivo
    df = pd.read_csv(ruta)

    muestra_df = df.head(filas_muestra)
    muestra = (
        muestra_df.astype(object)
        .where(muestra_df.notna(), None)
        .to_dict(orient="records")
    )

    informe = {
        "archivo": nombre_archivo,
        "filas": len(df),
        "numero_columnas": len(df.columns),
        "columnas": list(df.columns),
        "tipos_datos": {columna: str(tipo) for columna, tipo in df.dtypes.items()},
        "valores_nulos": {
            columna: int(cantidad) for columna, cantidad in df.isnull().sum().items()
        },
        "filas_muestra": muestra,
    }

    if columna_id and columna_id in df.columns:
        ids_unicos = int(df[columna_id].nunique())

        informe["identificadores"] = {
            "columna": columna_id,
            "ids_unicos": ids_unicos,
            "ids_totales": len(df),
            "posibles_duplicados": len(df) - ids_unicos,
        }

    if columnas_muestra:
        informe["muestras_columnas"] = {
            columna: [
                valor.item() if hasattr(valor, "item") else valor
                for valor in df[columna].dropna().head(filas_muestra)
            ]
            for columna in columnas_muestra
            if columna in df.columns
        }

    return informe


def generar_informe(
    data_dir: Path = DATA_DIR,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    """Genera y guarda el informe de exploración de FreshMart."""
    informes = {
        "clientes": analizar_csv(
            "campana_verano_clientes.csv",
            columna_id="cliente_id",
            data_dir=data_dir,
        ),
        "ventas": analizar_csv(
            "campana_verano_ventas.csv",
            columnas_muestra=["fecha_compra", "precio"],
            data_dir=data_dir,
        ),
        "productos": analizar_csv(
            "productos_promo_verano.csv",
            data_dir=data_dir,
        ),
    }

    informe_final = {
        "proyecto": "FreshMart",
        "tipo_informe": "exploracion_inicial",
        "datasets": informes,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8") as archivo:
        json.dump(
            informe_final,
            archivo,
            indent=4,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )

    return informe_final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explora los CSV de FreshMart y genera un informe JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR,
        help="Directorio que contiene los CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORT_PATH,
        help="Ruta del informe JSON de salida.",
    )

    args = parser.parse_args()

    generar_informe(
        data_dir=args.input,
        report_path=args.output,
    )
    print(f"Informe generado correctamente: {args.output}")


if __name__ == "__main__":
    main()

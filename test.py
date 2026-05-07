import os
import csv
import json
import requests

API_KEY = os.environ.get("hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu", "hzZItvRA2Rfrri2XEjt2VSyMek9PC1Yu")
BASE_URL = "https://api.polygon.io/v3/reference/conditions"

def fetch_conditions(asset_class="stocks", data_type="trade", limit=1000):
    """
    Descarga TODAS las condiciones (paginando) para el asset_class y data_type indicados.
    Devuelve una lista de dicts (cada dict es una condición).
    """
    params = {
        "asset_class": asset_class,
        "data_type": data_type,
        "limit": limit,
        "apiKey": API_KEY,
    }
    out = []
    url = BASE_URL

    while url:
        r = requests.get(url, params=params if url == BASE_URL else None, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("results", []))
        # next_url ya incluye query; solo añade apiKey si hace falta en algunos entornos
        url = data.get("next_url")
        if url:
            # Asegurar apiKey en next_url (por si la respuesta no lo trae)
            if "apiKey=" not in url:
                url = f"{url}&apiKey={API_KEY}"

    return out

def main():
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        raise SystemExit("Falta API key. Define POLYGON_API_KEY o edita el código.")

    conditions = fetch_conditions(asset_class="stocks", data_type="trade")

    # Mapeo compacto útil para OPEN: id -> flags de actualización (si están presentes)
    open_rules_map = {}
    rows_for_csv = []
    for c in conditions:
        cid = c.get("id")
        name = c.get("name")
        abbr = c.get("abbreviation")
        desc = c.get("description")
        # Algunos tenants tienen 'update_rules' con 'consolidated'
        consolidated = (c.get("update_rules") or {}).get("consolidated") or {}
        updates_open_close = consolidated.get("updates_open_close")
        updates_high_low = consolidated.get("updates_high_low")
        updates_volume = consolidated.get("updates_volume")

        open_rules_map[cid] = {
            "name": name,
            "abbreviation": abbr,
            "updates_open_close": updates_open_close,
        }

        rows_for_csv.append({
            "id": cid,
            "name": name,
            "abbreviation": abbr,
            "description": desc,
            "updates_open_close": updates_open_close,
            "updates_high_low": updates_high_low,
            "updates_volume": updates_volume,
        })

    # Guardar JSON completo
    with open("polygon_conditions_trade_stocks.json", "w", encoding="utf-8") as f:
        json.dump(conditions, f, ensure_ascii=False, indent=2)

    # Guardar CSV resumido (id, nombre, abreviatura, flags)
    fieldnames = ["id", "name", "abbreviation", "description",
                  "updates_open_close", "updates_high_low", "updates_volume"]
    with open("polygon_conditions_trade_stocks.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_for_csv)

    # Ejemplo: imprimir reglas de algunos IDs si existen (12, 14, 37, 41)
    for check_id in (12, 14, 37, 41):
        info = open_rules_map.get(check_id)
        print(f"Condición {check_id}: {info}" if info else f"Condición {check_id}: no encontrada")

    print("\nDescarga completa.")
    print("Archivos creados: polygon_conditions_trade_stocks.json, polygon_conditions_trade_stocks.csv")

if __name__ == "__main__":
    main()
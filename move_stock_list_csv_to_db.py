import pandas as pd
import sqlite3
import csv

def save_stocks_to_db(csv_file, db_name):
    df = pd.read_csv(csv_file)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    count = 0
    for symbol in df['Symbol']:
        cursor.execute('''
            INSERT OR IGNORE INTO Stocks (ticker, close, stock_index) VALUES (?, ?, ?)
        ''', (symbol, 0.0, 0))
        count += 1

    conn.commit()
    conn.close()

    print(f"Stocks saved successfully. {count} stocks were inserted.")

def actualizar_news_events(db_path, archivo_csv):
    # Conectar a la base de datos
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Leer el archivo CSV
    with open(archivo_csv, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        # Iterar sobre cada línea del archivo CSV
        for row in reader:
            symbol = row["Symbol"]
            description = row["Description"]
            sector = row["Sector"]
            
            # Verificar si el símbolo ya existe en la tabla NewsEventsAndPressReleases
            cursor.execute("SELECT COUNT(*) FROM NewsEventsAndPressReleases WHERE symbol = ?", (symbol,))
            if cursor.fetchone()[0] == 0:
                # Si el símbolo no existe, insertar la información en NewsEventsAndPressReleases
                cursor.execute("""
                    INSERT INTO NewsEventsAndPressReleases (symbol, name, sector)
                    VALUES (?, ?, ?)
                """, (symbol, description, sector))
                print(f"Símbolo {symbol} insertado con éxito.")
            else:
                print(f"El símbolo {symbol} ya existe en la tabla NewsEventsAndPressReleases.")
    
    # Confirmar cambios y cerrar la conexión
    conn.commit()
    conn.close()

def actualizar_news_events2(db_path, archivo):
    # Conectar a la base de datos
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Leer el archivo
    with open(archivo, 'r') as file:
        lines = file.readlines()

    # Iterar sobre cada línea en el archivo
    for line in lines:
        # Separar los datos por tabuladores
        symbol, name, url, sector = line.strip().split('\t')
        
        # Verificar si el símbolo existe en la tabla Stock
        cursor.execute("SELECT COUNT(*) FROM NewsEventsAndPressReleases WHERE symbol = ?", (symbol,))
        if cursor.fetchone()[0] > 0:
            # Si el símbolo existe, solo actualizar la URL en la tabla NewsEventsAndPressReleases
            cursor.execute("""
                UPDATE NewsEventsAndPressReleases
                SET url = ?
                WHERE symbol = ?
            """, (url, symbol))
            print(f"URL actualizada para el símbolo: {symbol}")
        else:
            # Si el símbolo no existe, insertar todo en la tabla NewsEventsAndPressReleases
            cursor.execute("""
                INSERT INTO NewsEventsAndPressReleases (symbol, name, url, sector)
                VALUES (?, ?, ?, ?)
            """, (symbol, name, url, sector))
            print(f"Símbolo {symbol} insertado con éxito.")

    # Confirmar cambios y cerrar la conexión
    conn.commit()
    conn.close()

    # print(f"Stocks saved successfully. {count} stocks were inserted.")

# Example usage
csv_file = 'stock_list_raw.csv'
db_name = 'histFinanData.db'
save_stocks_to_db(csv_file, db_name)

# actualizar_news_events2('histFinanData.db', 'health_care.txt')

# actualizar_news_events('histFinanData.db', 'data.csv')
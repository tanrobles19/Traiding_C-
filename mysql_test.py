import mysql.connector
import sqlite3

# # Parámetros de conexión
# db_connection = mysql.connector.connect(
#     host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
#     port=3306,
#     user="admin",  # Reemplaza con tu usuario de MySQL
#     password="E_I$S5PFri",  # Reemplaza con tu contraseña
#     database="mysql"  # Reemplaza con el nombre de tu base de datos
# )

# if db_connection.is_connected():
#     print("Conexión exitosa a la base de datos RDS MySQL")

# db_connection.close()

   
    # conn.close()

def to_int_or_zero(x):
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    if isinstance(x, str):
        x = x.strip()
        if x == "" or x.upper() == "N/A":
            return 0
        return int(float(x))
    return int(x) 

def transfer_data_to_mysql(sqlite_db):
    
    sqlite_conn = sqlite3.connect("histFinanData.db")
    sqlite_cursor = sqlite_conn.cursor()

    # Consultar todos los datos de la tabla Stocks de SQLite
    sqlite_cursor.execute("SELECT * FROM Stocks")
    rows = sqlite_cursor.fetchall()

    # db_connection = mysql.connector.connect(
    #     host="database-trading.cut2mkgg2cz9.us-east-1.rds.amazonaws.com",
    #     port=3306,
    #     user="admin",  # Reemplaza con tu usuario de MySQL
    #     password="E_I$S5PFri",  # Reemplaza con tu contraseña
    #     database="histFinanData"  # Reemplaza con el nombre de tu base de datos
    # )

    db_connection = mysql.connector.connect(
        host="localhost",
        port=3306,
        user="root", 
        password="E_I$S5PFri",  
        database="histFinanData"
    )    

    if db_connection.is_connected():
        print("Conexión exitosa a la base de datos RDS MySQL")    

    
    mysql_cursor = db_connection.cursor()

    # Insertar los datos en la tabla Stocks de MySQL
    insert_query = """
    INSERT INTO Stocks (ticker, close, avg_month_volume, shares_outstanding, float_value, shares_short, short_percent_float)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    
    for row in rows:
        # Preparar los datos para la inserción
        data = (
            row[0],  # ticker
            row[1],  # close
            to_int_or_zero(row[2]),  # avg_month_volume
            row[3],  # shares_outstanding
            row[4],  # float_value
            row[5],  # shares_short
            row[6]   # short_percent_float
        )
        
        # Ejecutar la inserción
        mysql_cursor.execute(insert_query, data)

    # Confirmar los cambios en MySQL
    db_connection.commit()

    # Cerrar las conexiones
    sqlite_conn.close()
    db_connection.close()
    print("Datos transferidos con éxito a MySQL.")


transfer_data_to_mysql('histFinanData.db')
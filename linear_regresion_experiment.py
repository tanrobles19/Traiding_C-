import matplotlib.pyplot as plt
import numpy as np
import sqlite3

def linear_regresion_experiment(precios):
    # Crear el arreglo X como índices del tiempo (0, 1, 2, ..., n)
    X = np.arange(len(precios)).reshape(-1, 1)
    y = np.array(precios).reshape(-1, 1)

    # Ajustar el modelo de regresión lineal
    A = np.hstack((np.ones((X.shape[0], 1)), X))  # Agregar el término de sesgo
    theta = np.linalg.inv(A.T @ A) @ A.T @ y  # Ecuación normal

    # Predicciones
    y_pred = A @ theta

    # Graficar los resultados
    plt.scatter(X, y, color='blue', label='Datos reales')
    plt.plot(X, y_pred, color='red', label='Línea ajustada')
    plt.xlabel('Tiempo (minutos)')
    plt.ylabel('Precio')
    plt.title('Experimento de Regresión Lineal sobre los Precios')
    plt.legend()
    plt.show()

def get_prices_from_db(ticker):
    
    conn = sqlite3.connect('histFinanData.db')
    cursor = conn.cursor()
    
    query = """
        SELECT close
        FROM HistoryByMinToday
        WHERE stockID = ?
    """
    cursor.execute(query, (ticker,))
    
    precios = [row[0] for row in cursor.fetchall()]
        
    conn.close()
    
    return precios

def main(ticket):

    precios = get_prices_from_db(ticket)

    x = np.arange(len(precios))
    y = np.array(precios)

    slope, intercept = np.polyfit(x, y, 1)

    print(f"Slope (pendiente): {slope}")
    print(f"Intercept (intersección con eje Y): {intercept}")   

# main("CLF") 
linear_regresion_experiment(get_prices_from_db("PAPL"))
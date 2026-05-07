import multiprocessing
import os
import time

# Función que imprime "Hello, World!" y el ID del proceso
async def print_hello():
    print(f"Hello, World! - Process ID: {os.getpid()}")

# Crear dos procesos
if __name__ == "__main__":
    process1 = multiprocessing.Process(target=print_hello)
    process2 = multiprocessing.Process(target=print_hello)

    # Iniciar los procesos
    process1.start()
    process2.start()

    # Esperar a que los procesos terminen
    process1.join()
    process2.join()

    print("Paralelismo completo!")
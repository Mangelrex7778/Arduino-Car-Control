import serial
import serial.tools.list_ports
import time
import keyboard  # Necesitas instalar esta librería: pip install keyboard

def encontrar_puerto_bluetooth():
    """Busca en los puertos disponibles uno que contenga 'HC-06' o 'Bluetooth'."""
    puertos = list(serial.tools.list_ports.comports())
    for puerto in puertos:
        if "HC-06" in puerto.description or "Bluetooth" in puerto.description:
            return puerto.device
    return None

# Intentar detectar el puerto automáticamente
puerto_bluetooth = encontrar_puerto_bluetooth()
if puerto_bluetooth is None:
    print("No se encontró el HC-06 automáticamente. Se usará 'COM4' por defecto.")
    puerto_bluetooth = "COM4"
else:
    print(f"Puerto detectado: {puerto_bluetooth}")

baud_rate = 9600
try:
    ser = serial.Serial(puerto_bluetooth, baud_rate)
    time.sleep(2)  # Espera a que se estabilice la conexión
    print(f"Conectado al carrito por Bluetooth en {puerto_bluetooth}")
except Exception as e:
    print(f"Error al conectar al puerto {puerto_bluetooth}: {e}")
    exit()

# Mapeo de teclas: Usaremos WASD para dirección y espacio para detener
# Se envían los comandos que espera tu Arduino:
#   'a' → Adelante, 'r' → Atrás, 'i' → Izquierda, 'd' → Derecha, 'p' → Parar
key_to_command = {
    'w': 'a',  # Avanzar
    's': 'r',  # Retroceder
    'a': 'i',  # Izquierda
    'd': 'd',  # Derecha
}

print("\nControl del carrito:")
print("  - Usa WASD para mover (W: adelante, S: atrás, A: izquierda, D: derecha).")
print("  - Presiona espacio para detener el auto.")
print("  - Presiona ESC para salir.")

# Bucle de control continuo
try:
    while True:
        if keyboard.is_pressed('esc'):
            print("Saliendo...")
            break

        # Por defecto, detener el auto
        comando = 'p'

        # Si se detecta alguna tecla, se actualiza el comando
        if keyboard.is_pressed('w'):
            comando = key_to_command['w']
        elif keyboard.is_pressed('s'):
            comando = key_to_command['s']
        elif keyboard.is_pressed('a'):
            comando = key_to_command['a']
        elif keyboard.is_pressed('d'):
            comando = key_to_command['d']
        elif keyboard.is_pressed('space'):
            comando = 'p'

        # Enviar el comando por Bluetooth
        ser.write(comando.encode())
        print(f"Comando enviado: {comando}      ", end='\r')
        
        time.sleep(0.1)  # Ajusta este valor para mayor o menor sensibilidad
except KeyboardInterrupt:
    pass

ser.close()
print("\nConexión cerrada.")

import sys
import time
import json
import serial
import serial.tools.list_ports
import subprocess
import math

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QPainter, QConicalGradient, QColor, QFont, QPen, QIcon

# --- CONFIGURACIÓN POR DEFECTO ---
DEFAULT_SETTINGS = {
    "input": "Input 1",
    "forward_key": "a",     
    "backward_key": "r",    
    "left_key": "i",        
    "right_key": "d",       
    "stop_key": "p",        
    "auto_brake_key": "b",
    "speed_initial": 0,
    "theme": "Aero",
    "luces_direccion_izquierda": "q",
    "luces_direccion_derecha": "e",
    "speed_change_key": "c"
}

def load_settings(filename="settings.json"):
    try:
        with open(filename, "r") as f:
            settings = json.load(f)
        for key, value in DEFAULT_SETTINGS.items():
            if key not in settings:
                settings[key] = value
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        print("Error al cargar settings.json, usando valores por defecto.")
        return DEFAULT_SETTINGS.copy()

def save_settings(settings, filename="settings.json"):
    try:
        with open(filename, "w") as f:
            json.dump(settings, f, indent=4)
        print("Settings guardados en settings.json")
    except Exception as e:
        print(f"Error guardando settings: {e}")

def encontrar_puerto_bluetooth():
    puertos = list(serial.tools.list_ports.comports())
    for puerto in puertos:
        if "HC-06" in puerto.description or "Bluetooth" in puerto.description:
            return puerto.device
    return None

# --- Diccionario de límites por engranaje ---
gearMapping = {
    "N": {"maxSpeed": 0,   "maxRPM": 0},
    "R": {"maxSpeed": 40,  "maxRPM": 2000},
    "1": {"maxSpeed": 100,  "maxRPM": 2500},
    "2": {"maxSpeed": 125,  "maxRPM": 3000},
    "3": {"maxSpeed": 200,  "maxRPM": 3500},
    "4": {"maxSpeed": 225,  "maxRPM": 4000},
    "5": {"maxSpeed": 300, "maxRPM": 4500},
    "6": {"maxSpeed": 325, "maxRPM": 5000},
    "7": {"maxSpeed": 400, "maxRPM": 6000}
}

# --- GaugeWidget: Indicador circular (odómetro o tacómetro) ---
class GaugeWidget(QtWidgets.QWidget):
    def __init__(self, gauge_type="speed", min_value=0, max_value=100, parent=None):
        super().__init__(parent)
        self.gauge_type = gauge_type  
        self.min_value = min_value
        self.max_value = max_value
        self.current_value = min_value
        # Valor límite opcional
        self.limit_value = max_value  
        self.setMinimumSize(150, 150)

    def setValue(self, value):
        self.current_value = value
        self.update()

    def setLimitValue(self, value):
        self.limit_value = value
        self.update()

    def paintEvent(self, event):
        w = self.width()
        h = self.height()
        center = QtCore.QPointF(w/2, h/2)
        radius = min(w, h) / 2 - 10

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Fondo y borde
        painter.setPen(QPen(QColor("#555555"), 4))
        painter.setBrush(QColor("#000000"))
        painter.drawEllipse(center, radius, radius)

        startAngle = 45
        spanAngle = -270

        pen = QPen(QColor("#333333"), 20)
        painter.setPen(pen)
        painter.drawArc(10, 10, w-20, h-20, startAngle*16, spanAngle*16)

        fraction = (self.current_value - self.min_value) / (self.max_value - self.min_value)
        valueAngle = startAngle + fraction * spanAngle

        gradient = QConicalGradient(center, -valueAngle)
        if self.gauge_type == "speed":
            gradient.setColorAt(0.0, QColor("#00b8fe"))
            gradient.setColorAt(1.0, QColor("#41dcf4"))
        elif self.gauge_type == "rpm":
            gradient.setColorAt(0.0, QColor("#f7b733"))
            gradient.setColorAt(1.0, QColor("#fc4a1a"))
        pen.setBrush(gradient)
        painter.setPen(pen)
        painter.drawArc(10, 10, w-20, h-20, startAngle*16, int((valueAngle - startAngle)*16))

        # Aguja
        painter.save()
        painter.translate(center)
        painter.rotate(valueAngle)
        needle_pen = QPen(QColor("#FFFFFF"), 3)
        painter.setPen(needle_pen)
        painter.drawLine(0, 0, radius - 20, 0)
        painter.restore()

        # Texto central (valor actual)
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), QtCore.Qt.AlignCenter, f"{int(self.current_value)}")

        # Texto inferior: muestra el límite
        font_small = QFont("Arial", 10)
        painter.setFont(font_small)
        bottom_rect = QtCore.QRect(0, int(h/2+20), w, 30)
        limit_text = f"Lim: {int(self.limit_value)}"
        painter.drawText(bottom_rect, QtCore.Qt.AlignCenter, limit_text)

        painter.end()

# --- Estilo Global ---
DASHBOARD_STYLE = """
    QMainWindow { background-color: rgba(27,27,27,0.85); }
    QLabel#TitleLabel { color: #FFFFFF; font-size: 24px; font-weight: bold; }
    QPushButton { background-color: rgba(51,51,51,0.85); color: #FFFFFF; border: 1px solid rgba(85,85,85,0.85); border-radius: 5px; padding: 8px; }
    QPushButton:hover { background-color: rgba(68,68,68,0.85); }
    QLineEdit, QComboBox, QTextEdit { background-color: rgba(43,43,43,0.85); color: #FFFFFF; border: 1px solid rgba(85,85,85,0.85); border-radius: 3px; padding: 4px; }
"""

# --- Variables Globales para simular la aceleración ---
ACC_STEP = 10  # Incremento en velocidad por pulsación

# --- Ventanas Auxiliares (Ejemplos y Configuración) ---
class ExamplesWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ejemplos de Código")
        layout = QtWidgets.QVBoxLayout(self)
        example_codes = {
            "Básico": "void setup() { ... }\nvoid loop() { ... }",
            "Avanzado": "// Ejemplo avanzado..."
        }
        self.code_combo = QtWidgets.QComboBox(self)
        self.code_combo.addItems(example_codes.keys())
        layout.addWidget(self.code_combo)
        self.code_text = QtWidgets.QTextEdit(self)
        self.code_text.setReadOnly(True)
        self.code_text.setText(example_codes[self.code_combo.currentText()])
        layout.addWidget(self.code_text)
        self.code_combo.currentIndexChanged.connect(
            lambda _: self.code_text.setText(example_codes[self.code_combo.currentText()])
        )
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

class ConfigWindow(QtWidgets.QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.settings = settings
        layout = QtWidgets.QVBoxLayout(self)

        self.input_label = QtWidgets.QLabel("Tecla Input para velocidades:", self)
        self.input_edit = QtWidgets.QLineEdit(self)
        self.input_edit.setText(self.settings.get("input", "Input 1"))
        layout.addWidget(self.input_label)
        layout.addWidget(self.input_edit)

        self.speed_init_label = QtWidgets.QLabel("Velocidad Inicial:", self)
        self.speed_init_edit = QtWidgets.QLineEdit(self)
        self.speed_init_edit.setText(str(self.settings.get("speed_initial", 0)))
        layout.addWidget(self.speed_init_label)
        layout.addWidget(self.speed_init_edit)

        self.auto_brake_label = QtWidgets.QLabel("Tecla para Freno Automático:", self)
        self.auto_brake_edit = QtWidgets.QLineEdit(self)
        self.auto_brake_edit.setText(self.settings.get("auto_brake_key", "b"))
        layout.addWidget(self.auto_brake_label)
        layout.addWidget(self.auto_brake_edit)

        self.speed_change_label = QtWidgets.QLabel("Tecla para cambiar Velocidades:", self)
        self.speed_change_edit = QtWidgets.QLineEdit(self)
        self.speed_change_edit.setText(self.settings.get("speed_change_key", "c"))
        layout.addWidget(self.speed_change_label)
        layout.addWidget(self.speed_change_edit)

        def addSection(label_text, key_name):
            lbl = QtWidgets.QLabel(f"{label_text}:", self)
            le = QtWidgets.QLineEdit(self)
            le.setText(self.settings.get(key_name, ""))
            btn = QtWidgets.QPushButton("Cambiar", self)
            btn.clicked.connect(lambda: self.setKey(label_text, key_name, le))
            hbox = QtWidgets.QHBoxLayout()
            hbox.addWidget(lbl)
            hbox.addWidget(le)
            hbox.addWidget(btn)
            layout.addLayout(hbox)

        addSection("Adelante", "forward_key")
        addSection("Atrás", "backward_key")
        addSection("Izquierda", "left_key")
        addSection("Derecha", "right_key")
        addSection("Parar", "stop_key")
        addSection("Luz Izquierda", "luces_direccion_izquierda")
        addSection("Luz Derecha", "luces_direccion_derecha")

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def setKey(self, label_text, key_name, widget):
        key, ok = QtWidgets.QInputDialog.getText(self, f"Asigna tecla para {label_text}", "Presiona la tecla:")
        if ok and key:
            widget.setText(key)
            self.settings[key_name] = key

    def accept(self):
        self.settings["input"] = self.input_edit.text()
        try:
            self.settings["speed_initial"] = int(self.speed_init_edit.text())
        except ValueError:
            self.settings["speed_initial"] = DEFAULT_SETTINGS["speed_initial"]
        self.settings["auto_brake_key"] = self.auto_brake_edit.text()
        self.settings["speed_change_key"] = self.speed_change_edit.text()
        save_settings(self.settings)
        super().accept()

# --- Ventana de Control Real (modo Bluetooth) ---
class ControlWindow(QtWidgets.QMainWindow):
    def __init__(self, serialConnection, settings, app):
        super().__init__()
        self.serialConnection = serialConnection
        self.settings = settings
        self.setWindowTitle("Dashboard")
        self.setFixedSize(800, 600)
        self.app = app
        self.interface = TestWindow(settings, serialConnection, parent=self)
        self.setCentralWidget(self.interface)

# --- TestWindow: Dashboard (simulado y real) ---
class TestWindow(QtWidgets.QMainWindow):
    def __init__(self, settings, serialConnection=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.serialConnection = serialConnection  # Si hay datos reales del Arduino
        self.setWindowTitle("Dashboard")
        self.setFixedSize(800, 600)
        
        # Variables del tablero
        self.currentGear = "1"   # Engranaje inicial (manual)
        self.odometer = settings.get("speed_initial", 0)   # Velocidad actual
        self.rpm = 0             # RPM actual
        
        # Límites asignados según el engranaje actual
        self.limit_speed = gearMapping[self.currentGear]["maxSpeed"]
        self.limit_rpm = gearMapping[self.currentGear]["maxRPM"]
        
        # Variables para luces direccionales
        self.leftLightOn = False
        self.rightLightOn = False
        self.leftBlinkOn = False  # Estado para alternar el blink
        self.rightBlinkOn = False

        self.leftBlinkTimer = QtCore.QTimer(self)
        self.leftBlinkTimer.setInterval(500)
        self.leftBlinkTimer.timeout.connect(self.blinkLeftLight)

        self.rightBlinkTimer = QtCore.QTimer(self)
        self.rightBlinkTimer.setInterval(500)
        self.rightBlinkTimer.timeout.connect(self.blinkRightLight)
        
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        
        # Encabezado
        header = QtWidgets.QLabel("Dashboard", self)
        header.setObjectName("TitleLabel")
        header.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header)
        
        # Sección superior: D-Pad (izquierda), Indicadores (centro), Luces direccionales (derecha)
        top_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(top_layout)
        
        # D-Pad
        dpad = QtWidgets.QWidget(self)
        dpad_layout = QtWidgets.QGridLayout(dpad)
        btn_size = 50
        self.btnUp = QtWidgets.QPushButton("↑")
        self.btnDown = QtWidgets.QPushButton("↓")
        self.btnLeft = QtWidgets.QPushButton("←")
        self.btnRight = QtWidgets.QPushButton("→")
        self.btnStop = QtWidgets.QPushButton("■")
        for btn in [self.btnUp, self.btnDown, self.btnLeft, self.btnRight, self.btnStop]:
            btn.setFixedSize(btn_size, btn_size)
            btn.setStyleSheet("font-size: 16px;")
        dpad_layout.addWidget(self.btnUp, 0, 1)
        dpad_layout.addWidget(self.btnLeft, 1, 0)
        dpad_layout.addWidget(self.btnStop, 1, 1)
        dpad_layout.addWidget(self.btnRight, 1, 2)
        dpad_layout.addWidget(self.btnDown, 2, 1)
        top_layout.addWidget(dpad)
        
        # Indicadores: Odómetro y Tacómetro
        gauges = QtWidgets.QWidget(self)
        gauges_layout = QtWidgets.QVBoxLayout(gauges)
        self.speedGauge = GaugeWidget("speed", 0, 400, self)
        self.tachGauge = GaugeWidget("rpm", 0, 6000, self)
        gauges_layout.addWidget(self.speedGauge)
        gauges_layout.addWidget(self.tachGauge)
        top_layout.addWidget(gauges)
        
        # Luces direccionales (inicialmente con color inactivo)
        lights = QtWidgets.QWidget(self)
        lights_layout = QtWidgets.QVBoxLayout(lights)
        self.labelLuzIzq = QtWidgets.QLabel("←", self)
        self.labelLuzDer = QtWidgets.QLabel("→", self)
        self.labelLuzIzq.setStyleSheet("font-size: 24px; color: #888;")
        self.labelLuzDer.setStyleSheet("font-size: 24px; color: #888;")
        lights_layout.addWidget(self.labelLuzIzq)
        lights_layout.addWidget(self.labelLuzDer)
        top_layout.addWidget(lights)
        
        # Sección central: Placeholder
        center = QtWidgets.QWidget(self)
        center_layout = QtWidgets.QVBoxLayout(center)
        self.placeholder_label = QtWidgets.QLabel("Entorno de prueba / real", self)
        self.placeholder_label.setStyleSheet("color: #FFF; font-size: 20px;")
        self.placeholder_label.setAlignment(QtCore.Qt.AlignCenter)
        self.placeholder_label.setFixedSize(400, 200)
        center_layout.addWidget(self.placeholder_label, alignment=QtCore.Qt.AlignCenter)
        layout.addWidget(center)
        
        # Sección inferior: Panel de funciones
        bottom = QtWidgets.QWidget(self)
        bottom_layout = QtWidgets.QHBoxLayout(bottom)
        self.btnFrenoAuto = QtWidgets.QPushButton("Freno Automático", self)
        self.btnLucesDireccionales = QtWidgets.QPushButton("Luces Direccionales", self)
        self.btnPanelVel = QtWidgets.QPushButton("Panel Velocidad (N-1-7)", self)
        self.btnAutomatico = QtWidgets.QPushButton("Automático", self)
        self.btnRR4 = QtWidgets.QPushButton("R-R4", self)
        for btn in [self.btnFrenoAuto, self.btnLucesDireccionales, self.btnPanelVel, self.btnAutomatico, self.btnRR4]:
            btn.setStyleSheet("font-size: 14px; padding: 10px;")
            bottom_layout.addWidget(btn)
        layout.addWidget(bottom)
        
        # Mapear teclas según settings
        self.map_forward = self.settings.get("forward_key", "r")
        self.map_backward = self.settings.get("backward_key", "a")
        self.map_stop = self.settings.get("stop_key", "p")
        self.map_luz_izq = self.settings.get("luces_direccion_izquierda", "q")
        self.map_luz_der = self.settings.get("luces_direccion_derecha", "e")
        self.speed_change_key = self.settings.get("speed_change_key", "c")
        
        self.app = QtWidgets.QApplication.instance()
        self.app.installEventFilter(self)
        
        # Timer para desaceleración (inercia)
        self.decel_timer = QtCore.QTimer(self)
        self.decel_timer.setInterval(100)
        self.decel_timer.timeout.connect(self.decelerate_gauges)
        self.decel_timer.start()
        
        # Si hay conexión serial, iniciar timer para actualizar datos reales
        if self.serialConnection:
            self.serial_timer = QtCore.QTimer(self)
            self.serial_timer.setInterval(100)
            self.serial_timer.timeout.connect(self.updateFromSerial)
            self.serial_timer.start()
        
        # Establecer valores iniciales en los gauges
        self.speedGauge.setLimitValue(self.limit_speed)
        self.tachGauge.setLimitValue(self.limit_rpm)
        self.speedGauge.setValue(self.odometer)
        self.tachGauge.setValue(self.rpm)

    def updateFromSerial(self):
        """
        Lee líneas del serial con formato 'VEL=<valor> RPM=<valor>'
        y actualiza los gauges de odómetro y tacómetro.
        """
        try:
            # Mientras haya datos disponibles
            while self.serialConnection and self.serialConnection.in_waiting:
                line = self.serialConnection.readline().decode("utf-8", errors="ignore").strip()
                # Ejemplo de línea: "VEL=155 RPM=1200"
                if line.startswith("VEL=") and "RPM=" in line:
                    # Separar en ["VEL=155", "RPM=1200"]
                    parts = line.split()
                    data = {}
                    for part in parts:
                        if "=" in part:
                            key, val = part.split("=", 1)
                            data[key] = int(val)

                    # --- Actualizar velocidad ---
                    if "VEL" in data:
                        vel = data["VEL"]
                        # Asegurar dentro del límite del engranaje actual
                        lim_speed = gearMapping[self.currentGear]["maxSpeed"]
                        vel = max(0, min(vel, lim_speed))
                        self.odometer = vel
                        self.speedGauge.setLimitValue(lim_speed)
                        self.speedGauge.setValue(self.odometer)

                    # --- Actualizar RPM ---
                    if "RPM" in data:
                        rpm_val = data["RPM"]
                        lim_rpm = gearMapping[self.currentGear]["maxRPM"]
                        rpm_val = max(0, min(rpm_val, lim_rpm))
                        self.rpm = rpm_val
                        self.tachGauge.setLimitValue(lim_rpm)
                        self.tachGauge.setValue(self.rpm)
        except Exception as e:
            print("Error leyendo datos serial en updateFromSerial:", e)


    def decelerate_gauges(self):
        changed = False
        # En modo simulado se desacelera gradualmente si no se mantiene presionado
        if self.odometer > 0:
            self.odometer = max(0, self.odometer - 2)
            changed = True
        if self.rpm > 0:
            self.rpm = max(0, self.rpm - 150)
            changed = True
        if changed:
            self.speedGauge.setValue(self.odometer)
            self.tachGauge.setValue(self.rpm)
            if self.odometer == 0:
                self.currentGear = "N"
                self.speedGauge.setLimitValue(gearMapping["N"]["maxSpeed"])
                self.tachGauge.setLimitValue(gearMapping["N"]["maxRPM"])

    def blinkLeftLight(self):
        # Alterna el color entre amarillo y inactivo
        self.leftBlinkOn = not self.leftBlinkOn
        if self.leftBlinkOn:
            self.labelLuzIzq.setStyleSheet("font-size: 24px; color: yellow;")
        else:
            self.labelLuzIzq.setStyleSheet("font-size: 24px; color: #888;")

    def blinkRightLight(self):
        self.rightBlinkOn = not self.rightBlinkOn
        if self.rightBlinkOn:
            self.labelLuzDer.setStyleSheet("font-size: 24px; color: yellow;")
        else:
            self.labelLuzDer.setStyleSheet("font-size: 24px; color: #888;")
        
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress:
            key = event.text()
            # Modo real: se envían comandos al Arduino
            if self.serialConnection:
                real_key_to_command = {
                    self.map_forward: b'a',
                    self.map_backward: b'r',
                    self.settings.get("left_key", "i"): b'i',
                    self.settings.get("right_key", "d"): b'd',
                    ' ': b'p'
                }
                if key in real_key_to_command:
                    self.serialConnection.write(real_key_to_command[key])
                    print(f"Comando enviado: {real_key_to_command[key].decode()}")
                if key in ['1','2','3','4','5','6','7']:
                    self.serialConnection.write(key.encode())
                    print(f"Comando enviado: {key}")
                if key == self.speed_change_key:
                    current_index = int(self.currentGear) if self.currentGear.isdigit() else 1
                    new_index = current_index + 1 if current_index < 7 else 1
                    self.currentGear = str(new_index)
                    gear_limits = gearMapping[self.currentGear]
                    self.odometer = gear_limits["maxSpeed"]
                    self.rpm = gear_limits["maxRPM"]
                    self.speedGauge.setValue(self.odometer)
                    self.tachGauge.setValue(self.rpm)
                    self.speedGauge.setLimitValue(gear_limits["maxSpeed"])
                    self.tachGauge.setLimitValue(gear_limits["maxRPM"])
                    print(f"Cambio de velocidad: {self.currentGear}")
                    self.serialConnection.write(self.currentGear.encode())
            else:
                # Modo simulado
                if key == self.map_forward:
                    gear_limits = gearMapping.get(self.currentGear, {"maxSpeed":400, "maxRPM":6000})
                    self.odometer = min(self.odometer + ACC_STEP, gear_limits["maxSpeed"])
                    self.rpm = min(self.rpm + ACC_STEP*10, gear_limits["maxRPM"])
                    self.speedGauge.setValue(self.odometer)
                    self.tachGauge.setValue(self.rpm)
                elif key == self.map_backward:
                    self.odometer = max(0, self.odometer - ACC_STEP)
                    self.rpm = max(0, self.rpm - ACC_STEP*10)
                    self.speedGauge.setValue(self.odometer)
                    self.tachGauge.setValue(self.rpm)
                elif key == self.map_stop or key == self.settings.get("auto_brake_key", "b"):
                    self.odometer = 0
                    self.rpm = 0
                    self.speedGauge.setValue(self.odometer)
                    self.tachGauge.setValue(self.rpm)
                    self.currentGear = "N"
                    self.speedGauge.setLimitValue(gearMapping["N"]["maxSpeed"])
                    self.tachGauge.setLimitValue(gearMapping["N"]["maxRPM"])
                elif key in ['1','2','3','4','5','6','7','N','R']:
                    if key == "N":
                        self.odometer = 0
                        self.currentGear = "N"
                    elif key == "R":
                        self.odometer = gearMapping["R"]["maxSpeed"]
                        self.currentGear = "R"
                    else:
                        gear_limits = gearMapping[key]
                        self.odometer = gear_limits["maxSpeed"]
                        self.currentGear = key
                    gear_limits = gearMapping.get(self.currentGear, {"maxSpeed":400, "maxRPM":6000})
                    self.rpm = gear_limits["maxRPM"]
                    self.speedGauge.setValue(self.odometer)
                    self.tachGauge.setValue(self.rpm)
                    self.speedGauge.setLimitValue(gear_limits["maxSpeed"])
                    self.tachGauge.setLimitValue(gear_limits["maxRPM"])
                # Soporte para luces direccionales: se activa o desactiva al pulsar su tecla
                if key == self.map_luz_izq:
                    self.leftLightOn = not self.leftLightOn
                    if self.leftLightOn:
                        self.leftBlinkTimer.start()
                    else:
                        self.leftBlinkTimer.stop()
                        self.labelLuzIzq.setStyleSheet("font-size: 24px; color: #888;")
                if key == self.map_luz_der:
                    self.rightLightOn = not self.rightLightOn
                    if self.rightLightOn:
                        self.rightBlinkTimer.start()
                    else:
                        self.rightBlinkTimer.stop()
                        self.labelLuzDer.setStyleSheet("font-size: 24px; color: #888;")
        return super().eventFilter(obj, event)
    
    def keyReleaseEvent(self, event):
        released_key = event.text()
        movement_keys = [
            self.map_forward, self.map_backward,
            self.settings.get("left_key", "i"),
            self.settings.get("right_key", "d"), ' '
        ]
        if released_key in movement_keys and self.serialConnection:
            self.serialConnection.write(b'p')
            print("Comando enviado: p")
        super().keyReleaseEvent(event)

# --- MENÚ PRINCIPAL ---
class MenuWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Control de Carrito Arduino")
        self.setFixedSize(400, 350)
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        title = QtWidgets.QLabel("Control de Carrito Arduino", self)
        title.setObjectName("TitleLabel")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        self.test_button = QtWidgets.QPushButton("Prueba", self)
        self.test_button.setStyleSheet("font-size: 16px; padding: 15px;")
        self.test_button.setIcon(QIcon("Test.png"))
        self.test_button.setIconSize(QtCore.QSize(24, 24))
        self.test_button.clicked.connect(self.abrir_test)
        layout.addWidget(self.test_button)
        self.connect_button = QtWidgets.QPushButton("Conectar Bluetooth", self)
        self.connect_button.setStyleSheet("font-size: 16px; padding: 15px;")
        self.connect_button.setIcon(QIcon("bluetooth.png"))
        self.connect_button.setIconSize(QtCore.QSize(24, 24))
        self.connect_button.clicked.connect(self.conectar_bluetooth)
        layout.addWidget(self.connect_button)
        self.config_button = QtWidgets.QPushButton("Configuración", self)
        self.config_button.setStyleSheet("font-size: 16px; padding: 15px;")
        self.config_button.setIcon(QIcon("Settings.png"))
        self.config_button.setIconSize(QtCore.QSize(24, 24))
        self.config_button.clicked.connect(self.open_config)
        layout.addWidget(self.config_button)
        self.examples_button = QtWidgets.QPushButton("Ejemplos", self)
        self.examples_button.setStyleSheet("font-size: 16px; padding: 15px;")
        self.examples_button.setIcon(QIcon("Credits.png"))
        self.examples_button.setIconSize(QtCore.QSize(24, 24))
        self.examples_button.clicked.connect(self.open_examples)
        layout.addWidget(self.examples_button)
        self.bluetooth_button = QtWidgets.QPushButton("Encender Bluetooth", self)
        self.bluetooth_button.setStyleSheet("font-size: 16px; padding: 15px;")
        self.bluetooth_button.setIcon(QIcon("bluetooth.png"))
        self.bluetooth_button.setIconSize(QtCore.QSize(24, 24))
        self.bluetooth_button.clicked.connect(self.enable_bluetooth)
        layout.addWidget(self.bluetooth_button)
        self.status_label = QtWidgets.QLabel("", self)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)
        self.settings = load_settings()

    def abrir_test(self):
        self.test_window = TestWindow(self.settings, serialConnection=None, parent=self)
        self.test_window.show()

    def conectar_bluetooth(self):
        try:
            puerto = encontrar_puerto_bluetooth()
            if not puerto:
                self.status_label.setText("No se encontró HC-06. Usando COM4 por defecto.")
                puerto = "COM4"
            else:
                self.status_label.setText(f"Puerto detectado: {puerto}")
            baud_rate = 9600
            try:
                ser = serial.Serial(puerto, baud_rate, timeout=1)
                time.sleep(2)
                print(f"Conectado al carrito por Bluetooth en {puerto}")
                self.control_window = TestWindow(self.settings, serialConnection=ser, parent=self)
                self.control_window.show()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error de conexión",
                    f"No se pudo conectar al puerto {puerto}.\nError: {str(e)}")
                self.status_label.setText("Estado: Error en la conexión.")
        except Exception as ex:
            QtWidgets.QMessageBox.critical(self, "Error inesperado",
                    f"Ocurrió un error inesperado:\n{str(ex)}")
            self.status_label.setText("Estado: Error inesperado.")

    def open_config(self):
        config_dialog = ConfigWindow(self.settings, self)
        if config_dialog.exec() == QtWidgets.QDialog.Accepted:
            print("Configuración aceptada")
        else:
            print("Configuración cancelada")

    def open_examples(self):
        examples_dialog = ExamplesWindow(self)
        examples_dialog.exec()

    def enable_bluetooth(self):
        try:
            subprocess.run(["powershell", "-Command",
                "Set-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Bluetooth\\Radio\\{00010000-0000-0000-0000-000000000000} -Name RadioEnabled -Value 1"],
                check=True)
            self.status_label.setText("Bluetooth Encendido")
        except subprocess.CalledProcessError as e:
            QtWidgets.QMessageBox.critical(self, "Error al encender Bluetooth",
                    f"No se pudo encender el Bluetooth:\n{str(e)}")
            self.status_label.setText("Error al encender Bluetooth")

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(DASHBOARD_STYLE)
    settings = load_settings()
    window = MenuWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

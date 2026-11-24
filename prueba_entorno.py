import sys
import platform

print("Hola desde mi Codespace")
print(f"Versión de Python: {platform.python_version()}")
print(f"Ubicación de Python: {sys.executable}")

if sys.version_info[:2] == (3, 12):
    print("OK: el entorno usa Python 3.12, la versión del curso")
else:
    print("ATENCIÓN: este entorno no usa Python 3.12")
import sys
import os

# Caminho para o diretório do seu projeto
project_home = os.path.dirname(os.path.abspath(__file__))

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Importe o objeto Flask como "application" para o PythonAnywhere
from app import app as application

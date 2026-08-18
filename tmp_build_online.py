import sys
from pathlib import Path
sys.path.insert(0, r"D:\Projetos\SIG Windows\scripts")
from release import build_installer_online

result = build_installer_online(Path(r"D:\Projetos\SIG Windows"), "20260817_010")
print("RESULTADO:", result)

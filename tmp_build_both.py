import sys
from pathlib import Path
sys.path.insert(0, r"D:\Projetos\SIG Windows\scripts")
from release import build_installer, build_installer_online

root = Path(r"D:\Projetos\SIG Windows")
offline = build_installer(root, "20260817_010")
online = build_installer_online(root, "20260817_010")
print("OFFLINE:", offline)
print("ONLINE:", online)

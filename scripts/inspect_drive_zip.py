"""Inspeciona o ZIP 006 publicado no Drive (verificação pós-publicação)."""
import hashlib
import io
import json
import sys
import zipfile

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDENTIALS = r"D:\Projetos\credentials.json"
TOKEN = r"D:\Projetos\token.json"

if __import__("os").path.exists(TOKEN):
    creds = Credentials.from_authorized_user_file(TOKEN)
else:
    sys.exit("token_drive.json não encontrado em D:/Projetos")

service = build("drive", "v3", credentials=creds)

manifest = json.load(open(r"D:\Projetos\SIG Windows\release\latest.json", encoding="utf-8"))
file_id = manifest["zip_file_id"]
print("manifest version:", manifest["version"])
print("zip_file_id:", file_id)
print("expected sha256:", manifest["sha256"])
print("expected size:", manifest["size"])

request = service.files().get_media(fileId=file_id)
from googleapiclient.http import MediaIoBaseDownload
buf = io.BytesIO()
downloader = MediaIoBaseDownload(buf, request)
done = False
while not done:
    _, done = downloader.next_chunk()
data = buf.getvalue()
print("downloaded bytes:", len(data))
print("sha256:", hashlib.sha256(data).hexdigest())
print("sha256 confere:", hashlib.sha256(data).hexdigest() == manifest["sha256"])
print("size confere:", len(data) == manifest["size"])

z = zipfile.ZipFile(io.BytesIO(data))
names = z.namelist()
print("total membros:", len(names))
for n in sorted(names)[:40]:
    print(" ", n)
big = sorted(((i.file_size, i.filename) for i in z.infolist()), reverse=True)[:5]
print("maiores:", big)

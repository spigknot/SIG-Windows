import base64, json, sys, time, threading
from pathlib import Path
import websocket

settings_path = Path(r"C:\Users\Gustavo\AppData\Roaming\sig\settings.json")
settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        pass
API_KEY = str(settings.get("elevenlabs_api_key") or "").strip()
URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

pcm = Path(r"C:\Users\Gustavo\AppData\Local\Temp\scribe_fala.pcm").read_bytes()
half = len(pcm) // 2
# insere 2.5s de silencio no meio (pausa longa -> VAD commita)
pausa = b"\x00\x00" * int(16000 * 2.5)
pcm_com_pausa = pcm[:half] + pausa + pcm[half:]
BLOCK = 3200

events = []
def on_open(ws): events.append(("OPEN",))
def on_message(ws, msg): events.append(("MSG", str(msg)))
def on_error(ws, err): events.append(("ERR", str(err)[:70]))
def on_close(ws, code, reason): events.append(("CLOSE", code, str(reason)[:50]))

q = "model_id=scribe_v2_realtime&audio_format=pcm_16000&language_code=pt&commit_strategy=vad&vad_silence_threshold_secs=1.0"
app = websocket.WebSocketApp(f"{URL}?{q}", header=[f"xi-api-key: {API_KEY}"],
    on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
threading.Thread(target=app.run_forever, daemon=True).start()
time.sleep(1.5)
sent = 0
for i in range(0, len(pcm_com_pausa), BLOCK):
    chunk = pcm_com_pausa[i:i+BLOCK]
    if not chunk:
        break
    if not app.sock:
        print("fechou no bloco", i // BLOCK)
        break
    try:
        app.send(json.dumps({"message_type": "input_audio_chunk",
                             "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                             "commit": False, "sample_rate": 16000}))
        sent += 1
    except Exception as exc:
        print("falha no bloco", i // BLOCK, str(exc)[:50])
        break
    time.sleep(0.1)
print(f"blocos enviados: {sent}")
time.sleep(5)
print(f"--- eventos ({len(events)}) ---")
for e in events:
    print("   ", e)
app.close()

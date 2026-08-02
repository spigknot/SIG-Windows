"""Aplica VAD em WAV PCM e grava um novo WAV contendo somente voz."""

import json
import os
import sys
import time
import wave
from pathlib import Path


SILERO_LEVELS = {
    "0": {
        "threshold": 0.40,
        "min_speech_duration_ms": 120,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 200,
    },
    "1": {
        "threshold": 0.50,
        "min_speech_duration_ms": 200,
        "min_silence_duration_ms": 350,
        "speech_pad_ms": 120,
    },
    "2": {
        "threshold": 0.60,
        "min_speech_duration_ms": 300,
        "min_silence_duration_ms": 250,
        "speech_pad_ms": 80,
    },
    "3": {
        "threshold": 0.70,
        "min_speech_duration_ms": 400,
        "min_silence_duration_ms": 150,
        "speech_pad_ms": 40,
    },
}


def _configure_dependencies(path):
    deps = Path(path)
    if not deps.is_dir():
        raise RuntimeError(f"pasta de dependências não encontrada: {deps}")
    sys.path.insert(0, str(deps))
    if os.name == "nt":
        candidates = [deps, deps / "numpy.libs", deps / "onnxruntime" / "capi"]
        for candidate in candidates:
            if candidate.is_dir():
                try:
                    os.add_dll_directory(str(candidate))
                except OSError:
                    pass


def _read_pcm(path):
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        compression = source.getcomptype()
        pcm = source.readframes(frame_count)
    if (channels, sample_width, sample_rate, compression) != (1, 2, 16000, "NONE"):
        raise ValueError("o VAD exige WAV PCM 16 kHz, mono e 16-bit")
    return pcm, frame_count, sample_rate


def _merge_segments(segments, total_frames):
    normalized = []
    for start, end in segments:
        start = max(0, min(total_frames, int(start)))
        end = max(start, min(total_frames, int(end)))
        if end <= start:
            continue
        if normalized and start <= normalized[-1][1]:
            normalized[-1] = (normalized[-1][0], max(normalized[-1][1], end))
        else:
            normalized.append((start, end))
    return normalized


def _write_filtered_wav(output_path, pcm, segments, sample_rate):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        for start, end in segments:
            target.writeframesraw(pcm[start * 2 : end * 2])


def _silero_detector(level):
    import numpy as np
    import onnxruntime

    deps = Path(sys.path[0])
    model_path = deps / "models" / "silero_vad.onnx"
    if not model_path.is_file():
        legacy_path = deps / "silero_vad" / "data" / "silero_vad_16k_op15.onnx"
        if legacy_path.is_file():
            model_path = legacy_path
        else:
            raise RuntimeError(f"modelo Silero ONNX não encontrado: {model_path}")
    options = onnxruntime.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    session = onnxruntime.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )
    params = SILERO_LEVELS[str(level)]

    def detect(pcm, frame_count, sample_rate):
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        window_samples = 512
        context_samples = 64
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, context_samples), dtype=np.float32)
        sample_rate_input = np.array(sample_rate, dtype=np.int64)
        probabilities = []
        for offset in range(0, frame_count, window_samples):
            chunk = audio[offset : offset + window_samples]
            if chunk.size < window_samples:
                chunk = np.pad(chunk, (0, window_samples - chunk.size))
            model_input = np.concatenate((context, chunk.reshape(1, -1)), axis=1)
            output, state = session.run(
                None,
                {"input": model_input, "state": state, "sr": sample_rate_input},
            )
            probabilities.append(float(output.reshape(-1)[0]))
            context = model_input[:, -context_samples:]

        threshold = float(params["threshold"])
        negative_threshold = max(threshold - 0.15, 0.01)
        minimum_speech = sample_rate * int(params["min_speech_duration_ms"]) / 1000
        minimum_silence = sample_rate * int(params["min_silence_duration_ms"]) / 1000
        speech_pad = int(sample_rate * int(params["speech_pad_ms"]) / 1000)
        triggered = False
        temporary_end = 0
        current_start = 0
        segments = []
        for index, probability in enumerate(probabilities):
            current_sample = index * window_samples
            if probability >= threshold:
                if temporary_end:
                    temporary_end = 0
                if not triggered:
                    triggered = True
                    current_start = current_sample
                continue
            if probability < negative_threshold and triggered:
                if not temporary_end:
                    temporary_end = current_sample
                if current_sample - temporary_end < minimum_silence:
                    continue
                if temporary_end - current_start > minimum_speech:
                    segments.append([current_start, temporary_end])
                triggered = False
                temporary_end = 0
        if triggered and frame_count - current_start > minimum_speech:
            segments.append([current_start, frame_count])

        for index, segment in enumerate(segments):
            if index == 0:
                segment[0] = max(0, segment[0] - speech_pad)
            if index == len(segments) - 1:
                segment[1] = min(frame_count, segment[1] + speech_pad)
                continue
            silence = segments[index + 1][0] - segment[1]
            if silence < 2 * speech_pad:
                half_silence = silence // 2
                segment[1] += half_silence
                segments[index + 1][0] = max(0, segments[index + 1][0] - half_silence)
            else:
                segment[1] = min(frame_count, segment[1] + speech_pad)
                segments[index + 1][0] = max(0, segments[index + 1][0] - speech_pad)
        return _merge_segments(segments, frame_count)

    return detect


def _webrtc_detector(level):
    import webrtcvad

    aggressiveness = int(level)

    def detect(pcm, frame_count, sample_rate):
        vad = webrtcvad.Vad(aggressiveness)
        frame_samples = sample_rate * 30 // 1000
        frame_bytes = frame_samples * 2
        segments = []
        speech_start = None
        complete_bytes = len(pcm) - (len(pcm) % frame_bytes)
        for offset in range(0, complete_bytes, frame_bytes):
            speaking = vad.is_speech(pcm[offset : offset + frame_bytes], sample_rate)
            frame_start = offset // 2
            if speaking and speech_start is None:
                speech_start = frame_start
            elif not speaking and speech_start is not None:
                segments.append((speech_start, frame_start))
                speech_start = None
        if speech_start is not None:
            segments.append((speech_start, complete_bytes // 2))
        return _merge_segments(segments, frame_count)

    return detect


def _process_file(item, detect):
    input_path = Path(item["input"])
    output_path = Path(item["output"])
    started = time.perf_counter()
    try:
        pcm, frame_count, sample_rate = _read_pcm(input_path)
        segments = detect(pcm, frame_count, sample_rate)
        if not segments:
            raise RuntimeError("nenhum trecho de voz foi detectado")
        _write_filtered_wav(output_path, pcm, segments, sample_rate)
        speech_frames = sum(end - start for start, end in segments)
        return {
            "input": str(input_path),
            "output": str(output_path),
            "ok": True,
            "input_bytes": input_path.stat().st_size,
            "output_bytes": output_path.stat().st_size,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "speech_duration": speech_frames / sample_rate,
            "total_duration": frame_count / sample_rate,
            "segment_count": len(segments),
        }
    except Exception as exc:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "input": str(input_path),
            "output": str(output_path),
            "ok": False,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "error": str(exc),
        }


def main():
    request = json.loads(sys.stdin.read())
    _configure_dependencies(request["vad_deps"])
    level = str(request.get("level", "1"))
    if level not in {"0", "1", "2", "3"}:
        raise ValueError(f"nível de agressividade inválido: {level}")
    vad_type = request.get("vad_type")
    if vad_type == "silero":
        detect = _silero_detector(level)
    elif vad_type == "webrtc":
        detect = _webrtc_detector(level)
    else:
        raise ValueError(f"tipo de VAD inválido: {vad_type}")
    for item in request.get("files", []):
        result = _process_file(item, detect)
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

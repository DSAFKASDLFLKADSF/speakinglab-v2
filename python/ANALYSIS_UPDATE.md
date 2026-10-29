# Acoustic analysis and Tencent SOE update

## Changes

- Decode recordings at 16 kHz and resample supplied arrays to the same rate, so the 20 ms silence windows have the same meaning on 16/44.1/48 kHz devices.
- Share the short-window RMS envelope between pause detection and speech-span measurement; measure pitch every 20 ms instead of every 10 ms.
- Count explicit vocal fillers (um, uh, erm, hmm); do not automatically penalize lexical uses of like, kind of, or you know.
- Return zero articulation rate for a silent waveform even if ASR supplies text; invalid non-finite waveforms use the existing explicitly labeled transcript fallback.
- Convert browser recordings to 16 kHz / 16-bit / mono PCM for Tencent SOE. Conversion stays in memory and rejects recordings longer than 180 seconds instead of truncating them.
- Use TransmitOralProcessWithInit with UserVoiceData and one-shot WorkMode=1. Free-speaking evaluation uses EvalMode=3; sentence repetition retains EvalMode=1.
- Convert Tencent fluency/completion fractions to the application's 0–100 scale. Preserve unavailable values as None; do not replace missing fluency with accuracy.
- Parse word times by field units, including Tencent MemBeginTime/MemEndTime.
- Default ScoreCoeff to adult strictness 4.0, configurable with TENCENT_SOE_SCORE_COEFF. This changes provider grading and should be checked with representative recordings.

## Validation

All 67 Python unittest cases passed offline, including generated stereo 48 kHz WebM/Opus, WAV/PCM round trips, sample-rate consistency, silent/invalid inputs, and mocked Tencent requests/responses.

Command: `python -m unittest discover -s python/tests -v`

Validation runtime: Python 3.12 with ffmpeg. The target server uses Python 3.10; run the same suite there before deploying. No Tencent or Qwen requests were made and no production credentials were used.

## Local timing experiment

Input: generated 45-second, 48 kHz mono tone with regular silence; both implementations warmed first; median of three calls in the same test environment.

| Metric | Before | After |
| --- | ---: | ---: |
| Analysis wall time | 0.9414 s | 0.1418 s |
| Recording duration | 45.0 s | 45.0 s |
| Internal pause count | 14 | 14 |
| Longest pause | 0.50 s | 0.49 s |
| Median pitch | 180.7 Hz | 180.2 Hz |

This is a synthetic acoustic-analysis benchmark, not a measurement of production latency or scoring accuracy. ASR, speech evaluation, and language-model calls are separate costs. Background-noise robustness and teacher score calibration still require representative recordings.

## Deployment notes

This change does not add the Qwen client or the user-facing model selector. The current GLM client still sends vendor-specific parameters, so changing only the key/model environment variables is insufficient for Qwen.

Before Tencent SOE validation, set SPEECH_EVAL_PROVIDER=tencent, remove any old TENCENT_SOE_EVAL_MODE_FREE=0 override, and use TENCENT_SOE_EVAL_MODE_FREE=3. Keep TENCENT_SOE_VOICE_FILE_TYPE at 1 (PCM) or 2 (WAV), and TENCENT_SOE_VOICE_ENCODE_TYPE=1. This application converts the source container automatically; do not describe WebM bytes as PCM.

The Tencent ASR adapter also needs integration validation: it currently requests ResTextFormat=0, and browser WebM plus word-offset parsing need attention before relying on word-level hesitation timestamps. It is outside this SOE/acoustics patch.

Official references:
- https://cloud.tencent.com/document/api/884/32605
- https://cloud.tencent.com/document/api/1093/37823
- https://help.aliyun.com/zh/model-studio/qwen3-8-max
- https://help.aliyun.com/zh/model-studio/qwen3-8-flash

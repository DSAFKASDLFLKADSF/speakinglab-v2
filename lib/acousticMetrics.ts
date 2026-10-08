/** Normalized waveform metrics shared by the Python API and web app. */
export interface PythonAcousticMetrics {
  duration_seconds: number;
  speech: {
    word_count: number;
    wpm: number;
    articulation_rate: number;
  };
  pauses: {
    pause_count: number;
    long_pause_count: number;
    longest_pause: number;
    total_pause_time: number;
    pause_ratio: number;
  };
  fillers: { count: number };
  prosody: {
    pitch_median: number | null;
    pitch_variation: number | null;
    energy_variation: number | null;
  };
  source: string;
}

export interface AcousticMetrics {
  durationSeconds: number;
  speech: {
    wordCount: number;
    wpm: number;
    articulationRate: number;
  };
  pauses: {
    pauseCount: number;
    longPauseCount: number;
    longestPause: number;
    totalPauseTime: number;
    pauseRatio: number;
  };
  fillers: { count: number };
  prosody: {
    pitchMedian: number | null;
    pitchVariation: number | null;
    energyVariation: number | null;
  };
  source: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isNonnegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isRatio(value: unknown): value is number {
  return isNonnegativeNumber(value) && value <= 1;
}

function isNullableNonnegativeNumber(value: unknown): value is number | null {
  return value === null || isNonnegativeNumber(value);
}

export function mapAcousticMetrics(
  raw: PythonAcousticMetrics | null | undefined
): AcousticMetrics | undefined {
  if (!isRecord(raw)) {
    return undefined;
  }

  const speech = raw.speech;
  const pauses = raw.pauses;
  const fillers = raw.fillers;
  const prosody = raw.prosody;
  if (
    !isRecord(speech) ||
    !isRecord(pauses) ||
    !isRecord(fillers) ||
    !isRecord(prosody) ||
    !isNonnegativeNumber(raw.duration_seconds) ||
    !isCount(speech.word_count) ||
    !isNonnegativeNumber(speech.wpm) ||
    !isNonnegativeNumber(speech.articulation_rate) ||
    !isCount(pauses.pause_count) ||
    !isCount(pauses.long_pause_count) ||
    !isNonnegativeNumber(pauses.longest_pause) ||
    !isNonnegativeNumber(pauses.total_pause_time) ||
    !isRatio(pauses.pause_ratio) ||
    !isCount(fillers.count) ||
    !isNullableNonnegativeNumber(prosody.pitch_median) ||
    !isNullableNonnegativeNumber(prosody.pitch_variation) ||
    !isNullableNonnegativeNumber(prosody.energy_variation) ||
    typeof raw.source !== "string" ||
    raw.source.trim().length === 0
  ) {
    return undefined;
  }

  return {
    durationSeconds: raw.duration_seconds,
    speech: {
      wordCount: speech.word_count,
      wpm: speech.wpm,
      articulationRate: speech.articulation_rate,
    },
    pauses: {
      pauseCount: pauses.pause_count,
      longPauseCount: pauses.long_pause_count,
      longestPause: pauses.longest_pause,
      totalPauseTime: pauses.total_pause_time,
      pauseRatio: pauses.pause_ratio,
    },
    fillers: { count: fillers.count },
    prosody: {
      pitchMedian: prosody.pitch_median,
      pitchVariation: prosody.pitch_variation,
      energyVariation: prosody.energy_variation,
    },
    source: raw.source,
  };
}

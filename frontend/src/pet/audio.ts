export const MIN_RECORDING_MS = 300;
export const MAX_RECORDING_MS = 15_000;
const ASR_WAV_SAMPLE_RATE = 16_000;

export class RecordingTooShortError extends Error {
  constructor() {
    super("recording_too_short");
    this.name = "RecordingTooShortError";
  }
}

export class MicrophonePermissionError extends Error {
  reason: "insecure_context" | "missing_api" | "permission_denied";

  constructor(
    reason: "insecure_context" | "missing_api" | "permission_denied" = "permission_denied"
  ) {
    super("microphone_unavailable");
    this.name = "MicrophonePermissionError";
    this.reason = reason;
  }
}

export type VoiceRecordingSession = {
  stop: () => Promise<Blob>;
  cancel: () => void;
  finished: Promise<Blob>;
};

type RecordingOptions = {
  mediaDevices?: MediaDeviceSource;
  mediaRecorderCtor?: typeof MediaRecorder;
  audioContextCtor?: typeof AudioContext;
};

type MediaDeviceSource = Pick<MediaDevices, "getUserMedia">;

type LegacyNavigatorMedia = Navigator & {
  getUserMedia?: (
    constraints: MediaStreamConstraints,
    success: (stream: MediaStream) => void,
    error: (err: unknown) => void
  ) => void;
  webkitGetUserMedia?: (
    constraints: MediaStreamConstraints,
    success: (stream: MediaStream) => void,
    error: (err: unknown) => void
  ) => void;
  mozGetUserMedia?: (
    constraints: MediaStreamConstraints,
    success: (stream: MediaStream) => void,
    error: (err: unknown) => void
  ) => void;
  msGetUserMedia?: (
    constraints: MediaStreamConstraints,
    success: (stream: MediaStream) => void,
    error: (err: unknown) => void
  ) => void;
};

class UnsupportedWavRecorderError extends Error {
  constructor() {
    super("wav_recorder_unavailable");
    this.name = "UnsupportedWavRecorderError";
  }
}

class UnsupportedMediaRecorderError extends Error {
  constructor() {
    super("media_recorder_unavailable");
    this.name = "UnsupportedMediaRecorderError";
  }
}

export function assertRecordingDuration(durationMs: number) {
  if (durationMs < MIN_RECORDING_MS) {
    throw new RecordingTooShortError();
  }
}

export async function createVoiceRecordingSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  if (shouldPreferWavRecorder()) {
    return createWavRecordingSession(options);
  }
  try {
    return await createMediaRecorderSession(options);
  } catch (error) {
    if (error instanceof MicrophonePermissionError) {
      throw error;
    }
  }
  return createWavRecordingSession(options);
}

function shouldPreferWavRecorder(): boolean {
  const ua = navigator.userAgent;
  const chromeMatch = ua.match(/(?:Chrome|Chromium)\/(\d+)/);
  if (!chromeMatch) {
    return false;
  }
  const major = Number(chromeMatch[1]);
  if (!Number.isFinite(major) || major <= 0 || major > 55) {
    return false;
  }
  return /\bwv\b/.test(ua) || /Version\/4\.0/.test(ua);
}

async function createWavRecordingSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  const mediaDevices = options.mediaDevices ?? getMediaDeviceSource();
  const AudioContextCtor = options.audioContextCtor ?? getAudioContextCtor();
  const unavailableReason = microphoneUnavailableReason(mediaDevices);
  if (unavailableReason) {
    throw new MicrophonePermissionError(unavailableReason);
  }
  if (!mediaDevices?.getUserMedia || !AudioContextCtor) {
    throw new UnsupportedWavRecorderError();
  }

  let stream: MediaStream;
  try {
    stream = await getUserMedia(mediaDevices, voiceMediaConstraints());
  } catch {
    throw new MicrophonePermissionError("permission_denied");
  }

  let audioContext: AudioContext;
  try {
    audioContext = new AudioContextCtor();
  } catch {
    stopStream(stream);
    throw new UnsupportedWavRecorderError();
  }

  const chunks: Float32Array[] = [];
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const startedAt = Date.now();
  let stopped = false;
  let resolveFinished: (blob: Blob) => void = () => undefined;
  let rejectFinished: (error: Error) => void = () => undefined;

  const finished = new Promise<Blob>((resolve, reject) => {
    resolveFinished = resolve;
    rejectFinished = reject;
  });

  processor.onaudioprocess = (event) => {
    const input = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(input));
  };
  source.connect(processor);
  processor.connect(audioContext.destination);

  const finish = () => {
    clearTimeout(maxTimer);
    processor.disconnect();
    source.disconnect();
    stopStream(stream);
    void audioContext.close?.();
    try {
      assertRecordingDuration(Date.now() - startedAt);
      resolveFinished(encodeWavBlob(chunks, normalizedSampleRate(audioContext.sampleRate)));
    } catch (error) {
      rejectFinished(error as Error);
    }
  };

  const maxTimer = window.setTimeout(() => {
    if (!stopped) {
      stopped = true;
      finish();
    }
  }, MAX_RECORDING_MS);

  return {
    stop: () => {
      if (!stopped) {
        stopped = true;
        finish();
      }
      return finished;
    },
    cancel: () => {
      stopped = true;
      clearTimeout(maxTimer);
      processor.disconnect();
      source.disconnect();
      stopStream(stream);
      void audioContext.close?.();
    },
    finished
  };
}

async function createMediaRecorderSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  const mediaDevices = options.mediaDevices ?? getMediaDeviceSource();
  const MediaRecorderCtor = options.mediaRecorderCtor ?? window.MediaRecorder;
  const unavailableReason = microphoneUnavailableReason(mediaDevices);
  if (unavailableReason) {
    throw new MicrophonePermissionError(unavailableReason);
  }
  if (!mediaDevices?.getUserMedia || !MediaRecorderCtor) {
    throw new UnsupportedMediaRecorderError();
  }

  let stream: MediaStream;
  try {
    stream = await getUserMedia(mediaDevices, voiceMediaConstraints());
  } catch {
    throw new MicrophonePermissionError("permission_denied");
  }

  const chunks: Blob[] = [];
  const mimeType = selectMimeType(MediaRecorderCtor);
  const recorder = mimeType
    ? new MediaRecorderCtor(stream, { mimeType })
    : new MediaRecorderCtor(stream);
  const startedAt = Date.now();
  let stopped = false;
  let resolveFinished: (blob: Blob) => void = () => undefined;
  let rejectFinished: (error: Error) => void = () => undefined;

  const finished = new Promise<Blob>((resolve, reject) => {
    resolveFinished = resolve;
    rejectFinished = reject;
  });

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      chunks.push(event.data);
    }
  };
  recorder.onstop = () => {
    clearTimeout(maxTimer);
    stopStream(stream);
    try {
      assertRecordingDuration(Date.now() - startedAt);
      resolveFinished(new Blob(chunks, { type: mimeType || "audio/webm" }));
    } catch (error) {
      rejectFinished(error as Error);
    }
  };

  const maxTimer = window.setTimeout(() => {
    if (!stopped && recorder.state !== "inactive") {
      stopped = true;
      recorder.stop();
    }
  }, MAX_RECORDING_MS);

  recorder.start();

  return {
    stop: () => {
      if (!stopped && recorder.state !== "inactive") {
        stopped = true;
        recorder.stop();
      }
      return finished;
    },
    cancel: () => {
      stopped = true;
      clearTimeout(maxTimer);
      stopStream(stream);
    },
    finished
  };
}

function selectMimeType(MediaRecorderCtor: typeof MediaRecorder): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
    "audio/wav"
  ];
  return candidates.find((candidate) => MediaRecorderCtor.isTypeSupported(candidate)) ?? "";
}

function voiceMediaConstraints(): MediaStreamConstraints {
  return {
    audio: {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1
    }
  };
}

function getAudioContextCtor(): typeof AudioContext | undefined {
  return window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext })
    .webkitAudioContext;
}

function microphoneUnavailableReason(
  mediaDevices?: MediaDeviceSource
): "insecure_context" | "missing_api" | null {
  if (!isLocalhost() && window.isSecureContext === false) {
    return "insecure_context";
  }
  if (!mediaDevices?.getUserMedia) {
    return "missing_api";
  }
  return null;
}

function getMediaDeviceSource(): MediaDeviceSource | undefined {
  const modernMediaDevices = navigator.mediaDevices as Partial<MediaDeviceSource> | undefined;
  if (typeof modernMediaDevices?.getUserMedia === "function") {
    return modernMediaDevices as MediaDeviceSource;
  }

  const legacyNavigator = navigator as LegacyNavigatorMedia;
  const legacyGetUserMedia =
    legacyNavigator.getUserMedia ??
    legacyNavigator.webkitGetUserMedia ??
    legacyNavigator.mozGetUserMedia ??
    legacyNavigator.msGetUserMedia;
  if (!legacyGetUserMedia) return undefined;

  return {
    getUserMedia: (constraints: MediaStreamConstraints) =>
      new Promise<MediaStream>((resolve, reject) => {
        legacyGetUserMedia.call(legacyNavigator, constraints, resolve, reject);
      })
  };
}

function getUserMedia(
  mediaDevices: MediaDeviceSource,
  constraints: MediaStreamConstraints
): Promise<MediaStream> {
  return Promise.resolve(mediaDevices.getUserMedia(constraints));
}

function isLocalhost(): boolean {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function stopStream(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

function encodeWavBlob(chunks: Float32Array[], sourceSampleRate: number): Blob {
  const samples = resamplePcm(flattenChunks(chunks), sourceSampleRate, ASR_WAV_SAMPLE_RATE);
  const sampleRate = ASR_WAV_SAMPLE_RATE;
  const sampleCount = samples.length;
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, sampleCount * 2, true);

  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function normalizedSampleRate(sampleRate: number): number {
  return Number.isFinite(sampleRate) && sampleRate > 0 ? sampleRate : ASR_WAV_SAMPLE_RATE;
}

function flattenChunks(chunks: Float32Array[]): Float32Array {
  const sampleCount = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const samples = new Float32Array(sampleCount);
  let offset = 0;
  chunks.forEach((chunk) => {
    samples.set(chunk, offset);
    offset += chunk.length;
  });
  return samples;
}

function resamplePcm(
  samples: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number
): Float32Array {
  if (!samples.length || sourceSampleRate === targetSampleRate) {
    return samples;
  }
  const ratio = sourceSampleRate / targetSampleRate;
  const targetLength = Math.max(1, Math.round(samples.length / ratio));
  const output = new Float32Array(targetLength);
  for (let index = 0; index < targetLength; index += 1) {
    const sourceIndex = index * ratio;
    const leftIndex = Math.floor(sourceIndex);
    const rightIndex = Math.min(leftIndex + 1, samples.length - 1);
    const weight = sourceIndex - leftIndex;
    output[index] = samples[leftIndex] * (1 - weight) + samples[rightIndex] * weight;
  }
  return output;
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

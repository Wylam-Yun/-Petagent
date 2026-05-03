export const MIN_RECORDING_MS = 300;
export const MAX_RECORDING_MS = 15_000;

export class RecordingTooShortError extends Error {
  constructor() {
    super("recording_too_short");
    this.name = "RecordingTooShortError";
  }
}

export class MicrophonePermissionError extends Error {
  constructor() {
    super("microphone_unavailable");
    this.name = "MicrophonePermissionError";
  }
}

export type VoiceRecordingSession = {
  stop: () => Promise<Blob>;
  cancel: () => void;
  finished: Promise<Blob>;
};

type RecordingOptions = {
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  mediaRecorderCtor?: typeof MediaRecorder;
};

export function assertRecordingDuration(durationMs: number) {
  if (durationMs < MIN_RECORDING_MS) {
    throw new RecordingTooShortError();
  }
}

export async function createVoiceRecordingSession(
  options: RecordingOptions = {}
): Promise<VoiceRecordingSession> {
  const mediaDevices = options.mediaDevices ?? navigator.mediaDevices;
  const MediaRecorderCtor = options.mediaRecorderCtor ?? window.MediaRecorder;
  if (!mediaDevices?.getUserMedia || !MediaRecorderCtor) {
    throw new MicrophonePermissionError();
  }

  let stream: MediaStream;
  try {
    stream = await mediaDevices.getUserMedia({ audio: true });
  } catch {
    throw new MicrophonePermissionError();
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
  const candidates = ["audio/webm", "audio/mp4", "audio/wav"];
  return candidates.find((candidate) => MediaRecorderCtor.isTypeSupported(candidate)) ?? "";
}

function stopStream(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

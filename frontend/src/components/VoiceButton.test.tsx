import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { VoiceButton } from "./VoiceButton";
import type { VoiceChatResponse } from "../pet/types";

const voiceResponse: VoiceChatResponse = {
  reply: "辛苦啦。Momo 陪你缓一下。",
  mood: "concerned",
  face_type: "concerned",
  animation: "tilt",
  vibration: "light",
  voice_url: null,
  user_text: "我今天好累",
  audio_understanding: {
    user_text: "我今天好累",
    detected_emotion: "tired",
    tone_notes: "语气低",
    non_verbal: "叹气",
    confidence: 0.82
  },
  pet_state: {
    name: "Momo",
    mood: "concerned",
    energy: 72,
    intimacy: 41,
    hunger: 30,
    cleanliness: 85,
    loneliness: 31,
    sleepiness: 15
  },
  runtime: { event_id: "evt-voice", skills_used: [] }
};

function recorderFactory(blob = new Blob(["voice"], { type: "audio/webm" })) {
  return vi.fn().mockResolvedValue({
    stop: vi.fn().mockResolvedValue(blob),
    cancel: vi.fn(),
    finished: Promise.resolve(blob)
  });
}

describe("VoiceButton", () => {
  test("moves through listening thinking and speaking phases", async () => {
    const onPhaseChange = vi.fn();
    const onVoiceResponse = vi.fn();
    const uploadVoice = vi.fn().mockResolvedValue(voiceResponse);

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={recorderFactory()}
        thinkingMode={false}
        uploadVoice={uploadVoice}
        onError={vi.fn()}
        onPhaseChange={onPhaseChange}
        onVoiceResponse={onVoiceResponse}
      />
    );

    fireEvent.mouseDown(screen.getByRole("button", { name: "按住说话" }));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("listening"));

    fireEvent.mouseUp(screen.getByRole("button", { name: "松开回应" }));

    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("thinking"));
    await waitFor(() => expect(onPhaseChange).toHaveBeenCalledWith("speaking"));
    expect(uploadVoice).toHaveBeenCalledTimes(1);
    expect(uploadVoice).toHaveBeenCalledWith(expect.any(Blob), { thinkingMode: false });
    expect(onVoiceResponse).toHaveBeenCalledWith(voiceResponse);
  });

  test("does not start a second upload while busy", async () => {
    let resolveUpload: (value: VoiceChatResponse) => void = () => undefined;
    const uploadPromise = new Promise<VoiceChatResponse>((resolve) => {
      resolveUpload = resolve;
    });
    const uploadVoice = vi.fn().mockReturnValue(uploadPromise);
    const createRecorder = recorderFactory();

    render(
      <VoiceButton
        disabled={false}
        phase="idle"
        recorderFactory={createRecorder}
        thinkingMode={true}
        uploadVoice={uploadVoice}
        onError={vi.fn()}
        onPhaseChange={vi.fn()}
        onVoiceResponse={vi.fn()}
      />
    );

    fireEvent.mouseDown(screen.getByRole("button", { name: "按住说话" }));
    await waitFor(() => expect(createRecorder).toHaveBeenCalledTimes(1));
    fireEvent.mouseUp(screen.getByRole("button", { name: "松开回应" }));
    fireEvent.mouseDown(screen.getByRole("button", { name: "让我想想" }));

    expect(createRecorder).toHaveBeenCalledTimes(1);
    resolveUpload(voiceResponse);
  });
});

export type Mood =
  | "idle"
  | "happy"
  | "sad"
  | "sleepy"
  | "angry"
  | "shy"
  | "thinking"
  | "concerned"
  | "excited"
  | "lonely";

export type AnimationName =
  | "breathing"
  | "bounce"
  | "droop"
  | "slowBlink"
  | "shake"
  | "wiggle"
  | "blink"
  | "tilt"
  | "jump"
  | "small";

export type PetEventType =
  | "pet_head"
  | "poke_face"
  | "hug"
  | "debug_happy"
  | "debug_sleepy"
  | "debug_angry";

export type PetUIPhase = "idle" | "listening" | "thinking" | "speaking" | "error";

export type PetState = {
  schema_version?: string;
  name: string;
  mood: Mood;
  energy: number;
  intimacy: number;
  hunger: number;
  cleanliness: number;
  loneliness: number;
  sleepiness: number;
  mode?: string;
  last_interaction_at?: string;
  updated_at?: string;
};

export type PetResponse = {
  schema_version?: string;
  reply: string;
  mood: Mood;
  face_type: Mood;
  animation: AnimationName;
  vibration: "none" | "light" | "medium";
  voice_url: string | null;
  pet_state: PetState;
  runtime: {
    event_id: string;
    skills_used: unknown[];
  };
};

export type AudioUnderstanding = {
  user_text: string;
  detected_emotion:
    | "calm"
    | "tired"
    | "happy"
    | "sad"
    | "angry"
    | "anxious"
    | "uncertain";
  tone_notes: string;
  non_verbal: string;
  confidence: number;
};

export type VoiceChatResponse = PetResponse & {
  user_text: string;
  audio_understanding: AudioUnderstanding;
};

export type ActivationResponse = PetResponse & {
  active: boolean;
  session_id: string | null;
};

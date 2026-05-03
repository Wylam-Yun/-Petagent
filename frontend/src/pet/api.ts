import type { PetEventType, PetResponse, PetState } from "./types";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getPetState(): Promise<PetState> {
  return requestJson<PetState>("/api/pet/state");
}

export function postPetEvent(event: PetEventType): Promise<PetResponse> {
  return requestJson<PetResponse>("/api/pet/event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      event,
      payload: { description: eventDescription(event) }
    })
  });
}

function eventDescription(event: PetEventType): string {
  switch (event) {
    case "pet_head":
      return "用户摸了你的头";
    case "poke_face":
      return "用户轻轻戳了你的脸";
    case "hug":
      return "用户抱了抱你";
    case "debug_happy":
      return "调试：开心";
    case "debug_sleepy":
      return "调试：困了";
    case "debug_angry":
      return "调试：小生气";
    default:
      return "用户和你互动";
  }
}

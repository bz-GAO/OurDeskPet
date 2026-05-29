export const petStates = ["idle", "follow", "talk", "sleep"] as const;

export type PetState = (typeof petStates)[number];

export type PetTone = "neutral" | "active" | "talk" | "muted";

export type PetTransitionReason =
  | "boot"
  | "hover"
  | "leave"
  | "click"
  | "double-click"
  | "context-menu"
  | "external";

export interface PetStateView {
  message: string;
  image: string;
  imageAlt: string;
  tone: PetTone;
}

export interface PetProfile {
  id: string;
  displayName: string;
  initialState: PetState;
  states: Record<PetState, PetStateView>;
}

export interface PetTransition {
  from: PetState;
  to: PetState;
  reason: PetTransitionReason;
  at: number;
}

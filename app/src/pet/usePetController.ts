import { useCallback, useMemo, useRef, useState } from "react";
import { defaultPetProfile } from "./profiles/defaultPetProfile";
import type {
  PetProfile,
  PetState,
  PetTransition,
  PetTransitionReason,
} from "./types";

export function usePetController(profile: PetProfile = defaultPetProfile) {
  const [state, setState] = useState<PetState>(profile.initialState);
  const transitionHistory = useRef<PetTransition[]>([]);

  const transitionTo = useCallback(
    (nextState: PetState, reason: PetTransitionReason = "external") => {
      setState((currentState) => {
        if (currentState === nextState) {
          return currentState;
        }

        const transition: PetTransition = {
          from: currentState,
          to: nextState,
          reason,
          at: Date.now(),
        };

        transitionHistory.current = [...transitionHistory.current.slice(-19), transition];
        console.info(
          `[pet-state] ${transition.from} -> ${transition.to} (${transition.reason})`,
        );

        return nextState;
      });
    },
    [],
  );

  const controller = useMemo(
    () => ({
      profile,
      state,
      view: profile.states[state],
      transitions: transitionHistory.current,
      transitionTo,
      idle: (reason: PetTransitionReason = "external") => transitionTo("idle", reason),
      follow: (reason: PetTransitionReason = "external") => transitionTo("follow", reason),
      talk: (reason: PetTransitionReason = "external") => transitionTo("talk", reason),
      sleep: (reason: PetTransitionReason = "external") => transitionTo("sleep", reason),
      wake: (reason: PetTransitionReason = "external") => transitionTo("idle", reason),
      toggleSleep: (reason: PetTransitionReason = "external") =>
        transitionTo(state === "sleep" ? "idle" : "sleep", reason),
    }),
    [profile, state, transitionTo],
  );

  return controller;
}

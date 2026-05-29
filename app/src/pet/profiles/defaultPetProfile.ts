import type { PetProfile } from "../types";

const rinaPlaceholderImage = "/assets/rina/Rina_bot_cutout.png";

export const defaultPetProfile: PetProfile = {
  id: "default-rina-placeholder",
  displayName: "RinaDesk Agent",
  initialState: "idle",
  states: {
    idle: {
      message: "RinaDesk Agent",
      image: rinaPlaceholderImage,
      imageAlt: "RinaDesk Agent placeholder character",
      tone: "neutral",
    },
    follow: {
      message: "I am here.",
      image: rinaPlaceholderImage,
      imageAlt: "RinaDesk Agent following the pointer",
      tone: "active",
    },
    talk: {
      message: "Ready to talk.",
      image: rinaPlaceholderImage,
      imageAlt: "RinaDesk Agent ready to talk",
      tone: "talk",
    },
    sleep: {
      message: "Zzz...",
      image: rinaPlaceholderImage,
      imageAlt: "RinaDesk Agent sleeping",
      tone: "muted",
    },
  },
};

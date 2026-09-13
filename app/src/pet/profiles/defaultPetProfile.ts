import type { PetProfile } from "../types";

const rinaIdleImage = "/assets/rina/rina-idle-v1.png";

export const defaultPetProfile: PetProfile = {
  id: "rina-astromeda-v1",
  displayName: "RinaDesk Agent",
  initialState: "idle",
  states: {
    idle: {
      message: "RinaDesk Agent",
      image: rinaIdleImage,
      imageAlt: "Rina wearing headphones and a hoodie",
      tone: "neutral",
    },
    follow: {
      message: "I am here.",
      image: rinaIdleImage,
      imageAlt: "RinaDesk Agent following the pointer",
      tone: "active",
    },
    talk: {
      message: "Ready to talk.",
      image: rinaIdleImage,
      imageAlt: "RinaDesk Agent ready to talk",
      tone: "talk",
    },
    sleep: {
      message: "Zzz...",
      image: rinaIdleImage,
      imageAlt: "RinaDesk Agent sleeping",
      tone: "muted",
    },
  },
};

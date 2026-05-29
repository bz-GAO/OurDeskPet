import type { PetProfile } from "../types";

const rinaPlaceholderImage = "/assets/rina/Rina_bot_cutout.png";

export const defaultPetProfile: PetProfile = {
  id: "default-rina-placeholder",
  displayName: "OurDeskPet",
  initialState: "idle",
  states: {
    idle: {
      message: "OurDeskPet",
      image: rinaPlaceholderImage,
      imageAlt: "OurDeskPet placeholder character",
      tone: "neutral",
    },
    follow: {
      message: "I am here.",
      image: rinaPlaceholderImage,
      imageAlt: "OurDeskPet following the pointer",
      tone: "active",
    },
    talk: {
      message: "Ready to talk.",
      image: rinaPlaceholderImage,
      imageAlt: "OurDeskPet ready to talk",
      tone: "talk",
    },
    sleep: {
      message: "Zzz...",
      image: rinaPlaceholderImage,
      imageAlt: "OurDeskPet sleeping",
      tone: "muted",
    },
  },
};

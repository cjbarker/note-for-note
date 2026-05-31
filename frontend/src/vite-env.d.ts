/// <reference types="vite/client" />

// Safari/older WebKit expose the constructor under a prefixed name.
interface Window {
  webkitAudioContext?: typeof AudioContext;
}

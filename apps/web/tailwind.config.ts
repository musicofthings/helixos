import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201b",
        graphite: "#2c332f",
        fern: "#236047",
        signal: "#1d7a8c",
        reagent: "#a54242",
        amber: "#b7791f"
      }
    }
  },
  plugins: []
};

export default config;

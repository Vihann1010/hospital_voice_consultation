import type { Config } from "tailwindcss";

/**
 * Satya Hospital design tokens.
 * Palette drawn from the hospital's world: deep pine (scrub green, calm and
 * clinical), chalk mint surfaces, marigold accent (Indian hospital warmth),
 * clay for alerts. Display face: Bricolage Grotesque; body: Inter.
 *
 * The shadcn-compatible semantic tokens below map onto the same palette, so
 * the patient app and the clinical dashboard share one visual language.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand palette taken from the Satya Trauma & Maternity Center logo:
        // #0B55A1 (blue) and #B7DC0D (lime). Token NAMES are unchanged so the
        // whole application re-skins without touching any component.
        //   pine     -> logo blue      (primary surfaces, headers, sidebar)
        //   marigold -> logo lime      (accent, AI markers, calls to action)
        // marigold.deep is a darkened lime that meets AA contrast on white,
        // since the bright lime is only legible as a background.
        pine: { DEFAULT: "#0B55A1", deep: "#073E75", soft: "#1668BF" },
        mint: { DEFAULT: "#EEF3F9", card: "#F7FAFD" },
        marigold: { DEFAULT: "#B7DC0D", deep: "#6E8A05" },
        clay: { DEFAULT: "#C4553B", soft: "#F3E2DD" },
        ink: { DEFAULT: "#101C2B", muted: "#4A5A6E", faint: "#8496A8" },
        // Semantic (shadcn) tokens
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(14,59,52,0.04), 0 8px 24px -12px rgba(14,59,52,0.16)",
        lift: "0 2px 4px rgba(14,59,52,0.05), 0 16px 40px -16px rgba(14,59,52,0.24)",
      },
      keyframes: {
        breathe: {
          "0%, 100%": { transform: "scale(1)", opacity: "0.85" },
          "50%": { transform: "scale(1.12)", opacity: "1" },
        },
        pulseRing: {
          "0%": { transform: "scale(1)", opacity: "0.5" },
          "100%": { transform: "scale(1.9)", opacity: "0" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        breathe: "breathe 2.6s ease-in-out infinite",
        pulseRing: "pulseRing 1.8s ease-out infinite",
        shimmer: "shimmer 1.8s infinite",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;

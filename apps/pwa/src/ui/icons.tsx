// Inline stroke icons (no icon font, no network).
const base = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const MicIcon = ({ size = 26 }: { size?: number }) => (
  <svg {...base} width={size} height={size}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
export const MoreIcon = () => (
  <svg {...base}>
    <circle cx="5" cy="12" r="1.3" fill="currentColor" />
    <circle cx="12" cy="12" r="1.3" fill="currentColor" />
    <circle cx="19" cy="12" r="1.3" fill="currentColor" />
  </svg>
);
export const CloseIcon = () => (
  <svg {...base}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
export const ChevronIcon = () => (
  <svg {...base} width={20} height={20} style={{ color: "var(--muted)", flex: "none" }}>
    <path d="M9 6l6 6-6 6" />
  </svg>
);
export const TrophyIcon = ({ size = 36 }: { size?: number }) => (
  <svg {...base} width={size} height={size} style={{ color: "var(--accent)" }}>
    <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4zM7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4" />
  </svg>
);
export const DroidIcon = () => (
  <svg {...base} style={{ color: "var(--accent)", flex: "none" }}>
    <rect x="5" y="8" width="14" height="11" rx="3" />
    <path d="M12 8V4M9 13h.01M15 13h.01M3 13v2M21 13v2" />
  </svg>
);
export const SpeakerIcon = () => (
  <svg {...base} width={18} height={18} style={{ flex: "none" }}>
    <path d="M11 5L6 9H3v6h3l5 4V5zM16 9a4 4 0 0 1 0 6" />
  </svg>
);

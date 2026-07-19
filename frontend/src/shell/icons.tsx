/**
 * Inline SVG icons. The spec's #ui-system rule for the sidebar is "All icons are
 * inline SVG — no icon font, no emoji" (16×16 viewBox, ~1.6 stroke, round caps),
 * so the shell ships its own small set rather than a runtime icon dependency.
 */

import type { ReactNode } from 'react';

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const SearchIcon = () => (
  <Svg>
    <circle cx="7" cy="7" r="4.5" />
    <line x1="10.5" y1="10.5" x2="14" y2="14" />
  </Svg>
);

export const PanelLeftIcon = () => (
  <Svg>
    <rect x="1.5" y="1.5" width="13" height="13" rx="2.5" />
    <line x1="5.5" y1="1.5" x2="5.5" y2="14.5" />
  </Svg>
);

export const MenuIcon = () => (
  <Svg>
    <line x1="2" y1="4.5" x2="14" y2="4.5" />
    <line x1="2" y1="8" x2="14" y2="8" />
    <line x1="2" y1="11.5" x2="14" y2="11.5" />
  </Svg>
);

export const ChevronIcon = () => (
  <Svg>
    <polyline points="6,4 10,8 6,12" />
  </Svg>
);

export const CheckIcon = () => (
  <Svg>
    <polyline points="3,8.5 6.5,12 13,4.5" />
  </Svg>
);

export const SunIcon = () => (
  <Svg>
    <circle cx="8" cy="8" r="3.2" />
    <line x1="8" y1="1" x2="8" y2="2.4" />
    <line x1="8" y1="13.6" x2="8" y2="15" />
    <line x1="1" y1="8" x2="2.4" y2="8" />
    <line x1="13.6" y1="8" x2="15" y2="8" />
    <line x1="3" y1="3" x2="4" y2="4" />
    <line x1="12" y1="12" x2="13" y2="13" />
    <line x1="13" y1="3" x2="12" y2="4" />
    <line x1="4" y1="12" x2="3" y2="13" />
  </Svg>
);

export const MoonIcon = () => (
  <Svg>
    <path d="M13 9.5A5.5 5.5 0 1 1 6.5 3 4.4 4.4 0 0 0 13 9.5Z" />
  </Svg>
);

export const SignOutIcon = () => (
  <Svg>
    <path d="M6 2.5H3.5A1.5 1.5 0 0 0 2 4v8a1.5 1.5 0 0 0 1.5 1.5H6" />
    <polyline points="10,5 13,8 10,11" />
    <line x1="13" y1="8" x2="6.5" y2="8" />
  </Svg>
);

export const BuildingIcon = () => (
  <Svg>
    <rect x="3.5" y="2" width="9" height="12" rx="1" />
    <line x1="6.5" y1="14" x2="9.5" y2="14" />
    <line x1="6" y1="5" x2="6.6" y2="5" />
    <line x1="9.4" y1="5" x2="10" y2="5" />
    <line x1="6" y1="8" x2="6.6" y2="8" />
    <line x1="9.4" y1="8" x2="10" y2="8" />
  </Svg>
);

export const DashboardIcon = () => (
  <Svg>
    <rect x="2" y="2" width="5" height="5" rx="1" />
    <rect x="9" y="2" width="5" height="5" rx="1" />
    <rect x="2" y="9" width="5" height="5" rx="1" />
    <rect x="9" y="9" width="5" height="5" rx="1" />
  </Svg>
);

export const PartsIcon = () => (
  <Svg>
    <path d="M8 1.5l5.5 3.2v6.6L8 14.5 2.5 11.3V4.7z" />
    <path d="M2.5 4.7L8 8l5.5-3.3M8 8v6.5" />
  </Svg>
);

export const QuotesIcon = () => (
  <Svg>
    <rect x="3" y="1.5" width="10" height="13" rx="1.5" />
    <line x1="5.5" y1="5" x2="10.5" y2="5" />
    <line x1="5.5" y1="8" x2="10.5" y2="8" />
    <line x1="5.5" y1="11" x2="8.5" y2="11" />
  </Svg>
);

export const OrdersIcon = () => (
  <Svg>
    <path d="M2.5 4.5h11l-1 9h-9z" />
    <path d="M5.5 4.5V3.2a2.5 2.5 0 0 1 5 0v1.3" />
  </Svg>
);

export const ContactsIcon = () => (
  <Svg>
    <circle cx="8" cy="5.3" r="2.5" />
    <path d="M3 13.5a5 5 0 0 1 10 0" />
  </Svg>
);

export const SuppliersIcon = () => (
  <Svg>
    <path d="M1.5 6.5 3 2.5h10l1.5 4" />
    <path d="M1.5 6.5h13v7h-13z" />
    <path d="M6 6.5v2.5h4V6.5" />
  </Svg>
);

export const ConfigureIcon = () => (
  <Svg>
    <circle cx="8" cy="8" r="2.2" />
    <path d="M8 1.5v2M8 12.5v2M14.5 8h-2M3.5 8h-2M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4M12.6 12.6l-1.4-1.4M4.8 4.8 3.4 3.4" />
  </Svg>
);

export const AnalyticsIcon = () => (
  <Svg>
    <line x1="2.5" y1="13.5" x2="13.5" y2="13.5" />
    <rect x="3.5" y="8" width="2.2" height="4" />
    <rect x="7" y="5" width="2.2" height="7" />
    <rect x="10.5" y="9.5" width="2.2" height="2.5" />
  </Svg>
);

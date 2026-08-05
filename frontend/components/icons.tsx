type IconName =
  | "activity"
  | "arrow-right"
  | "beaker"
  | "check"
  | "chevron-down"
  | "clock"
  | "filter"
  | "flask"
  | "grid"
  | "refresh"
  | "search"
  | "shield"
  | "triangle"
  | "x";

const paths: Record<IconName, React.ReactNode> = {
  activity: (
    <path d="M3 12h3l2-7 4 14 2-7h7" />
  ),
  "arrow-right": <path d="M5 12h14m-6-6 6 6-6 6" />,
  beaker: (
    <path d="M9 3h6m-5 0v5l-5.2 8.5A2 2 0 0 0 6.5 20h11a2 2 0 0 0 1.7-3.5L14 8V3M7.8 15h8.4" />
  ),
  check: <path d="m5 12 4 4L19 6" />,
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3 2" /></>,
  filter: <path d="M4 5h16l-6 7v5l-4 2v-7L4 5Z" />,
  flask: <><path d="M9 3h6M10 3v5l-4.5 8A2 2 0 0 0 7.2 19h9.6a2 2 0 0 0 1.7-3L14 8V3" /><path d="M8 14h8" /></>,
  grid: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
  refresh: <path d="M20 6v5h-5M4 18v-5h5m10.2-2A7.5 7.5 0 0 0 6.4 7.4L4 11m16 2-2.4 3.6A7.5 7.5 0 0 1 4.8 13" />,
  search: <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 4 4" /></>,
  shield: <path d="M12 3 19 6v5c0 4.4-2.8 8-7 10-4.2-2-7-5.6-7-10V6l7-3Z" />,
  triangle: <path d="m12 4 9 16H3L12 4Z" />,
  x: <path d="m6 6 12 12M18 6 6 18" />,
};

export function Icon({ name, size = 18, strokeWidth = 1.8 }: { name: IconName; size?: number; strokeWidth?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
    >
      {paths[name]}
    </svg>
  );
}


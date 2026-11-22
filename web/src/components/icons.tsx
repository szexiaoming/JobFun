import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function GridIcon(props: IconProps) {
  return <Icon {...props}><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></Icon>;
}

export function FileIcon(props: IconProps) {
  return <Icon {...props}><path d="M6 2.8h8l4 4V21H6z" /><path d="M14 2.8V7h4" /><path d="M9 12h6M9 16h6" /></Icon>;
}

export function BriefcaseIcon(props: IconProps) {
  return <Icon {...props}><rect x="3" y="7" width="18" height="13" rx="3" /><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></Icon>;
}

export function MessageIcon(props: IconProps) {
  return <Icon {...props}><path d="M20 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4z" /><path d="M8 9h8M8 13h5" /></Icon>;
}

export function ShieldIcon(props: IconProps) {
  return <Icon {...props}><path d="M12 3 20 6v5c0 5-3.3 8.4-8 10-4.7-1.6-8-5-8-10V6z" /><path d="m9 12 2 2 4-5" /></Icon>;
}

export function LogoutIcon(props: IconProps) {
  return <Icon {...props}><path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" /></Icon>;
}

export function SparkIcon(props: IconProps) {
  return <Icon {...props}><path d="m12 3 1.3 3.7L17 8l-3.7 1.3L12 13l-1.3-3.7L7 8l3.7-1.3zM18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8zM6 14l.6 1.4L8 16l-1.4.6L6 18l-.6-1.4L4 16l1.4-.6z" /></Icon>;
}

export function AudioIcon(props: IconProps) {
  return <Icon {...props}><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" /></Icon>;
}

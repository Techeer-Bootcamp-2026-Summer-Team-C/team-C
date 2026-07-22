export function ServiceMark() {
  return (
    <span className="service-mark" aria-hidden="true">
      <svg viewBox="0 0 48 36">
        <path className="service-mark-ring" d="M 34 7 A 13 13 0 1 1 18 6" />
        <path className="service-mark-aperture" d="M 18 6 L 24 12" />
        <circle className="service-mark-focus" cx="24" cy="18" r="3" />
      </svg>
    </span>
  );
}

import { Loader } from "./Loader";

/** Quiet fallback shown while a lazy route module is fetched. */
export function RouteFallback() {
  return (
    <div className="route-fallback" aria-busy="true">
      <Loader size={42} label="Opening the archive" />
      <p className="eyebrow">Opening the archive</p>
    </div>
  );
}

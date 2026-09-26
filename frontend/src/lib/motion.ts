import { useEffect, useState } from "react";
export function useMotionPreference() {
  const [system, setSystem] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystem(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const [local, setLocal] = useState(
    () => localStorage.getItem("testq-reduce-motion") === "true",
  );
  useEffect(() => {
    const update = () =>
      setLocal(localStorage.getItem("testq-reduce-motion") === "true");
    window.addEventListener("testq-motion-change", update);
    return () => window.removeEventListener("testq-motion-change", update);
  }, []);
  return system || local;
}

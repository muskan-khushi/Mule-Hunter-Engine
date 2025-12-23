import { useEffect, useState } from "react";

export default function useExplanations() {
  const [explanations, setExplanations] = useState({});

  useEffect(() => {
    const controller = new AbortController();

    async function loadExplanations() {
      try {
        const res = await fetch(
          `${import.meta.env.VITE_BACKEND_URL}/api/node/{id}`,
          { signal: controller.signal }
        );

        if (!res.ok) {
          throw new Error(`Backend returned ${res.status}`);
        }

        const contentType = res.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
          throw new TypeError("Backend did not return JSON");
        }

        const data = await res.json();

        const map = {};
        data?.forEach((item) => {
          map[item.node_id] = {
            reasons: item.reasons,
          };
        });

        setExplanations(map);
      } catch (err) {
        if (err.name !== "AbortError") {
          console.error("Failed to load explanations:", err.message);
        }
      }
    }

    loadExplanations();
    return () => controller.abort();
  }, []);

  return explanations;
}

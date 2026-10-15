"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";

type State = "checking" | "ok" | "unavailable";

const LABELS: Record<State, string> = {
  checking: "Vérification de l'API…",
  ok: "API et base de données disponibles",
  unavailable: "API ou base de données indisponible",
};

export function HealthStatus() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    let cancelled = false;
    api
      .GET("/health")
      .then(({ data }) => {
        if (!cancelled) setState(data?.status === "ok" ? "ok" : "unavailable");
      })
      .catch(() => {
        if (!cancelled) setState("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <p role="status" data-state={state}>
      {LABELS[state]}
    </p>
  );
}

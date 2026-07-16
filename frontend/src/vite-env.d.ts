/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_INCIDENT_GRAPH_ENABLED?: string;
  readonly VITE_TOPOLOGY_GRAPH_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

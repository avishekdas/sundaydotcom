export type Values = Record<string, unknown>;

export interface ServerItem {
  id: string;
  name: string;
  group_id: string;
  version: number;
  values: Values;
  computed?: Values;
}

/** A change pushed over the WebSocket (or the PATCH response): only the changed columns; null = cleared. */
export interface ItemEvent {
  item_id: string;
  version: number;
  values: Record<string, unknown | null>;
  mutation_id?: string | null;
}

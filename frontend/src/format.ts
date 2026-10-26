import dayjs from "dayjs";

export const money = (v?: number | null) =>
  v === null || v === undefined ? "—" : v.toLocaleString("ru-RU", { maximumFractionDigits: 0 });

export const num = (v?: number | null, digits = 2) =>
  v === null || v === undefined ? "—" : v.toLocaleString("ru-RU", { maximumFractionDigits: digits });

export const pct = (v?: number | null, digits = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toLocaleString("ru-RU", { maximumFractionDigits: digits })} %`;

export const d = (v?: string | null) => (v ? dayjs(v).format("DD.MM.YYYY") : "—");

export const dt = (v?: string | null) => (v ? dayjs(v).format("DD.MM.YYYY HH:mm") : "—");

export const iso = (v: dayjs.Dayjs | null | undefined) => (v ? v.format("YYYY-MM-DD") : undefined);

export const STATUS_COLORS: Record<string, string> = {
  draft: "default",
  registered: "blue",
  collecting: "processing",
  docs_required: "orange",
  scoring: "processing",
  review: "geekblue",
  committee: "purple",
  approved: "green",
  rejected: "red",
  issued: "cyan",
  client_refused: "default",
};

export const CLASS_COLORS: Record<string, string> = { A: "green", B: "lime", C: "gold", D: "orange", E: "red" };

export const REC_COLORS: Record<string, string> = { approve: "green", approve_changed: "gold", reject: "red" };

export const MODEL_COLORS: Record<string, string> = {
  candidate: "default",
  approval: "orange",
  approved: "blue",
  published: "green",
  archived: "default",
  rejected: "red",
};

export const OUTCOMES: Record<string, string> = {
  approve: "Одобрить",
  approve_changed: "Одобрить на изменённых условиях",
  reject: "Отказать",
  committee: "Передана на кредитный комитет",
  docs: "Запрошены документы",
};

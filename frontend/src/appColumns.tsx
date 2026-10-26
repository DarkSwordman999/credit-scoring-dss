import { Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { CLASS_COLORS, d, money, OUTCOME_COLORS, OUTCOMES, pct, REC_COLORS, STATUS_COLORS } from "./format";

export interface AppRow {
  id: number;
  number: string;
  created_at: string;
  status: string;
  status_name: string;
  client_id: number;
  client: string;
  product: string;
  amount: number;
  term_months: number;
  channel: string;
  risk_class: string | null;
  pd: number | null;
  score: number | null;
  pdn: number | null;
  recommendation: string | null;
  officer: string;
  decided_at: string | null;
  decision: string | null;
  decided_by: string;
  decision_stage: string | null;
  reason: string;
  loan_status: string | null;
}

const sub = (text: React.ReactNode) => (
  <div>
    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
      {text}
    </Typography.Text>
  </div>
);

/** Колонки таблицы заявок: номер, клиент, параметры, оценка, рекомендация и решение, причина, состояние. */
export function appColumns(recNames: Record<string, string> = {}, withClient = true): ColumnsType<AppRow> {
  const cols: ColumnsType<AppRow> = [
    {
      title: "Заявка",
      dataIndex: "number",
      className: "nw",
      width: 140,
      render: (v, r) => (
        <>
          <Link to={`/applications/${r.id}`}>{v}</Link>
          {sub(d(r.created_at))}
        </>
      ),
    },
  ];
  if (withClient)
    cols.push({
      title: "Клиент",
      dataIndex: "client",
      width: 190,
      render: (v, r) => <Link to={`/clients/${r.client_id}`}>{v}</Link>,
    });
  cols.push(
    {
      title: "Продукт и сумма",
      dataIndex: "amount",
      width: 165,
      render: (v, r) => (
        <>
          <span className="nw">
            {money(v)} руб. · {r.term_months} мес.
          </span>
          {sub(r.product)}
        </>
      ),
    },
    {
      title: "Оценка",
      dataIndex: "risk_class",
      className: "nw",
      width: 120,
      render: (v, r) => (
        <>
          {v ? (
            <Tooltip title={r.score !== null ? `Балл скоринговой карты: ${r.score}` : undefined}>
              <Tag color={CLASS_COLORS[v]}>{v}</Tag>
              PD {pct(r.pd, 1)}
            </Tooltip>
          ) : r.recommendation === "reject" ? (
            <Tag color="red">стоп-фактор</Tag>
          ) : (
            "—"
          )}
          {r.pdn !== null && sub(`ПДН ${pct(r.pdn, 0)}`)}
        </>
      ),
    },
    {
      title: "Рекомендация → решение",
      dataIndex: "decision",
      width: 195,
      render: (v, r) => (
        <>
          {r.recommendation ? (
            <Tooltip title="Рекомендация системы">
              <Tag color={REC_COLORS[r.recommendation]}>{recNames[r.recommendation] || r.recommendation}</Tag>
            </Tooltip>
          ) : (
            "—"
          )}
          {v && (
            <div style={{ marginTop: 4 }}>
              <Tag color={OUTCOME_COLORS[v]} bordered={false}>
                → {OUTCOMES[v] || v}
              </Tag>
              {sub(`${r.decision_stage === "committee" ? "Кредитный комитет · " : ""}${r.decided_by}`)}
            </div>
          )}
        </>
      ),
    },
    {
      title: "Причина",
      dataIndex: "reason",
      render: (v) =>
        v ? (
          <Typography.Paragraph ellipsis={{ rows: 3, tooltip: v }} style={{ margin: 0, fontSize: 13, minWidth: 200 }}>
            {v}
          </Typography.Paragraph>
        ) : (
          "—"
        ),
    },
    {
      title: "Состояние",
      dataIndex: "status",
      width: 135,
      render: (v, r) => <Tag color={STATUS_COLORS[v]}>{r.status_name}</Tag>,
    },
  );
  return cols;
}

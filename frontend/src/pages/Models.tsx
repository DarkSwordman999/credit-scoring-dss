import { Alert, Button, Card, Table, Tabs, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { d, dt, MODEL_COLORS, num, pct } from "../format";
import { useAction, useLoad } from "../hooks";

interface Model {
  id: number;
  version: number;
  name: string;
  status: string;
  status_name: string;
  metrics: any;
  created_at: string;
  created_by: string;
  approved_by: string | null;
  published_at: string | null;
  characteristics: number;
}

interface Mon {
  period: string;
  version: number;
  n_scored: number;
  psi: number | null;
  n_matured: number;
  gini: number | null;
  gini_ref: number | null;
  default_rate: number | null;
  alerts: string[];
}

/** Методика оценки: версии и мониторинг (ПР 7-8, «Обучить и опубликовать модель», «Мониторить качество модели»). */
export default function Models() {
  const { can } = useAuth();
  const { busy, run } = useAction();
  const models = useLoad(() => api.get<Model[]>("/api/models"));
  const mon = useLoad(() => api.get<Mon[]>("/api/models/monitoring"));
  const published = models.data?.find((m) => m.status === "published");
  const chart = [...(mon.data || [])].reverse();

  return (
    <>
      <Typography.Title level={3} className="page-title">
        Методика оценки кредитоспособности
      </Typography.Title>
      {published && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }}
               message={`Действует версия ${published.version}: ${published.name}`}
               description={`Опубликована ${d(published.published_at)}. На созревших кредитах: ROC AUC ${num(published.metrics.auc, 3)}, Gini ${num(published.metrics.gini, 3)}, KS ${num(published.metrics.ks, 3)} (выборка ${published.metrics.n ?? "—"}, дефолтов ${published.metrics.bad ?? "—"}). Требование ТЗ: ROC AUC не ниже 0,75.`} />
      )}
      <Card>
        <Tabs
          items={[
            {
              key: "v",
              label: "Версии",
              children: (
                <Table<Model> rowKey="id" size="middle" loading={models.loading} dataSource={models.data || []} pagination={false}
                  columns={[
                    { title: "Версия", dataIndex: "version", render: (v, r) => <Link to={`/models/${r.id}`}>v{v}</Link> },
                    { title: "Название", dataIndex: "name" },
                    { title: "Состояние", dataIndex: "status", render: (v, r) => <Tag color={MODEL_COLORS[v]}>{r.status_name}</Tag> },
                    { title: "ROC AUC", align: "right", render: (_, r) => num(r.metrics.auc, 3) },
                    { title: "Gini", align: "right", render: (_, r) => num(r.metrics.gini, 3) },
                    { title: "KS", align: "right", render: (_, r) => num(r.metrics.ks, 3) },
                    { title: "Выборка", align: "right", render: (_, r) => r.metrics.n ?? "—" },
                    { title: "Создана", render: (_, r) => `${dt(r.created_at)}, ${r.created_by}` },
                  ]} />
              ),
            },
            {
              key: "m",
              label: "Мониторинг (С-15)",
              children: (
                <>
                  <div className="toolbar">
                    <Typography.Text type="secondary">
                      PSI — сдвиг потока заявок относительно выборки, на которой проверялась версия (порог 0,25). Gini — качество на кредитах,
                      созревших к концу месяца.
                    </Typography.Text>
                    <span className="spacer" />
                    {can("risk_analyst") && (
                      <Button icon={<ReloadOutlined />} loading={busy}
                              onClick={async () => {
                                if (await run(() => api.post("/api/models/monitoring", {}), "Мониторинг за прошлый месяц рассчитан")) mon.reload();
                              }}>
                        Рассчитать за прошлый месяц
                      </Button>
                    )}
                  </div>
                  {chart.length > 0 && (
                    <div style={{ height: 280, marginBottom: 16 }}>
                      <ResponsiveContainer>
                        <LineChart data={chart} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="period" />
                          <YAxis domain={[0, "auto"]} />
                          <Tooltip formatter={(v: any) => num(v, 3)} />
                          <Legend />
                          <ReferenceLine y={0.25} stroke="#cf1322" strokeDasharray="4 4" label="порог PSI" />
                          <Line type="monotone" dataKey="psi" name="PSI" stroke="#1f4e8c" strokeWidth={2} />
                          <Line type="monotone" dataKey="gini" name="Gini" stroke="#389e0d" strokeWidth={2} />
                          <Line type="monotone" dataKey="gini_ref" name="Gini при проверке" stroke="#999" strokeDasharray="5 5" dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                  <Table<Mon> rowKey={(r) => `${r.period}-${r.version}`} size="small" loading={mon.loading} dataSource={mon.data || []}
                    pagination={{ pageSize: 12 }} rowClassName={(r) => (r.alerts.length ? "row-alert" : "")}
                    columns={[
                      { title: "Месяц", dataIndex: "period" },
                      { title: "Версия", dataIndex: "version", render: (v) => `v${v}` },
                      { title: "Оценено заявок", dataIndex: "n_scored", align: "right" },
                      { title: "PSI", dataIndex: "psi", align: "right", render: (v) => num(v, 3) },
                      { title: "Созревших кредитов", dataIndex: "n_matured", align: "right" },
                      { title: "Gini", dataIndex: "gini", align: "right", render: (v) => num(v, 3) },
                      { title: "Доля 90+", dataIndex: "default_rate", align: "right", render: (v) => pct(v) },
                      { title: "Оповещения", dataIndex: "alerts", render: (v: string[]) => (v.length ? v.join("; ") : "нет") },
                    ]} />
                </>
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}

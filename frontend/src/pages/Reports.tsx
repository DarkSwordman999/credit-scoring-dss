import { useState } from "react";
import { Button, Card, Col, DatePicker, Empty, Row, Select, Space, Statistic, Table, Typography } from "antd";
import { FileExcelOutlined, FilePdfOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { api, download } from "../api";
import { dt, iso, num } from "../format";
import { useAction } from "../hooks";

const KINDS = [
  { value: "applications", label: "Отчёт по заявкам" },
  { value: "decisions", label: "Решения и уровень одобрения" },
  { value: "portfolio", label: "Качество кредитного портфеля" },
  { value: "model", label: "Качество и стабильность методики оценки" },
];

interface Report {
  title: string;
  meta: [string, string][];
  summary: [string, any][];
  tables: { title: string; headers: string[]; rows: any[][] }[];
}

const cell = (v: any) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return num(v, 2);
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return dt(v);
  return String(v);
};

/** Отчёты за произвольный период (П-11, С-16; ПР 7-8, вариант «Сформировать отчёт»). */
export default function Reports() {
  const [kind, setKind] = useState("decisions");
  const [period, setPeriod] = useState<[Dayjs, Dayjs]>([dayjs().subtract(3, "month").startOf("month"), dayjs()]);
  const [rep, setRep] = useState<Report | null>(null);
  const { busy, run } = useAction();
  const params = { date_from: iso(period[0]), date_to: iso(period[1]) };

  const build = async () => {
    const r = await run(() => api.get<Report>(`/api/reports/${kind}`, params));
    if (r) setRep(r);
  };

  return (
    <>
      <Typography.Title level={3} className="page-title">Отчёты</Typography.Title>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select value={kind} options={KINDS} style={{ width: 340 }} onChange={(v) => { setKind(v); setRep(null); }} />
          <DatePicker.RangePicker format="DD.MM.YYYY" allowClear={false} value={period}
                                  onChange={(v) => v && v[0] && v[1] && setPeriod([v[0], v[1]])} />
          <Button type="primary" loading={busy} onClick={build}>Сформировать</Button>
          <Button icon={<FileExcelOutlined />} onClick={() => run(() => download(`/api/reports/${kind}`, { ...params, format: "xlsx" }))}>
            XLSX
          </Button>
          <Button icon={<FilePdfOutlined />} onClick={() => run(() => download(`/api/reports/${kind}`, { ...params, format: "pdf" }))}>
            PDF
          </Button>
        </Space>
      </Card>
      {!rep ? (
        <Card><Empty description="Выберите отчёт и период и нажмите «Сформировать»" /></Card>
      ) : (
        <>
          <Card title={rep.title} extra={rep.meta.map(([k, v]) => `${k}: ${v}`).join("; ")} style={{ marginBottom: 16 }}>
            <Row gutter={[16, 16]}>
              {rep.summary.map(([k, v]) => (
                <Col key={k} xs={12} md={6}>
                  <Statistic title={k} value={cell(v)} />
                </Col>
              ))}
            </Row>
          </Card>
          {rep.tables.map((t) => (
            <Card key={t.title} title={t.title} size="small" style={{ marginBottom: 16 }}>
              <Table size="small" rowKey={(_, i) => String(i)} dataSource={t.rows.map((r) => ({ r }))}
                     pagination={t.rows.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
                     scroll={{ x: true }}
                     columns={t.headers.map((h, i) => ({ title: h, key: h, render: (x: any) => cell(x.r[i]),
                                                         align: typeof t.rows[0]?.[i] === "number" ? "right" as const : undefined }))} />
            </Card>
          ))}
        </>
      )}
    </>
  );
}

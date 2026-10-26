import { useState } from "react";
import { Button, Card, Checkbox, Col, DatePicker, Input, Row, Select, Statistic, Table, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { Link } from "react-router-dom";
import { api } from "../api";
import { CLASS_COLORS, d, dpdColor, iso, LOAN_COLORS, LOAN_STATUSES, money, pct } from "../format";
import { useLoad, useProducts } from "../hooks";

interface LoanRow {
  id: number;
  contract_number: string;
  application_id: number;
  application_number: string;
  client_id: number;
  client: string;
  product: string;
  issued_at: string;
  amount: number;
  term_months: number;
  rate: number;
  status: string;
  status_name: string;
  max_dpd_12m: number;
  risk_class: string | null;
  pd: number | null;
}

interface ClassRow {
  risk_class: string;
  count: number;
  amount: number;
  defaults: number;
  default_rate: number | null;
  pd_avg: number | null;
}

interface Summary {
  count: number;
  amount: number;
  rate_avg: number | null;
  pd_avg: number | null;
  with_dpd: number;
  default_rate: number | null;
  by_status: Record<string, { count: number; amount: number }>;
  by_class: ClassRow[];
}

const muted = (text: string) => (
  <Typography.Text type="secondary" style={{ fontSize: 14 }}>
    {text}
  </Typography.Text>
);

/** Кредитный портфель: выданные кредиты, обслуживание, качество по классам риска (прогноз PD против факта). */
export default function Loans() {
  const products = useProducts();
  const [status, setStatus] = useState<string[]>([]);
  const [classes, setClasses] = useState<string[]>([]);
  const [productId, setProductId] = useState<number | undefined>();
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [overdue, setOverdue] = useState(false);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const reset = () => setPage(1);

  const { data, loading, reload } = useLoad(
    () =>
      api.get<{ total: number; items: LoanRow[]; summary: Summary }>("/api/loans", {
        status,
        risk_class: classes,
        product_id: productId,
        date_from: iso(period?.[0]),
        date_to: iso(period?.[1]),
        overdue: overdue || undefined,
        q: search,
        page,
        size: 50,
      }),
    [status.join(","), classes.join(","), productId, period?.[0]?.valueOf(), period?.[1]?.valueOf(), overdue, search, page],
  );
  const s = data?.summary;
  const st = (k: string) => s?.by_status[k] || { count: 0, amount: 0 };

  return (
    <>
      <Typography.Title level={3} className="page-title">
        Кредитный портфель
      </Typography.Title>
      <Card style={{ marginBottom: 16 }}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Input.Search
            placeholder="Договор, заявка или фамилия"
            allowClear
            style={{ width: 260 }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onSearch={(v) => {
              reset();
              setSearch(v.trim());
            }}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="Состояние"
            style={{ minWidth: 200 }}
            value={status}
            onChange={(v) => {
              reset();
              setStatus(v);
            }}
            options={Object.entries(LOAN_STATUSES).map(([value, label]) => ({ value, label }))}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="Класс риска"
            style={{ minWidth: 150 }}
            value={classes}
            onChange={(v) => {
              reset();
              setClasses(v);
            }}
            options={["A", "B", "C", "D", "E"].map((c) => ({ value: c, label: c }))}
          />
          <Select
            allowClear
            placeholder="Продукт"
            style={{ minWidth: 220 }}
            value={productId}
            onChange={(v) => {
              reset();
              setProductId(v);
            }}
            options={products.map((p) => ({ value: p.id, label: p.name }))}
          />
          <DatePicker.RangePicker
            format="DD.MM.YYYY"
            value={period as any}
            placeholder={["Выдан с", "по"]}
            onChange={(v) => {
              reset();
              setPeriod(v as any);
            }}
          />
          <Checkbox
            checked={overdue}
            onChange={(e) => {
              reset();
              setOverdue(e.target.checked);
            }}
          >
            С просрочкой
          </Checkbox>
          <Button icon={<ReloadOutlined />} onClick={() => reload()} />
        </div>
      </Card>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={4}>
          <Card>
            <Statistic title="Кредитов" value={money(s?.count)} />
          </Card>
        </Col>
        <Col xs={12} md={5}>
          <Card>
            <Statistic title="Выдано, руб." value={money(s?.amount)} />
          </Card>
        </Col>
        <Col xs={12} md={5}>
          <Card>
            <Statistic title="Действующие, руб." value={money(st("active").amount)} suffix={muted(`(${st("active").count})`)} />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card>
            <Statistic title="Погашено" value={money(st("closed").count)} />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card>
            <Statistic
              title="Дефолт"
              value={money(st("default").count)}
              valueStyle={{ color: "#cf1322" }}
              suffix={muted(pct(s?.default_rate, 1))}
            />
          </Card>
        </Col>
        <Col xs={12} md={4}>
          <Card>
            <Statistic title="Средняя ставка" value={s?.rate_avg ? s.rate_avg.toFixed(2).replace(".", ",") : "—"} suffix="%" />
          </Card>
        </Col>
      </Row>
      <Card title="Качество портфеля по классам риска на момент выдачи" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary">
          Прогноз — средняя вероятность дефолта по оценке системы при выдаче, факт — доля кредитов с просрочкой 90+ дней.
          Если факт заметно выше прогноза, методику нужно пересмотреть (раздел «Методика оценки»). Молодые кредиты
          ещё не успели «созреть», поэтому факт по ним занижен.
        </Typography.Paragraph>
        <Table<ClassRow>
          rowKey="risk_class"
          size="small"
          pagination={false}
          loading={loading}
          dataSource={s?.by_class || []}
          columns={[
            { title: "Класс риска", dataIndex: "risk_class", render: (v) => <Tag color={CLASS_COLORS[v]}>{v}</Tag> },
            { title: "Кредитов", dataIndex: "count", align: "right", render: money },
            { title: "Сумма, руб.", dataIndex: "amount", align: "right", render: money },
            {
              title: "Доля портфеля",
              dataIndex: "amount",
              key: "share",
              align: "right",
              render: (v) => pct(s?.amount ? v / s.amount : null, 1),
            },
            { title: "Прогноз PD", dataIndex: "pd_avg", align: "right", render: (v) => pct(v, 1) },
            { title: "Дефолтов", dataIndex: "defaults", align: "right" },
            { title: "Факт (доля дефолтов)", dataIndex: "default_rate", align: "right", render: (v) => pct(v, 1) },
          ]}
        />
      </Card>
      <Card title="Кредиты">
        <Table<LoanRow>
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={data?.items || []}
          scroll={{ x: 1000 }}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total || 0,
            showSizeChanger: false,
            showTotal: (t) => `Кредитов: ${t}`,
            onChange: setPage,
          }}
          columns={[
            {
              title: "Договор",
              dataIndex: "contract_number",
              className: "nw",
              render: (v, r) => (
                <>
                  {v}
                  <div>
                    <Link to={`/applications/${r.application_id}`} style={{ fontSize: 12 }}>
                      заявка {r.application_number}
                    </Link>
                  </div>
                </>
              ),
            },
            {
              title: "Заёмщик",
              dataIndex: "client",
              render: (v, r) => (
                <>
                  <Link to={`/clients/${r.client_id}`}>{v}</Link>
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {r.product}
                    </Typography.Text>
                  </div>
                </>
              ),
            },
            { title: "Выдан", dataIndex: "issued_at", render: d, className: "nw" },
            {
              title: "Сумма и условия",
              dataIndex: "amount",
              className: "nw",
              render: (v, r) => (
                <>
                  {money(v)} руб.
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {r.term_months} мес. · {String(r.rate).replace(".", ",")} %
                    </Typography.Text>
                  </div>
                </>
              ),
            },
            {
              title: "Класс / PD при выдаче",
              dataIndex: "risk_class",
              className: "nw",
              render: (v, r) =>
                v ? (
                  <>
                    <Tag color={CLASS_COLORS[v]}>{v}</Tag>
                    {pct(r.pd, 1)}
                  </>
                ) : (
                  "—"
                ),
            },
            {
              title: "Просрочка за 12 мес.",
              dataIndex: "max_dpd_12m",
              align: "center",
              render: (v) => (v ? <Tag color={dpdColor(v)}>{v} дн.</Tag> : "нет"),
            },
            {
              title: "Состояние",
              dataIndex: "status",
              render: (v, r) => <Tag color={LOAN_COLORS[v]}>{r.status_name}</Tag>,
            },
          ]}
        />
      </Card>
    </>
  );
}

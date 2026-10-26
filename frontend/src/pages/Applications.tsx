import { useState } from "react";
import { Button, Card, Checkbox, DatePicker, Input, Select, Table, Tag, Typography } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { CLASS_COLORS, dt, iso, money, pct, REC_COLORS, STATUS_COLORS } from "../format";
import { useDictionaries, useLoad } from "../hooks";

interface Row {
  id: number;
  number: string;
  created_at: string;
  status: string;
  status_name: string;
  client: string;
  product: string;
  amount: number;
  term_months: number;
  channel: string;
  risk_class: string | null;
  pd: number | null;
  recommendation: string | null;
  officer: string;
}

export default function Applications() {
  const { can } = useAuth();
  const nav = useNavigate();
  const dict = useDictionaries();
  const [status, setStatus] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);

  const { data, loading, reload } = useLoad(
    () =>
      api.get<{ total: number; items: Row[] }>("/api/applications", {
        status,
        q: search,
        date_from: iso(period?.[0]),
        date_to: iso(period?.[1]),
        mine,
        page,
        size: 50,
      }),
    [status.join(","), search, period?.[0]?.valueOf(), period?.[1]?.valueOf(), mine, page],
  );

  return (
    <>
      <div className="toolbar">
        <Typography.Title level={3} className="page-title" style={{ marginBottom: 0 }}>
          Кредитные заявки
        </Typography.Title>
        <span className="spacer" />
        {can("credit_officer") && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => nav("/applications/new")}>
            Новая заявка
          </Button>
        )}
      </div>
      <Card>
        <div className="toolbar">
          <Input.Search
            placeholder="Номер, фамилия или номер паспорта"
            allowClear
            style={{ width: 300 }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onSearch={(v) => {
              setPage(1);
              setSearch(v.trim());
            }}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="Состояние"
            style={{ minWidth: 260 }}
            value={status}
            onChange={(v) => {
              setPage(1);
              setStatus(v);
            }}
            options={Object.entries(dict?.statuses || {}).map(([value, label]) => ({ value, label }))}
          />
          <DatePicker.RangePicker
            format="DD.MM.YYYY"
            value={period as any}
            onChange={(v) => {
              setPage(1);
              setPeriod(v as any);
            }}
          />
          {can("credit_officer") && (
            <Checkbox checked={mine} onChange={(e) => setMine(e.target.checked)}>
              Только мои
            </Checkbox>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => reload()} />
        </div>
        <Table<Row>
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={data?.items || []}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total || 0,
            showSizeChanger: false,
            showTotal: (t) => `Всего: ${t}`,
            onChange: setPage,
          }}
          onRow={(r) => ({ onDoubleClick: () => nav(`/applications/${r.id}`) })}
          columns={[
            { title: "Номер", dataIndex: "number", render: (v, r) => <Link to={`/applications/${r.id}`}>{v}</Link> },
            { title: "Дата", dataIndex: "created_at", render: dt },
            { title: "Клиент", dataIndex: "client" },
            { title: "Продукт", dataIndex: "product" },
            { title: "Сумма, руб.", dataIndex: "amount", align: "right", render: money },
            { title: "Срок", dataIndex: "term_months", align: "right", render: (v) => `${v} мес.` },
            {
              title: "Класс / PD",
              dataIndex: "risk_class",
              render: (v, r) =>
                v ? (
                  <span>
                    <Tag color={CLASS_COLORS[v]}>{v}</Tag>
                    {pct(r.pd, 1)}
                  </span>
                ) : r.recommendation === "reject" ? (
                  <Tag color="red">стоп-фактор</Tag>
                ) : (
                  "—"
                ),
            },
            {
              title: "Рекомендация",
              dataIndex: "recommendation",
              render: (v) => (v ? <Tag color={REC_COLORS[v]}>{dict?.recommendations[v] || v}</Tag> : "—"),
            },
            {
              title: "Состояние",
              dataIndex: "status",
              render: (v, r) => <Tag color={STATUS_COLORS[v]}>{r.status_name}</Tag>,
            },
          ]}
        />
      </Card>
    </>
  );
}

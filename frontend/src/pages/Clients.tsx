import { useState } from "react";
import { Button, Card, Checkbox, Input, Table, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { d, dpdColor, money } from "../format";
import { useLoad } from "../hooks";

interface Row {
  id: number;
  full_name: string;
  birth_date: string;
  age: number;
  passport: string;
  phone: string;
  applications: number;
  approved: number;
  rejected: number;
  last_application_at: string | null;
  loans: number;
  active_loans: number;
  active_amount: number;
  defaults: number;
  max_dpd: number;
}

/** Реестр заёмщиков: все клиенты, обращавшиеся в Банк, с итогами по заявкам и кредитам. */
export default function Clients() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [withLoans, setWithLoans] = useState(false);
  const [overdue, setOverdue] = useState(false);
  const [page, setPage] = useState(1);
  const { data, loading, reload } = useLoad(
    () =>
      api.get<{ total: number; items: Row[] }>("/api/clients", {
        q: search,
        with_loans: withLoans || undefined,
        overdue: overdue || undefined,
        page,
        size: 50,
      }),
    [search, withLoans, overdue, page],
  );

  return (
    <>
      <Typography.Title level={3} className="page-title">
        Заёмщики
      </Typography.Title>
      <Card>
        <div className="toolbar">
          <Input.Search
            placeholder="Фамилия, имя, номер паспорта или телефон"
            allowClear
            style={{ width: 340 }}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onSearch={(v) => {
              setPage(1);
              setSearch(v.trim());
            }}
          />
          <Checkbox checked={withLoans} onChange={(e) => { setPage(1); setWithLoans(e.target.checked); }}>
            Только с кредитами
          </Checkbox>
          <Checkbox checked={overdue} onChange={(e) => { setPage(1); setOverdue(e.target.checked); }}>
            С просрочкой
          </Checkbox>
          <Button icon={<ReloadOutlined />} onClick={() => reload()} />
        </div>
        <Table<Row>
          rowKey="id"
          size="middle"
          loading={loading}
          dataSource={data?.items || []}
          scroll={{ x: 1150 }}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total || 0,
            showSizeChanger: false,
            showTotal: (t) => `Клиентов: ${t}`,
            onChange: setPage,
          }}
          onRow={(r) => ({ onDoubleClick: () => nav(`/clients/${r.id}`) })}
          columns={[
            { title: "Клиент", dataIndex: "full_name", render: (v, r) => <Link to={`/clients/${r.id}`}>{v}</Link> },
            { title: "Дата рождения", dataIndex: "birth_date", render: (v, r) => `${d(v)} (${r.age})` },
            { title: "Паспорт", dataIndex: "passport", className: "nw" },
            { title: "Телефон", dataIndex: "phone", className: "nw" },
            {
              title: "Заявки",
              dataIndex: "applications",
              align: "center",
              render: (v, r) => (
                <span className="nw">
                  {v}
                  {r.approved > 0 && <Tag color="green" style={{ marginLeft: 6 }}>одобр. {r.approved}</Tag>}
                  {r.rejected > 0 && <Tag color="red">отказ {r.rejected}</Tag>}
                </span>
              ),
            },
            { title: "Последнее обращение", dataIndex: "last_application_at", render: d },
            {
              title: "Кредиты",
              dataIndex: "loans",
              align: "center",
              render: (v, r) => (v ? `${v} (действ. ${r.active_loans})` : "—"),
            },
            { title: "Действующая задолженность, руб.", dataIndex: "active_amount", align: "right", render: (v) => (v ? money(v) : "—") },
            {
              title: "Макс. просрочка",
              dataIndex: "max_dpd",
              align: "center",
              render: (v, r) =>
                r.defaults ? <Tag color="red">дефолт</Tag> : v ? <Tag color={dpdColor(v)}>{v} дн.</Tag> : "—",
            },
          ]}
        />
      </Card>
    </>
  );
}

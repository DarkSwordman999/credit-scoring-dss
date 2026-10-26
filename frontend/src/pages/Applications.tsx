import { useState } from "react";
import { Button, Card, Checkbox, DatePicker, Input, Select, Table, Typography } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { appColumns, type AppRow } from "../appColumns";
import { iso } from "../format";
import { useDictionaries, useLoad, useProducts } from "../hooks";

export default function Applications() {
  const { can } = useAuth();
  const nav = useNavigate();
  const dict = useDictionaries();
  const [status, setStatus] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [mine, setMine] = useState(false);
  const [productId, setProductId] = useState<number | undefined>();
  const [classes, setClasses] = useState<string[]>([]);
  const products = useProducts();
  const [page, setPage] = useState(1);

  const { data, loading, reload } = useLoad(
    () =>
      api.get<{ total: number; items: AppRow[] }>("/api/applications", {
        status,
        q: search,
        date_from: iso(period?.[0]),
        date_to: iso(period?.[1]),
        mine,
        product_id: productId,
        risk_class: classes,
        page,
        size: 50,
      }),
    [status.join(","), search, period?.[0]?.valueOf(), period?.[1]?.valueOf(), mine, productId, classes.join(","), page],
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
          <Select
            allowClear
            placeholder="Продукт"
            style={{ minWidth: 220 }}
            value={productId}
            onChange={(v) => {
              setPage(1);
              setProductId(v);
            }}
            options={products.map((p) => ({ value: p.id, label: p.name }))}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="Класс риска"
            style={{ minWidth: 150 }}
            value={classes}
            onChange={(v) => {
              setPage(1);
              setClasses(v);
            }}
            options={["A", "B", "C", "D", "E"].map((c) => ({ value: c, label: c }))}
          />
          {can("credit_officer") && (
            <Checkbox checked={mine} onChange={(e) => setMine(e.target.checked)}>
              Только мои
            </Checkbox>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => reload()} />
        </div>
        <Table<AppRow>
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
          columns={appColumns(dict?.recommendations)}
        />
      </Card>
    </>
  );
}

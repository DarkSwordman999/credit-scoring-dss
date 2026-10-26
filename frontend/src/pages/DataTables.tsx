import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Input, List, Row, Select, Table, Tag, Tooltip, Typography } from "antd";
import { KeyOutlined, LinkOutlined, ReloadOutlined } from "@ant-design/icons";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useLoad } from "../hooks";

interface TableInfo {
  name: string;
  title: string;
  rows: number;
  columns: number;
}

interface Column {
  name: string;
  type: string;
  pk: boolean;
  fk: string | null;
  masked: boolean;
}

interface Rows {
  name: string;
  title: string;
  total: number;
  columns: Column[];
  items: Record<string, any>[];
}

const show = (v: any) => {
  if (v === null || v === undefined) return <Typography.Text type="secondary">NULL</Typography.Text>;
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") {
    const s = JSON.stringify(v);
    return (
      <Tooltip title={<pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(v, null, 2)}</pre>}>
        <span>{s.length > 60 ? s.slice(0, 60) + "…" : s}</span>
      </Tooltip>
    );
  }
  const s = String(v);
  return s.length > 80 ? <Tooltip title={s}>{s.slice(0, 80) + "…"}</Tooltip> : s;
};

/** Просмотр таблиц базы данных «как есть» (только чтение). */
export default function DataTables() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const name = params.get("t") || "applications";
  const [page, setPage] = useState(1);
  const [column, setColumn] = useState<string | undefined>();
  const [value, setValue] = useState("");
  const [filter, setFilter] = useState<{ column?: string; value: string }>({ value: "" });

  const tables = useLoad(() => api.get<TableInfo[]>("/api/data/tables"));
  const { data, loading, reload } = useLoad(
    () => api.get<Rows>(`/api/data/tables/${name}`, { page, size: 100, column: filter.column, value: filter.value }),
    [name, page, filter.column, filter.value],
  );
  useEffect(() => {
    setPage(1);
    setColumn(undefined);
    setValue("");
    setFilter({ value: "" });
  }, [name]);

  return (
    <>
      <Typography.Title level={3} className="page-title">
        Таблицы базы данных
      </Typography.Title>
      {user?.role !== "head" && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Персональные данные клиентов скрыты (***): их видит только руководитель кредитного отдела."
        />
      )}
      <Row gutter={16}>
        <Col xs={24} lg={6}>
          <Card title="Таблицы" size="small" bodyStyle={{ padding: 0 }}>
            <List
              size="small"
              loading={tables.loading}
              dataSource={tables.data || []}
              renderItem={(t) => (
                <List.Item
                  onClick={() => setParams({ t: t.name })}
                  style={{ cursor: "pointer", padding: "6px 12px", background: t.name === name ? "#e6f0ff" : undefined }}
                >
                  <List.Item.Meta
                    title={<span style={{ fontFamily: "monospace" }}>{t.name}</span>}
                    description={<span style={{ fontSize: 12 }}>{t.title}</span>}
                  />
                  <Tag>{t.rows.toLocaleString("ru-RU")}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={18}>
          <Card
            size="small"
            title={
              <span>
                <span style={{ fontFamily: "monospace" }}>{name}</span>
                {data && <Typography.Text type="secondary"> — {data.title}</Typography.Text>}
              </span>
            }
          >
            <div className="toolbar">
              <Select
                allowClear
                placeholder="Столбец"
                style={{ width: 200 }}
                value={column}
                onChange={setColumn}
                options={(data?.columns || []).filter((c) => !c.masked).map((c) => ({ value: c.name, label: c.name }))}
              />
              <Input.Search
                placeholder="Значение (для текста — часть строки)"
                allowClear
                style={{ width: 280 }}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onSearch={(v) => {
                  setPage(1);
                  setFilter({ column, value: v.trim() });
                }}
              />
              <Button icon={<ReloadOutlined />} onClick={() => reload()} />
            </div>
            <Table
              rowKey={(_, i) => String(i)}
              size="small"
              bordered
              loading={loading}
              dataSource={data?.items || []}
              scroll={{ x: "max-content" }}
              pagination={{
                current: page,
                pageSize: 100,
                total: data?.total || 0,
                showSizeChanger: false,
                showTotal: (t) => `Строк: ${t.toLocaleString("ru-RU")}`,
                onChange: setPage,
              }}
              columns={(data?.columns || []).map((c) => ({
                key: c.name,
                dataIndex: c.name,
                className: "nw",
                title: (
                  <Tooltip title={`${c.type}${c.fk ? ` → ${c.fk}` : ""}`}>
                    <span style={{ fontFamily: "monospace" }}>
                      {c.pk && <KeyOutlined style={{ color: "#d4b106", marginRight: 4 }} />}
                      {c.fk && <LinkOutlined style={{ color: "#1677ff", marginRight: 4 }} />}
                      {c.name}
                    </span>
                  </Tooltip>
                ),
                render: show,
              }))}
            />
          </Card>
        </Col>
      </Row>
    </>
  );
}

import { useState } from "react";
import { Button, Card, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Select, Space, Table, Tabs, Tag,
  Typography } from "antd";
import { CloudDownloadOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { api, download } from "../api";
import { dt, iso, money } from "../format";
import { useAction, useDictionaries, useLoad } from "../hooks";

/** Администрирование (П-12, П-13, Н-1). Руководителю отдела доступен только журнал аудита (only="audit"). */
export default function Admin({ only }: { only?: "audit" }) {
  if (only === "audit") {
    return (
      <>
        <Typography.Title level={3} className="page-title">Журнал аудита</Typography.Title>
        <Card><Audit /></Card>
      </>
    );
  }
  return (
    <>
      <Typography.Title level={3} className="page-title">Администрирование</Typography.Title>
      <Card>
        <Tabs items={[
          { key: "u", label: "Пользователи и роли", children: <Users /> },
          { key: "s", label: "Параметры", children: <Settings /> },
          { key: "a", label: "Журнал аудита", children: <Audit /> },
          { key: "i", label: "Журнал обмена", children: <IntegrationLog /> },
          { key: "b", label: "Резервные копии", children: <Backups /> },
        ]} />
      </Card>
    </>
  );
}

function Users() {
  const dict = useDictionaries();
  const { data, loading, reload } = useLoad(() => api.get<any[]>("/api/admin/users"));
  const [edit, setEdit] = useState<any | null>(null);
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  const role = Form.useWatch("role", form);
  const unlimited = Form.useWatch("unlimited", form);
  const save = async (v: any) => {
    const body = { ...v, limit_amount: v.unlimited ? null : v.limit_amount ?? null, password: v.password || null };
    const r = await run(() => (edit?.id ? api.put(`/api/admin/users/${edit.id}`, body) : api.post("/api/admin/users", body)), "Сохранено");
    if (r) {
      setEdit(null);
      reload();
    }
  };
  const open = (u: any) => {
    form.resetFields();
    form.setFieldsValue(u.id ? { ...u, unlimited: u.limit_amount === null } : { role: "credit_officer", active: true, unlimited: true });
    setEdit(u);
  };
  return (
    <>
      <div className="toolbar">
        <Button icon={<PlusOutlined />} onClick={() => open({})}>Пользователь</Button>
      </div>
      <Table rowKey="id" size="middle" loading={loading} dataSource={data || []} pagination={false}
        onRow={(r) => ({ onDoubleClick: () => open(r) })}
        columns={[
          { title: "Логин", dataIndex: "login" },
          { title: "ФИО", dataIndex: "full_name" },
          { title: "Роль", dataIndex: "role_name" },
          {
            title: "Лимит полномочий", dataIndex: "limit_amount",
            render: (v, r) => (r.role === "underwriter" || r.role === "head" ? (v === null ? "без ограничения" : `${money(v)} руб.`) : "—"),
          },
          { title: "Состояние", dataIndex: "active", render: (v) => (v ? "активен" : <Tag color="red">заблокирован</Tag>) },
          { title: "", render: (_, r) => <Button size="small" type="link" onClick={() => open(r)}>изменить</Button> },
        ]} />
      <Modal open={!!edit} title={edit?.id ? `Пользователь ${edit.login}` : "Новый пользователь"} onCancel={() => setEdit(null)}
             onOk={() => form.submit()} confirmLoading={busy} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={save}>
          <Form.Item name="login" label="Логин" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
          <Form.Item name="full_name" label="ФИО" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="role" label="Роль" rules={[{ required: true }]}>
            <Select options={Object.entries(dict?.roles || {}).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          {(role === "underwriter" || role === "head") && (
            <Space align="end">
              <Form.Item name="limit_amount" label="Лимит полномочий, руб. (С-12)">
                <InputNumber min={0} step={100000} style={{ width: 200 }} disabled={unlimited} />
              </Form.Item>
              <Form.Item name="unlimited" valuePropName="checked"><Checkbox>без ограничения</Checkbox></Form.Item>
            </Space>
          )}
          <Form.Item name="password" label={edit?.id ? "Новый пароль (если нужно сменить)" : "Пароль"}
                     rules={[{ required: !edit?.id, min: 6, message: "Не короче 6 символов" }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="active" valuePropName="checked"><Checkbox>Активен</Checkbox></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function Settings() {
  const { data, setData } = useLoad(() => api.get<{ values: Record<string, any>; labels: Record<string, string> }>("/api/admin/settings"));
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  if (!data) return null;
  const keys = Object.keys(data.labels).filter((k) => k !== "risk_classes");
  const save = async (v: any) => {
    const r = await run(() => api.put<any>("/api/admin/settings", v), "Параметры сохранены");
    if (r) setData(r);
  };
  return (
    <Form form={form} layout="horizontal" labelCol={{ span: 10 }} wrapperCol={{ span: 10 }} initialValues={data.values}
          onFinish={save} style={{ maxWidth: 900 }}>
      {keys.map((k) => (
        <Form.Item key={k} name={k} label={data.labels[k]}>
          {k.endsWith("_mode") ? (
            <Select options={[{ value: "demo", label: "Встроенный имитатор (демо)" }, { value: "http", label: "HTTP API" }]} />
          ) : k.endsWith("_url") ? <Input placeholder="https://…" /> : <InputNumber step={k.includes("rate") || k.includes("alert") ? 0.01 : 1} />}
        </Form.Item>
      ))}
      <Typography.Paragraph type="secondary">
        Пороги классов риска и матрица условий — в «Справочники → Классы риска и условия».
      </Typography.Paragraph>
      <Button type="primary" htmlType="submit" loading={busy}>Сохранить</Button>
    </Form>
  );
}

function Audit() {
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [login, setLogin] = useState("");
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const { run } = useAction();
  const params = { date_from: iso(period?.[0]), date_to: iso(period?.[1]), login, action, entity };
  const { data, loading, reload } = useLoad(
    () => api.get<{ total: number; items: any[] }>("/api/admin/audit", { ...params, page, size: 100 }),
    [period?.[0]?.valueOf(), period?.[1]?.valueOf(), login, action, entity, page],
  );
  return (
    <>
      <Typography.Paragraph type="secondary">
        Записи журнала не изменяются и не удаляются — это обеспечивает СУБД (С-18).
      </Typography.Paragraph>
      <div className="toolbar">
        <DatePicker.RangePicker format="DD.MM.YYYY" value={period as any} onChange={(v) => { setPage(1); setPeriod(v as any); }} />
        <Input.Search placeholder="Пользователь (логин)" allowClear style={{ width: 200 }} onSearch={(v) => { setPage(1); setLogin(v.trim()); }} />
        <Input.Search placeholder="Действие" allowClear style={{ width: 200 }} onSearch={(v) => { setPage(1); setAction(v.trim()); }} />
        <Input.Search placeholder="Номер объекта" allowClear style={{ width: 200 }} onSearch={(v) => { setPage(1); setEntity(v.trim()); }} />
        <Button icon={<ReloadOutlined />} onClick={() => reload()} />
        <Button icon={<DownloadOutlined />} onClick={() => run(() => download("/api/admin/audit", { ...params, xlsx: true }))}>XLSX</Button>
      </div>
      <Table rowKey="id" size="small" loading={loading} dataSource={data?.items || []}
        pagination={{ current: page, pageSize: 100, total: data?.total || 0, showSizeChanger: false, onChange: setPage,
                      showTotal: (t) => `Записей: ${t}` }}
        columns={[
          { title: "Время", dataIndex: "created_at", render: dt, width: 150 },
          { title: "Пользователь", dataIndex: "user", width: 120 },
          { title: "Действие", dataIndex: "action" },
          { title: "Объект", render: (_, r) => [r.entity, r.entity_id].filter(Boolean).join(" ") },
          {
            title: "Изменения", dataIndex: "changes",
            render: (v: Record<string, any>) => Object.entries(v || {})
              .map(([k, x]) => `${k}: ${Array.isArray(x) ? `${x[0] ?? "—"} → ${typeof x[1] === "object" ? JSON.stringify(x[1]) : x[1] ?? "—"}` : x}`)
              .join("; "),
          },
        ]} />
    </>
  );
}

function IntegrationLog() {
  const [system, setSystem] = useState<string | undefined>();
  const { data, loading, reload } = useLoad(() => api.get<any[]>("/api/admin/integration-log", { system }), [system]);
  return (
    <>
      <div className="toolbar">
        <Select allowClear placeholder="Система" style={{ width: 220 }} value={system} onChange={setSystem}
                options={[{ value: "bki", label: "БКИ" }, { value: "abs", label: "АБС" }, { value: "scoring", label: "Сервис скоринга" },
                          { value: "notify", label: "Уведомления" }, { value: "scheduler", label: "Планировщик" }]} />
        <Button icon={<ReloadOutlined />} onClick={() => reload()} />
      </div>
      <Table rowKey="id" size="small" loading={loading} dataSource={data || []}
        columns={[
          { title: "Время", dataIndex: "created_at", render: dt, width: 150 },
          { title: "Система", dataIndex: "system", width: 110 },
          { title: "Направление", dataIndex: "direction", width: 110, render: (v) => (v === "in" ? "входящий" : "исходящий") },
          { title: "Статус", dataIndex: "status", width: 90, render: (v) => <Tag color={v === "ok" ? "green" : v === "warn" ? "orange" : "red"}>{v}</Tag> },
          { title: "Сообщение", dataIndex: "message" },
        ]} />
    </>
  );
}

function Backups() {
  const { data, loading, reload } = useLoad(() => api.get<any[]>("/api/admin/backups"));
  const { busy, run } = useAction();
  return (
    <>
      <Typography.Paragraph type="secondary">
        Копия создаётся автоматически каждый день в 02:00, хранятся 14 последних (Н-1). Восстановление — командой
        «creditdss restore &lt;копия&gt;» при остановленной программе.
      </Typography.Paragraph>
      <div className="toolbar">
        <Button type="primary" icon={<CloudDownloadOutlined />} loading={busy}
                onClick={async () => { if (await run(() => api.post("/api/admin/backups"), "Копия создана")) reload(); }}>
          Создать копию сейчас
        </Button>
      </div>
      <Table rowKey="name" size="small" loading={loading} dataSource={data || []} pagination={false}
        columns={[
          { title: "Файл", dataIndex: "name" },
          { title: "Размер", dataIndex: "size", render: (v) => `${(v / 1024 / 1024).toFixed(1)} МБ` },
          { title: "Создана", dataIndex: "created", render: dt },
          { title: "", render: (_, r) => <Button size="small" type="link" onClick={() => run(() => download(`/api/admin/backups/${r.name}`))}>скачать</Button> },
        ]} />
    </>
  );
}

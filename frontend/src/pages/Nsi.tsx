import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Checkbox, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Select, Space,
  Switch, Table, Tabs, Tag, Typography } from "antd";
import { DeleteOutlined, PlusOutlined, SaveOutlined } from "@ant-design/icons";
import { api } from "../api";
import { useAuth } from "../auth";
import { CLASS_COLORS, d, iso, money, REC_COLORS } from "../format";
import { useAction, useLoad, type Product } from "../hooks";

/** Справочники кредитной политики (П-12): продукты, стоп-факторы, классы риска и матрица условий, стоп-лист. */
export default function Nsi() {
  const { can } = useAuth();
  const items = [
    { key: "p", label: "Кредитные продукты", children: <Products /> },
    { key: "s", label: "Стоп-факторы", children: <StopFactors /> },
    { key: "c", label: "Классы риска и условия", children: <Conditions /> },
  ];
  if (can("admin", "risk_analyst", "underwriter", "head")) items.push({ key: "l", label: "Стоп-лист", children: <StopList /> });
  return (
    <>
      <Typography.Title level={3} className="page-title">Справочники</Typography.Title>
      <Card><Tabs items={items} /></Card>
    </>
  );
}

function Products() {
  const { can } = useAuth();
  const { data, loading, reload } = useLoad(() => api.get<Product[]>("/api/nsi/products"));
  const [edit, setEdit] = useState<Partial<Product> | null>(null);
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  const admin = can("admin");
  const save = async (v: any) => {
    const r = await run(() => (edit?.id ? api.put(`/api/nsi/products/${edit.id}`, v) : api.post("/api/nsi/products", v)), "Сохранено");
    if (r) {
      setEdit(null);
      reload();
    }
  };
  return (
    <>
      {admin && (
        <div className="toolbar">
          <Button icon={<PlusOutlined />} onClick={() => { form.resetFields(); form.setFieldsValue({ active: true }); setEdit({}); }}>
            Продукт
          </Button>
        </div>
      )}
      <Table<Product> rowKey="id" size="middle" loading={loading} dataSource={data || []} pagination={false}
        onRow={(r) => ({ onDoubleClick: () => { if (admin) { form.setFieldsValue(r); setEdit(r); } } })}
        columns={[
          { title: "Продукт", dataIndex: "name" },
          { title: "Сумма, руб.", render: (_, r) => `${money(r.min_amount)} – ${money(r.max_amount)}` },
          { title: "Срок, мес.", render: (_, r) => `${r.min_term} – ${r.max_term}` },
          { title: "Базовая ставка", dataIndex: "base_rate", render: (v) => `${v} %` },
          { title: "Действует", dataIndex: "active", render: (v) => (v ? "да" : <Tag>нет</Tag>) },
        ]} />
      <Modal open={!!edit} title={edit?.id ? "Кредитный продукт" : "Новый продукт"} onCancel={() => setEdit(null)}
             onOk={() => form.submit()} confirmLoading={busy} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={save}>
          <Form.Item name="name" label="Название" rules={[{ required: true }]}><Input /></Form.Item>
          <Space>
            <Form.Item name="min_amount" label="Сумма от" rules={[{ required: true }]}><InputNumber min={1} step={10000} /></Form.Item>
            <Form.Item name="max_amount" label="до" rules={[{ required: true }]}><InputNumber min={1} step={10000} /></Form.Item>
          </Space>
          <Space>
            <Form.Item name="min_term" label="Срок от, мес." rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
            <Form.Item name="max_term" label="до" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
            <Form.Item name="base_rate" label="Ставка, %" rules={[{ required: true }]}><InputNumber min={0.1} max={99} step={0.1} /></Form.Item>
          </Space>
          <Form.Item name="active" valuePropName="checked"><Checkbox>Действует</Checkbox></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function StopFactors() {
  const { can } = useAuth();
  const { data, loading, reload } = useLoad(() => api.get<any[]>("/api/nsi/stop-factors"));
  const rules = useLoad(() => api.get<any[]>("/api/nsi/stop-factor-rules"));
  const [edit, setEdit] = useState<any | null>(null);
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  const editor = can("risk_analyst", "admin");
  const rule = Form.useWatch("rule", form);
  const needs = rules.data?.find((r) => r.rule === rule)?.needs_threshold;
  const save = async (v: any) => {
    const body = { ...v, threshold: needs ? v.threshold : null };
    const r = await run(() => (edit?.id ? api.put(`/api/nsi/stop-factors/${edit.id}`, body) : api.post("/api/nsi/stop-factors", body)), "Сохранено");
    if (r) {
      setEdit(null);
      reload();
    }
  };
  const toggle = async (r: any, active: boolean) => {
    if (await run(() => api.put(`/api/nsi/stop-factors/${r.id}`, { ...r, active }), active ? "Включён" : "Отключён")) reload();
  };
  return (
    <>
      <Typography.Paragraph type="secondary">
        При срабатывании хотя бы одного активного стоп-фактора система рекомендует отказ с указанием кода (С-5).
        {editor ? " Настраивает риск-аналитик." : ""}
      </Typography.Paragraph>
      {editor && (
        <div className="toolbar">
          <Button icon={<PlusOutlined />} onClick={() => { form.resetFields(); form.setFieldsValue({ active: true }); setEdit({}); }}>
            Стоп-фактор
          </Button>
        </div>
      )}
      <Table rowKey="id" size="middle" loading={loading} dataSource={data || []} pagination={false}
        onRow={(r) => ({ onDoubleClick: () => { if (editor) { form.setFieldsValue(r); setEdit(r); } } })}
        columns={[
          { title: "Код", dataIndex: "code", width: 80 },
          { title: "Описание", dataIndex: "description" },
          { title: "Условие", dataIndex: "rule_name" },
          { title: "Порог", dataIndex: "threshold", render: (v, r) => (r.needs_threshold ? v : "—") },
          {
            title: "Активен", dataIndex: "active", width: 100,
            render: (v, r) => (editor ? <Switch size="small" checked={v} onChange={(x) => toggle(r, x)} /> : v ? "да" : "нет"),
          },
        ]} />
      <Modal open={!!edit} title="Стоп-фактор" onCancel={() => setEdit(null)} onOk={() => form.submit()} confirmLoading={busy} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={save}>
          <Form.Item name="code" label="Код" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="Описание" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="rule" label="Условие" rules={[{ required: true }]}>
            <Select options={(rules.data || []).map((r) => ({ value: r.rule, label: r.name }))} />
          </Form.Item>
          {needs && <Form.Item name="threshold" label="Порог" rules={[{ required: true }]}><InputNumber step={0.01} /></Form.Item>}
          <Form.Item name="active" valuePropName="checked"><Checkbox>Активен</Checkbox></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

interface Rule {
  risk_class: string;
  pdn_from: number;
  pdn_to: number;
  decision: string;
  amount_factor: number;
  rate_add: number;
}

function Conditions() {
  const { can } = useAuth();
  const { message } = App.useApp();
  const { data, reload } = useLoad(() => api.get<{ classes: [string, number | null][]; rules: Rule[] }>("/api/nsi/conditions"));
  const [classes, setClasses] = useState<[string, number | null][]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const { busy, run } = useAction();
  const editor = can("risk_analyst", "admin");
  useEffect(() => {
    if (data) {
      setClasses(data.classes);
      setRules(data.rules);
    }
  }, [data]);
  const upd = (i: number, k: keyof Rule, v: any) => setRules(rules.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const save = async () => {
    if (await run(() => api.put("/api/nsi/conditions", { classes, rules }), "Классы и матрица условий сохранены")) reload();
  };
  const toText = (v: number) => (v >= 99 ? "∞" : `${Math.round(v * 100)} %`);
  return (
    <>
      <Typography.Paragraph type="secondary">
        Класс риска присваивается по порогам PD (С-7); рекомендация и условия кредита — по матрице «класс риска × ПДН» (С-10).
      </Typography.Paragraph>
      <Card size="small" title="Пороги PD" style={{ marginBottom: 16 }}>
        <Space wrap>
          {classes.map(([name, upper], i) => (
            <Space key={name}>
              <Tag color={CLASS_COLORS[name]}>{name}</Tag>
              {upper === null ? "свыше предыдущего" : (
                <>
                  до
                  <InputNumber size="small" min={0.001} max={1} step={0.01} value={upper} disabled={!editor}
                               onChange={(v) => setClasses(classes.map((c, j) => (j === i ? [c[0], v ?? 0] : c)))} />
                </>
              )}
            </Space>
          ))}
        </Space>
      </Card>
      <Table size="small" rowKey={(_, i) => String(i)} dataSource={rules} pagination={false}
        columns={[
          { title: "Класс", dataIndex: "risk_class", render: (v) => <Tag color={CLASS_COLORS[v]}>{v}</Tag> },
          { title: "ПДН", render: (_, r) => `${toText(r.pdn_from)} – ${toText(r.pdn_to)}` },
          {
            title: "Рекомендация", dataIndex: "decision",
            render: (v, _, i) => editor ? (
              <Select size="small" value={v} style={{ width: 240 }} onChange={(x) => upd(i, "decision", x)}
                      options={[{ value: "approve", label: "Одобрить" }, { value: "approve_changed", label: "Одобрить на изменённых условиях" },
                                { value: "reject", label: "Отказать" }]} />
            ) : <Tag color={REC_COLORS[v]}>{v}</Tag>,
          },
          {
            title: "Множитель суммы", dataIndex: "amount_factor",
            render: (v, r, i) => editor && r.decision !== "reject" ? (
              <InputNumber size="small" min={0} max={1} step={0.05} value={v} onChange={(x) => upd(i, "amount_factor", x ?? 0)} />
            ) : r.decision === "reject" ? "—" : v,
          },
          {
            title: "Надбавка к ставке, п. п.", dataIndex: "rate_add",
            render: (v, r, i) => editor && r.decision !== "reject" ? (
              <InputNumber size="small" min={-50} max={50} step={0.5} value={v} onChange={(x) => upd(i, "rate_add", x ?? 0)} />
            ) : r.decision === "reject" ? "—" : v,
          },
        ]} />
      {editor && (
        <Button type="primary" icon={<SaveOutlined />} loading={busy} style={{ marginTop: 12 }}
                onClick={() => (classes.length ? save() : message.error("Нет классов"))}>
          Сохранить
        </Button>
      )}
      {!editor && <Alert type="info" showIcon style={{ marginTop: 12 }} message="Изменяет риск-аналитик" />}
    </>
  );
}

const SOURCES: Record<string, string> = {
  invalid_passport: "Недействительный паспорт",
  rosfin: "Перечень Росфинмониторинга",
  internal: "Внутренний стоп-лист",
};

function StopList() {
  const { can } = useAuth();
  const { data, loading, reload } = useLoad(() => api.get<any[]>("/api/nsi/stoplist"));
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const { busy, run } = useAction();
  const admin = can("admin");
  const save = async (v: any) => {
    if (await run(() => api.post("/api/nsi/stoplist", { ...v, birth_date: iso(v.birth_date) || null }), "Запись добавлена")) {
      setOpen(false);
      reload();
    }
  };
  return (
    <>
      {admin && (
        <div className="toolbar">
          <Button icon={<PlusOutlined />} onClick={() => { form.resetFields(); form.setFieldsValue({ source: "internal" }); setOpen(true); }}>
            Запись
          </Button>
        </div>
      )}
      <Table rowKey="id" size="middle" loading={loading} dataSource={data || []}
        columns={[
          { title: "Источник", dataIndex: "source", render: (v) => SOURCES[v] || v },
          { title: "Паспорт", render: (_, r) => (r.passport_series ? `${r.passport_series} ${r.passport_number}` : "—") },
          { title: "ФИО", dataIndex: "full_name", render: (v) => v || "—" },
          { title: "Дата рождения", dataIndex: "birth_date", render: d },
          { title: "Основание", dataIndex: "reason" },
          ...(admin ? [{
            title: "", width: 60, render: (_: any, r: any) => (
              <Popconfirm title="Удалить запись?" onConfirm={async () => { if (await run(() => api.del(`/api/nsi/stoplist/${r.id}`), "Удалено")) reload(); }}>
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            ),
          }] : []),
        ]} />
      <Modal open={open} title="Запись стоп-листа" onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={busy} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={save}>
          <Form.Item name="source" label="Источник"><Select options={Object.entries(SOURCES).map(([value, label]) => ({ value, label }))} /></Form.Item>
          <Space>
            <Form.Item name="passport_series" label="Серия"><Input maxLength={4} style={{ width: 90 }} /></Form.Item>
            <Form.Item name="passport_number" label="Номер"><Input maxLength={6} style={{ width: 120 }} /></Form.Item>
          </Space>
          <Form.Item name="full_name" label="ФИО"><Input /></Form.Item>
          <Form.Item name="birth_date" label="Дата рождения"><DatePicker format="DD.MM.YYYY" /></Form.Item>
          <Form.Item name="reason" label="Основание"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
